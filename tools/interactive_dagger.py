import copy
import json
import os
import sys
import threading
import time
from collections import defaultdict

from flask import Flask, render_template, request, jsonify
from kaggle_environments import make

import main

app = Flask(__name__)
DATASET_FILE = "dagger_dataset.jsonl"

# Thread synchronization events
agent_event = threading.Event()
flask_event = threading.Event()

# Shared state between Kaggle Engine thread and Flask thread
shared_state = {
    "status": "processing",
    "board": {},
    "options": [],
    "turn": 0,
    "selected_action": None,
    "reasoning": "",
    "raw_obs": None,
    "raw_heuristic": None
}

def translate_option(opt, obs_dict):
    t = str(opt.get("type", "UNKNOWN"))
    detail = ""
    us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
    
    if t == "PLAY" or t == "1" or t == "3":
        idx = opt.get("index", 0)
        try:
            detail = f"PLAY CARD: {us['hand'][idx].get('name', '?')}"
        except:
            detail = f"PLAY Idx: {idx}"
    elif t == "ATTACK" or t == "5":
        detail = f"ATTACK: {opt.get('attackId')}"
    elif t == "ATTACH" or t == "4":
        idx = opt.get("index", 0)
        try:
            detail = f"ATTACH ENERGY: {us['hand'][idx].get('name', '?')}"
        except:
            detail = f"ATTACH Idx: {idx}"
    elif t == "RETREAT" or t == "6":
        detail = "RETREAT ACTIVE"
    elif t == "ABILITY" or t == "2":
        detail = "USE ABILITY"
    else:
        detail = f"TYPE {t}"
    return detail

def extract_card_info(c):
    if not c: return None
    return {
        "name": c.get("name", "Unknown"),
        "hp": c.get("hp", 0),
        "damage": c.get("damage", 0),
        "energy": len(c.get("energy", []))
    }

def safe_len(lst):
    return len(lst) if lst is not None else 0

def build_board_state(obs_dict):
    try:
        us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
        opp = obs_dict["current"]["players"][1 - obs_dict["current"]["yourIndex"]]
        
        return {
            "my_active": extract_card_info(us["active"][0] if us.get("active") else None),
            "my_bench": [extract_card_info(c) for c in us.get("bench") if c] if us.get("bench") else [],
            "my_hand": [extract_card_info(c) for c in us.get("hand") if c] if us.get("hand") else [],
            "my_prizes": safe_len(us.get("prize")),
            "my_deck": safe_len(us.get("deck")),
            "my_discard": safe_len(us.get("discard")),
            "opp_active": extract_card_info(opp["active"][0] if opp.get("active") else None),
            "opp_bench": [extract_card_info(c) for c in opp.get("bench") if c] if opp.get("bench") else [],
            "opp_prizes": safe_len(opp.get("prize")),
            "opp_deck": safe_len(opp.get("deck")),
            "opp_discard": safe_len(opp.get("discard"))
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"error": str(e)}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/state")
def get_state():
    return jsonify(shared_state)

@app.route("/action", methods=["POST"])
def submit_action():
    data = request.json
    action_idx = data.get("action_index")
    reasoning = data.get("reasoning", "")
    
    if shared_state["status"] == "waiting_for_human":
        if action_idx is not None:
            # Reconstruct the Kaggle choice array
            select_data = shared_state["raw_obs"].get("select", {})
            max_count = select_data.get("maxCount", 1)
            final_choice = [int(action_idx)] * max_count
            
            # Save to dataset
            record = {
                "obs": copy.deepcopy(shared_state["raw_obs"]),
                "heuristic_choice": shared_state["raw_heuristic"],
                "human_choice": final_choice,
                "reasoning": reasoning
            }
            with open(DATASET_FILE, "a") as f:
                f.write(json.dumps(record) + "\n")
                
            shared_state["selected_action"] = final_choice
            shared_state["status"] = "processing"
            agent_event.set()  # Wake up Kaggle agent
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Not waiting for human"})

def interactive_agent(obs_dict):
    import sys
    import traceback
    
    # Kaggle captures stdout/stderr. Restore them so we can see errors.
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    
    try:
        obs_copy = copy.deepcopy(obs_dict)
        heuristic_choice = main.agent(obs_copy)
        
        select_data = obs_dict.get("select")
        if not select_data:
            print("No select data, returning heuristic.", flush=True)
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            return heuristic_choice
        
        options = select_data.get("option", [])
        if not options or len(options) == 1:
            print(f"Only {len(options)} options, returning heuristic.", flush=True)
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            return heuristic_choice
            
        print(f"Agent turn! {len(options)} options available. Pausing for human...", flush=True)
        
        # We have a choice! Push to Flask and wait.
        shared_state["turn"] += 1
        shared_state["raw_obs"] = obs_dict
        shared_state["raw_heuristic"] = heuristic_choice
        shared_state["board"] = build_board_state(obs_dict)
        
        heuristic_idx = heuristic_choice[0] if isinstance(heuristic_choice, list) and heuristic_choice else -1
        
        opts_ui = []
        for i, opt in enumerate(options):
            opts_ui.append({
                "id": i,
                "text": translate_option(opt, obs_dict),
                "is_heuristic": (i == heuristic_idx)
            })
        shared_state["options"] = opts_ui
        shared_state["status"] = "waiting_for_human"
        
        # Wait for frontend to POST action
        agent_event.clear()
        
        # We restore before waiting, so kaggle engine isn't confused, though kaggle engine is blocked.
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        
        print("Waiting on agent_event...", flush=True)
        agent_event.wait()
        print(f"Action received from UI: {shared_state['selected_action']}", flush=True)
        
        return shared_state["selected_action"]
    except Exception as e:
        print(f"CRASH IN AGENT: {e}", flush=True)
        traceback.print_exc()
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        raise e

def run_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("="*60, flush=True)
    print("Starting Interactive Web DAgger Loop...", flush=True)
    print("Open http://localhost:5000 in your browser!", flush=True)
    print("="*60, flush=True)
    
    # Start Flask in daemon thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    
    # Run kaggle engine in main thread
    env = make("cabt")
    import baseline_agent
    
    while True:
        print("Starting new game...", flush=True)
        shared_state["turn"] = 0
        try:
            env.run([interactive_agent, baseline_agent.agent])
            print("Player 0 status:", env.state[0].status, flush=True)
            print("Player 1 status:", env.state[1].status, flush=True)
        except Exception as e:
            print("Error during simulation:", e, flush=True)
            import traceback; traceback.print_exc()
        time.sleep(2)

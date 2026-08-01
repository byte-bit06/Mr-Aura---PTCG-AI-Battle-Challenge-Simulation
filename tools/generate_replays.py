import os
import json
import uuid
import copy
import sys

# Ensure we can import from the root directory and agents/
_root_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _root_dir)
sys.path.insert(0, os.path.join(_root_dir, "agents"))

from kaggle_environments import make
import main
import baseline_agent

_replays_dir = os.path.join(_root_dir, "replays")
os.makedirs(_replays_dir, exist_ok=True)
replay_id = str(uuid.uuid4())[:8]

recorded_decisions = []

def record_agent(obs_dict):
    obs_copy = copy.deepcopy(obs_dict)
    heuristic = main.agent(obs_copy)
    
    select_data = obs_dict.get("select")
    if select_data and select_data.get("option") and len(select_data["option"]) > 1:
        opts_ui = []
        for i, opt in enumerate(select_data["option"]):
            t = str(opt.get("type", "UNKNOWN"))
            detail = ""
            try:
                us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
                if t in ["PLAY", "1", "3"]:
                    idx = opt.get("index", 0)
                    try: detail = f"PLAY CARD: {us['hand'][idx].get('name', '?')}"
                    except: detail = f"PLAY Idx: {idx}"
                elif t in ["ATTACK", "5"]: detail = f"ATTACK: {opt.get('attackId')}"
                elif t in ["ATTACH", "4"]:
                    idx = opt.get("index", 0)
                    try: detail = f"ATTACH ENERGY: {us['hand'][idx].get('name', '?')}"
                    except: detail = f"ATTACH Idx: {idx}"
                elif t in ["RETREAT", "6"]: detail = "RETREAT ACTIVE"
                elif t in ["ABILITY", "2"]: detail = "USE ABILITY"
                else: detail = f"TYPE {t}"
            except:
                detail = f"TYPE {t}"
            
            opts_ui.append({
                "id": i,
                "text": detail,
                "is_heuristic": (i == (heuristic[0] if isinstance(heuristic, list) and heuristic else -1))
            })
            
        recorded_decisions.append({
            "step": obs_dict.get("step", 0),
            "turn": obs_dict.get("current", {}).get("turn", 0) if obs_dict.get("current") else 0,
            "options": opts_ui,
            "raw_obs": obs_dict,
            "raw_heuristic": heuristic
        })
        
    return heuristic

if __name__ == "__main__":
    print(f"Generating replay {replay_id}...")
    env = make("cabt")
    env.run([record_agent, baseline_agent.agent])
    
    print("Game finished. Saving JSON...")
    replay_json = env.toJSON()
    with open(os.path.join(_replays_dir, f"{replay_id}.json"), "w", encoding="utf-8") as f:
        json.dump(replay_json, f)
        
    print("Saving metadata...")
    with open(os.path.join(_replays_dir, f"{replay_id}_meta.json"), "w", encoding="utf-8") as f:
        json.dump(recorded_decisions, f)
        
    print(f"Done! {len(recorded_decisions)} decisions recorded.")

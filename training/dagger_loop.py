import os
import sys
import json
import copy

sys.path.insert(0, '.')
from kaggle_environments import make

import main
import baseline_agent

DATASET_FILE = "dagger_dataset.jsonl"

def _card_str(c):
    if not c: return "[Empty]"
    name = c.get("name", "Unknown")
    hp = c.get("hp", "?")
    energies = len(c.get("energies", []))
    return f"{name} (HP: {hp}, E: {energies})"

def print_board_state(obs_dict):
    current = obs_dict.get("current", {})
    players = current.get("players", [])
    if len(players) < 2: return
    
    my_idx = current.get("yourIndex", 0)
    op_idx = 1 - my_idx
    us = players[my_idx]
    them = players[op_idx]

    print("\n" + "="*60)
    print(f"TURN {current.get('turn', 0)} | Actions this turn: {current.get('turnActionCount', 0)}")
    print("-"*60)
    print("OPPONENT (Baseline)")
    print(f"  Prizes left: {len(them.get('prize', []))} | Hand: {them.get('handCount', 0)} | Deck: {them.get('deckCount', 0)}")
    
    active_op = them.get("active", [])
    if active_op:
        print(f"  Active: {_card_str(active_op[0])}")
    
    bench_op = [c for c in them.get("bench", []) if c]
    if bench_op:
        print("  Bench : " + ", ".join([_card_str(c) for c in bench_op]))

    print("-"*60)
    print("YOU (DAgger Agent)")
    print(f"  Prizes left: {len(us.get('prize', []))} | Hand: {len(us.get('hand', []))} | Deck: {us.get('deckCount', 0)}")
    
    active_us = us.get("active", [])
    if active_us:
        print(f"  Active: {_card_str(active_us[0])}")
    
    bench_us = [c for c in us.get("bench", []) if c]
    if bench_us:
        print("  Bench : " + ", ".join([_card_str(c) for c in bench_us]))
    print("="*60)

def dagger_agent(obs_dict):
    # Kaggle environments captures stdout. We must restore it to print to the terminal.
    import sys
    original_stdout = sys.stdout
    sys.stdout = sys.__stdout__
    
    try:
        # Deepcopy to prevent main.py from mutating the state
        obs_copy = copy.deepcopy(obs_dict)
        
        # Get heuristic recommendation
        heuristic_choice = main.agent(obs_copy)

        select_data = obs_dict.get("select")
        if not select_data:
            # Initial deck submission phase
            sys.stdout = original_stdout
            return heuristic_choice
        
        options = select_data.get("option", [])
        if not options or len(options) == 1:
            # Forced move or no options
            sys.stdout = original_stdout
            return heuristic_choice

        # We have a choice to make. Show UI.
        print_board_state(obs_dict)
        
        print("\nLEGAL OPTIONS:")
        for i, opt in enumerate(options):
            # E.g., {'type': 'ATTACK', 'attackId': 983, ...}
            t = str(opt.get("type", "UNKNOWN"))
            detail = ""
            if t == "PLAY" or t == "1" or t == "3":
                idx = opt.get("index", 0)
                us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
                try:
                    c = us["hand"][idx]
                    detail = f"Card: {c.get('name', '?')}"
                except (IndexError, TypeError):
                    detail = f"Idx: {idx}"
            elif t == "ATTACK" or t == "5":
                detail = f"Attack ID: {opt.get('attackId')}"
            elif t == "ATTACH" or t == "4":
                idx = opt.get("index", 0)
                us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
                try:
                    c = us["hand"][idx]
                    detail = f"Attach {c.get('name', '?')}"
                except (IndexError, TypeError):
                    detail = f"Idx: {idx}"
                
            print(f"  [{i:2d}] {t:10s} {detail}")

        # Heuristic choice is usually a list of indices
        rec_idx = heuristic_choice[0] if isinstance(heuristic_choice, list) and heuristic_choice else -1
        
        print(f"\nAgent's proposed action: [{rec_idx}]")
        sys.stdout.flush()
        
        while True:
            try:
                val = input("Press ENTER to accept, or type option number to override: ").strip()
                if val == "":
                    final_choice = heuristic_choice
                    break
                else:
                    idx = int(val)
                    if 0 <= idx < len(options):
                        final_choice = [idx] * select_data.get("maxCount", 1)
                        break
                    else:
                        print("Invalid option number.")
            except ValueError:
                print("Please enter a valid number or press ENTER.")
                
        # Save the trajectory if it's a real choice
        record = {
            "obs": copy.deepcopy(obs_dict),
            "heuristic_choice": heuristic_choice,
            "human_choice": final_choice
        }
        with open(DATASET_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
            
        sys.stdout = original_stdout
        return final_choice
    except Exception as e:
        import traceback
        sys.stdout = sys.__stdout__
        traceback.print_exc()
        sys.stdout = original_stdout
        raise e


if __name__ == "__main__":
    print("Starting Interactive DAgger Loop...")
    env = make("cabt")
    
    try:
        # Player 0 = DAgger, Player 1 = Baseline
        env.run([dagger_agent, baseline_agent.agent])
        
        r0 = env.state[0].reward
        r1 = env.state[1].reward
        if r0 == 1:
            print("\n*** YOU WON! ***")
        elif r1 == 1:
            print("\n*** YOU LOST! ***")
        else:
            print("\n*** DRAW ***")
            
    except KeyboardInterrupt:
        print("\nDAgger loop interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nSimulation ended with error: {e}")

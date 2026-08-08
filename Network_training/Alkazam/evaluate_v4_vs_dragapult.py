import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIRNAME = "Alakazam_V4"
PRIMARY_NAME = "Alakazam_V4"

_PRIMARY_PATH = os.path.join(_HERE, AGENT_DIRNAME, "main.py")
_AGENT_DIR = os.path.dirname(_PRIMARY_PATH)

_OPPONENTS_DIR = os.path.join(_HERE, "opponents")
if not os.path.exists(_OPPONENTS_DIR):
    _OPPONENTS_DIR = os.path.join(_PARENT, "opponents")
sys.path.append(_OPPONENTS_DIR)

_CG_ROOT = _AGENT_DIR
if _CG_ROOT not in sys.path:
    sys.path.insert(0, _CG_ROOT)

print(f"Agent     : {_PRIMARY_PATH}", flush=True)
print(f"Opponents : {_OPPONENTS_DIR}", flush=True)
print(f"cg engine : {_CG_ROOT}", flush=True)

import cg.api
from kaggle_environments import make

os.chdir(_AGENT_DIR)

_spec = importlib.util.spec_from_file_location("alakazam_v4", _PRIMARY_PATH)
_primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_primary_module)
primary_agent = _primary_module.agent

import dragapult_agent

EVAL_GAMES = int(os.environ.get("EVAL_GAMES", 2))

print(f"\n=======================================================")
print(f" Starting {EVAL_GAMES}-Game Matchup: Alakazam_V4 vs Dragapult ex")
print(f"=======================================================\n", flush=True)

wins = 0
losses = 0
ties = 0

for game_i in range(1, EVAL_GAMES + 1):
    env = make("cabt", debug=True)
    if game_i % 2 != 0:
        agents = [primary_agent, dragapult_agent.agent]
        p_name, o_name = "Alakazam_V4", "Dragapult ex"
        p_idx = 0
    else:
        agents = [dragapult_agent.agent, primary_agent]
        p_name, o_name = "Dragapult ex", "Alakazam_V4"
        p_idx = 1

    match_label = f"{p_name}_vs_{o_name}_{game_i}"
    print(f"Match: {p_name} vs {o_name} ({match_label})", flush=True)

    steps = env.run(agents)
    last_step = steps[-1]
    p_status = last_step[p_idx].get("status")
    o_status = last_step[1 - p_idx].get("status")
    p_reward = last_step[p_idx].get("reward") or 0
    o_reward = last_step[1 - p_idx].get("reward") or 0

    if p_reward > o_reward or (p_status == "DONE" and o_status == "INVALID"):
        winner = "Alakazam_V4"
        wins += 1
    elif o_reward > p_reward or (o_status == "DONE" and p_status == "INVALID"):
        winner = "Dragapult ex"
        losses += 1
    else:
        winner = "Tie"
        ties += 1

    print(f"Winner: {winner}", flush=True)

print(f"\n================ FINAL RESULTS ================")
print(f"Alakazam_V4 vs Dragapult ex: {wins} Wins, {losses} Losses, {ties} Ties ({wins/max(1, wins+losses)*100:.1f}% Win Rate)")
print(f"================================================\n", flush=True)

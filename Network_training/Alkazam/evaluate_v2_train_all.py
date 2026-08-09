import importlib.util
import json
import os
import sys

# ---------------------------------------------------------------------------
# Comprehensive Full-Opponent Evaluator for Alakazam V2 Train
# Opponents: Dragapult ex, Grimmsnarl ex, Wall_V10 V3, Abomasnow, Alakazam, Archaludon, Iono, Lucario, MCTS Lucario
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIRNAME = "Alakazam_V2_train"
PRIMARY_NAME = "Alakazam_V2_train"

_PRIMARY_PATH = os.path.join(_HERE, AGENT_DIRNAME, "main.py")
_AGENT_DIR = os.path.dirname(_PRIMARY_PATH)

_OPPONENTS_DIR = os.path.join(_HERE, "opponents")
if not os.path.exists(_OPPONENTS_DIR):
    _OPPONENTS_DIR = os.path.join(_PARENT, "opponents")
sys.path.append(_OPPONENTS_DIR)

_CG_ROOT = None
for c in [_AGENT_DIR, _HERE, _PARENT]:
    if os.path.exists(os.path.join(c, "cg", "__init__.py")):
        _CG_ROOT = c
        break

if _CG_ROOT is None:
    print("FATAL: cannot find cg/ module directory!")
    sys.exit(1)

sys.path.insert(0, _CG_ROOT)

import cg.api
from kaggle_environments import make

REPLAY_DIR = os.path.join(_HERE, "replays_v2_train")
os.makedirs(REPLAY_DIR, exist_ok=True)

_spec = importlib.util.spec_from_file_location(PRIMARY_NAME, _PRIMARY_PATH)
_primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_primary_module)
primary_agent = _primary_module.agent

opponents = {}

# 1. Dragapult ex
_drag_path = os.path.join(_OPPONENTS_DIR, "dragapult_agent.py")
if os.path.exists(_drag_path):
    _drag_spec = importlib.util.spec_from_file_location("dragapult_agent", _drag_path)
    _drag_module = importlib.util.module_from_spec(_drag_spec)
    _drag_spec.loader.exec_module(_drag_module)
    opponents["Dragapult ex"] = _drag_module.agent

# 2. Grimmsnarl ex
_grimm_pkg = os.path.join(_OPPONENTS_DIR, "grimmsnarl_pkg")
if os.path.exists(_grimm_pkg):
    if _grimm_pkg not in sys.path:
        sys.path.insert(0, _grimm_pkg)
    _old_cwd = os.getcwd()
    try:
        os.chdir(_grimm_pkg)
        import main as _grimm_module
        opponents["Grimmsnarl ex"] = _grimm_module.agent
    finally:
        os.chdir(_old_cwd)

# 3. Wall_V10 V3
_wall_v10_path = os.path.abspath(os.path.join(_HERE, "..", "Wall_V10", "V3", "main.py"))
if os.path.exists(_wall_v10_path):
    _wall_spec = importlib.util.spec_from_file_location("wall_v10_v3", _wall_v10_path)
    _wall_module = importlib.util.module_from_spec(_wall_spec)
    _wall_spec.loader.exec_module(_wall_module)
    opponents["Wall_V10 V3"] = _wall_module.agent

# 4. Standard Opponents
for op_filename in os.listdir(_OPPONENTS_DIR):
    if op_filename.endswith(".py") and op_filename not in ("dragapult_agent.py", "grimmsnarl_agent.py"):
        name_clean = op_filename.replace(".py", "").replace("_agent", "").replace("_", " ").title()
        opp_path = os.path.join(_OPPONENTS_DIR, op_filename)
        try:
            opp_spec = importlib.util.spec_from_file_location(op_filename[:-3], opp_path)
            opp_mod = importlib.util.module_from_spec(opp_spec)
            opp_spec.loader.exec_module(opp_mod)
            if hasattr(opp_mod, "agent"):
                opponents[name_clean] = opp_mod.agent
        except Exception:
            pass


def play_match(env, p1_agent, p2_agent, match_name, p1_name, p2_name):
    steps = env.run([p1_agent, p2_agent])
    html = env.render(mode="html")
    with open(os.path.join(REPLAY_DIR, f"{match_name}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    r1 = steps[-1][0].reward
    r2 = steps[-1][1].reward
    if r1 == 1: winner = p1_name
    elif r2 == 1: winner = p2_name
    else: winner = "Tie"

    p1_taken, p1_conceded = 0, 0
    for idx in range(len(steps) - 1, -1, -1):
        step = steps[idx]
        if isinstance(step, list) and len(step) > 0 and isinstance(step[0], dict):
            obs_dict = step[0].get("observation", {})
            if isinstance(obs_dict, dict) and "current" in obs_dict:
                curr = obs_dict["current"]
                if isinstance(curr, dict) and "players" in curr and len(curr["players"]) >= 2:
                    p0_prz = len(curr["players"][0].get("prize", []))
                    p1_prz = len(curr["players"][1].get("prize", []))
                    p1_taken = 6 - p0_prz
                    p1_conceded = 6 - p1_prz
                    break

    return winner, p1_taken, p1_conceded


def main():
    env = make("cabt", debug=False)
    games_per_matchup = int(os.environ.get("EVAL_GAMES", "10"))

    print(f"\n=======================================================")
    print(f" Starting Comprehensive Evaluation Suite for {PRIMARY_NAME}")
    print(f" Total Opponents: {len(opponents)} | Games per Matchup: {games_per_matchup}")
    print(f"=======================================================\n")

    summary = []
    tot_w, tot_l, tot_t = 0, 0, 0
    grand_prizes_taken, grand_prizes_conceded = 0, 0
    grand_total_games = 0

    for opp_name, opp_agent in opponents.items():
        w, l, t = 0, 0, 0
        opp_prizes_taken, opp_prizes_conceded = 0, 0
        print(f"--- Evaluator: {PRIMARY_NAME} vs {opp_name} ({games_per_matchup} Games) ---", flush=True)

        for g in range(games_per_matchup):
            match_name = f"{PRIMARY_NAME}_vs_{opp_name.replace(' ', '_')}_g{g+1}"
            if g % 2 == 0:
                winner, p1_taken, p1_conceded = play_match(env, primary_agent, opp_agent, match_name, PRIMARY_NAME, opp_name)
                opp_prizes_taken += p1_taken
                opp_prizes_conceded += p1_conceded
            else:
                winner, p2_taken, p2_conceded = play_match(env, opp_agent, primary_agent, match_name, opp_name, PRIMARY_NAME)
                opp_prizes_taken += p2_conceded
                opp_prizes_conceded += p2_taken

            if winner == PRIMARY_NAME: w += 1
            elif winner == opp_name: l += 1
            else: t += 1

        wr = (w / games_per_matchup) * 100.0
        avg_taken = opp_prizes_taken / games_per_matchup
        avg_conc = opp_prizes_conceded / games_per_matchup

        tot_w += w; tot_l += l; tot_t += t
        grand_prizes_taken += opp_prizes_taken
        grand_prizes_conceded += opp_prizes_conceded
        grand_total_games += games_per_matchup

        print(f"  Result vs {opp_name}: {w} Wins, {l} Losses, {t} Ties ({wr:.1f}% Win Rate) | Avg Prizes Taken: {avg_taken:.2f} | Avg Prizes Conceded: {avg_conc:.2f}\n", flush=True)

        summary.append({
            "opponent": opp_name,
            "wins": w, "losses": l, "ties": t, "win_rate": wr,
            "prizes_taken": opp_prizes_taken, "prizes_conceded": opp_prizes_conceded,
            "avg_taken": avg_taken, "avg_conc": avg_conc
        })

    overall_wr = (tot_w / grand_total_games) * 100.0 if grand_total_games > 0 else 0.0
    overall_avg_taken = grand_prizes_taken / grand_total_games if grand_total_games > 0 else 0.0
    overall_avg_conc = grand_prizes_conceded / grand_total_games if grand_total_games > 0 else 0.0

    print("\n" + "=" * 106)
    print(f"{'COMPREHENSIVE EVALUATION SUMMARY FOR ' + PRIMARY_NAME:^106}")
    print("=" * 106)
    print(f"{'Opponent':<24} | {'Wins':<5} | {'Losses':<6} | {'Ties':<4} | {'Win Rate':<9} | {'Prizes Taken (Avg)':<22} | {'Prizes Conceded (Avg)':<22}")
    print("-" * 106)
    for row in summary:
        print(f"{row['opponent']:<24} | {row['wins']:<5} | {row['losses']:<6} | {row['ties']:<4} | {row['win_rate']:>6.1f}%   | {row['prizes_taken']:>3} total ({row['avg_taken']:.2f}/gm)    | {row['prizes_conceded']:>3} total ({row['avg_conc']:.2f}/gm)")
    print("-" * 106)
    print(f"{'OVERALL TOTAL':<24} | {tot_w:<5} | {tot_l:<6} | {tot_t:<4} | {overall_wr:>6.1f}%   | {grand_prizes_taken:>3} total ({overall_avg_taken:.2f}/gm)    | {grand_prizes_conceded:>3} total ({overall_avg_conc:.2f}/gm)")
    print("=" * 106 + "\n")


if __name__ == "__main__":
    main()

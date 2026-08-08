import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Comprehensive Full-Opponent Evaluator for V3 Counter
# Opponents: Dragapult ex, Grimmsnarl ex, Wall_V10 V3, Abomasnow, Archaludon, Iono, Lucario, MCTS Lucario
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIRNAME = "V3 Counter"
PRIMARY_NAME = "V3 Counter"

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

if _CG_ROOT and _CG_ROOT not in sys.path:
    sys.path.insert(0, _CG_ROOT)

print(f"Agent     : {_PRIMARY_PATH}", flush=True)
print(f"Opponents : {_OPPONENTS_DIR}", flush=True)
print(f"cg engine : {_CG_ROOT or 'NOT FOUND'}", flush=True)

try:
    import cg.api  # noqa: F401
except ImportError as e:
    print(f"\nFATAL: cannot import cg.api ({e})", flush=True)
    sys.exit(1)

from kaggle_environments import make

os.chdir(_AGENT_DIR)

_spec = importlib.util.spec_from_file_location("v3_counter", _PRIMARY_PATH)
_primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_primary_module)

primary_agent = _primary_module.agent
primary_name = PRIMARY_NAME

# Load Opponents
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

# 4. Standard Opponent Agents in opponents directory
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
        except Exception as e:
            print(f"Skipping {op_filename}: {e}", flush=True)

REPLAY_DIR = os.path.join(_HERE, "replays_v3_counter_full")
os.makedirs(REPLAY_DIR, exist_ok=True)


def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    steps = env.run([p1_agent, p2_agent])
    r1 = steps[-1][0].reward
    r2 = steps[-1][1].reward

    html = env.render(mode="html")
    with open(os.path.join(REPLAY_DIR, f"{match_name}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    if r1 == 1:
        winner = p1_name
    elif r2 == 1:
        winner = p2_name
    else:
        winner = "Tie"

    return winner


def main():
    env = make("cabt", debug=False)
    games = int(os.environ.get("EVAL_GAMES", "10"))

    print(f"\n=======================================================", flush=True)
    print(f" Starting Comprehensive Evaluation Suite for {primary_name}")
    print(f" Total Opponents: {len(opponents)} | Games per Matchup: {games}")
    print(f"=======================================================\n", flush=True)

    summary_table = []

    for opp_name, opp_agent in opponents.items():
        results = {"win": 0, "loss": 0, "tie": 0}
        print(f"--- Evaluator: {primary_name} vs {opp_name} ({games} Games) ---", flush=True)

        for i in range(games):
            if i % 2 == 0:
                winner = play_match(env, primary_name, primary_agent, opp_name,
                                    opp_agent, f"{primary_name}_vs_{opp_name}_{i+1}")
            else:
                winner = play_match(env, opp_name, opp_agent, primary_name,
                                    primary_agent, f"{opp_name}_vs_{primary_name}_{i+1}")

            if winner == primary_name:
                results["win"] += 1
            elif winner == opp_name:
                results["loss"] += 1
            else:
                results["tie"] += 1

        w = results["win"]
        l = results["loss"]
        t = results["tie"]
        pct = (w / games) * 100.0 if games > 0 else 0.0
        summary_table.append((opp_name, w, l, t, pct))

        print(f"  Result vs {opp_name}: {w} Wins, {l} Losses, {t} Ties ({pct:.1f}% Win Rate)\n", flush=True)

    print(f"\n=======================================================", flush=True)
    print(f"            COMPREHENSIVE EVALUATION SUMMARY           ", flush=True)
    print(f"=======================================================", flush=True)
    print(f"{'Opponent':<25} | {'Wins':<5} | {'Losses':<6} | {'Ties':<5} | {'Win Rate':<8}", flush=True)
    print(f"-" * 60, flush=True)
    
    total_w, total_l, total_t = 0, 0, 0
    for opp_name, w, l, t, pct in summary_table:
        total_w += w
        total_l += l
        total_t += t
        print(f"{opp_name:<25} | {w:<5} | {l:<6} | {t:<5} | {pct:>6.1f}%", flush=True)

    total_games = total_w + total_l + total_t
    overall_pct = (total_w / total_games) * 100.0 if total_games > 0 else 0.0
    print(f"-" * 60, flush=True)
    print(f"{'OVERALL TOTAL':<25} | {total_w:<5} | {total_l:<6} | {total_t:<5} | {overall_pct:>6.1f}%\n", flush=True)


if __name__ == "__main__":
    main()

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Comprehensive Full-Opponent Evaluator for Alakazam V5
# Opponents: Dragapult ex, Grimmsnarl ex, Wall_V10 V3, Abomasnow, Archaludon, Iono, Lucario, MCTS Lucario
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIRNAME = "Alakazam_V5"
PRIMARY_NAME = "Alakazam_V5"

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

_spec = importlib.util.spec_from_file_location("alakazam_v5", _PRIMARY_PATH)
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

REPLAY_DIR = os.path.join(_HERE, "replays_v5_full")
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

    # Extract final prize state for detailed prize statistics
    p1_taken, p1_conceded = 0, 0
    for st in reversed(steps):
        s0 = st[0]
        if isinstance(s0, dict) and s0.get("observation") and isinstance(s0["observation"], dict):
            raw_obs = s0["observation"].get("obs")
            if isinstance(raw_obs, str) and len(raw_obs) > 10:
                try:
                    obs0 = cg.api.json_to_dataclass(json.loads(raw_obs), cg.api.GameState)
                    my_i = obs0.current.yourIndex
                    op_i = obs0.current.opIndex
                    p1_prizes_rem = len(obs0.players[my_i].prize)
                    p2_prizes_rem = len(obs0.players[op_i].prize)
                    p1_taken = 6 - p1_prizes_rem
                    p1_conceded = 6 - p2_prizes_rem
                    break
                except Exception:
                    pass

    return winner, p1_taken, p1_conceded


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
        total_prizes_taken = 0
        total_prizes_conceded = 0
        print(f"--- Evaluator: {primary_name} vs {opp_name} ({games} Games) ---", flush=True)

        for i in range(games):
            if i % 2 == 0:
                winner, p_taken, p_conc = play_match(env, primary_name, primary_agent, opp_name,
                                                     opp_agent, f"{primary_name}_vs_{opp_name}_{i+1}")
            else:
                winner, p_conc, p_taken = play_match(env, opp_name, opp_agent, primary_name,
                                                     primary_agent, f"{opp_name}_vs_{primary_name}_{i+1}")

            if winner == primary_name:
                results["win"] += 1
            elif winner == opp_name:
                results["loss"] += 1
            else:
                results["tie"] += 1

            total_prizes_taken += p_taken
            total_prizes_conceded += p_conc

        w = results["win"]
        l = results["loss"]
        t = results["tie"]
        pct = (w / games) * 100.0 if games > 0 else 0.0
        avg_taken = total_prizes_taken / games if games > 0 else 0.0
        avg_conc = total_prizes_conceded / games if games > 0 else 0.0

        summary_table.append((opp_name, w, l, t, pct, total_prizes_taken, total_prizes_conceded, avg_taken, avg_conc))

        print(f"  Result vs {opp_name}: {w} Wins, {l} Losses, {t} Ties ({pct:.1f}% Win Rate) | Avg Prizes Taken: {avg_taken:.2f} | Avg Prizes Conceded: {avg_conc:.2f}\n", flush=True)

    print(f"\n==========================================================================================================", flush=True)
    print(f"                               COMPREHENSIVE EVALUATION SUMMARY (WITH PRIZES)                             ", flush=True)
    print(f"==========================================================================================================", flush=True)
    print(f"{'Opponent':<23} | {'Wins':<4} | {'Losses':<6} | {'Ties':<4} | {'Win Rate':<8} | {'Prizes Taken (Avg)':<18} | {'Prizes Conceded (Avg)':<21}", flush=True)
    print(f"-" * 95, flush=True)
    
    total_w, total_l, total_t = 0, 0, 0
    sum_taken, sum_conc = 0, 0
    for opp_name, w, l, t, pct, p_taken, p_conc, avg_t, avg_c in summary_table:
        total_w += w
        total_l += l
        total_t += t
        sum_taken += p_taken
        sum_conc += p_conc
        print(f"{opp_name:<23} | {w:<4} | {l:<6} | {t:<4} | {pct:>6.1f}%  | {p_taken:>3d} total ({avg_t:>4.2f}/gm)    | {p_conc:>3d} total ({avg_c:>4.2f}/gm)", flush=True)

    total_games = total_w + total_l + total_t
    overall_pct = (total_w / total_games) * 100.0 if total_games > 0 else 0.0
    overall_avg_t = sum_taken / total_games if total_games > 0 else 0.0
    overall_avg_c = sum_conc / total_games if total_games > 0 else 0.0

    print(f"-" * 95, flush=True)
    print(f"{'OVERALL TOTAL':<23} | {total_w:<4} | {total_l:<6} | {total_t:<4} | {overall_pct:>6.1f}%  | {sum_taken:>3d} total ({overall_avg_t:>4.2f}/gm)    | {sum_conc:>3d} total ({overall_avg_c:>4.2f}/gm)\n", flush=True)


if __name__ == "__main__":
    main()

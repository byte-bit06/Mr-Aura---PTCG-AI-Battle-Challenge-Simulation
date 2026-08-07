import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Path resolution — dedicated evaluator for Alakazam V2 vs Grimmsnarl ex
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIRNAME = "Alakazam_V2"
PRIMARY_NAME = "Alakazam_V2"

_PRIMARY_PATH = os.path.join(_HERE, AGENT_DIRNAME, "main.py")
if not os.path.exists(_PRIMARY_PATH):
    _PRIMARY_PATH = os.path.join(_HERE, "main.py")

_AGENT_DIR = os.path.dirname(_PRIMARY_PATH)

_OPPONENTS_DIR = os.path.join(_HERE, "opponents")
if not os.path.exists(_OPPONENTS_DIR):
    _OPPONENTS_DIR = os.path.join(_PARENT, "opponents")
sys.path.append(_OPPONENTS_DIR)

# --- the cg engine ---------------------------------------------------------
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

_spec = importlib.util.spec_from_file_location("alakazam_v2", _PRIMARY_PATH)
_primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_primary_module)

primary_agent = _primary_module.agent
primary_name = PRIMARY_NAME

# --- Load Grimmsnarl ex agent from grimmsnarl_pkg -------------------------
_grimm_pkg = os.path.join(_OPPONENTS_DIR, "grimmsnarl_pkg")
if _grimm_pkg not in sys.path:
    sys.path.insert(0, _grimm_pkg)

_old_cwd = os.getcwd()
try:
    os.chdir(_grimm_pkg)
    import main as _grimm_module
    _grimm_agent = _grimm_module.agent
finally:
    os.chdir(_old_cwd)

REPLAY_DIR = os.path.join(_HERE, "replays_grimmsnarl_v2")
os.makedirs(REPLAY_DIR, exist_ok=True)


def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    print(f"Match: {p1_name} vs {p2_name} ({match_name})", flush=True)
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

    print(f"Winner: {winner}", flush=True)
    return winner


def main():
    env = make("cabt", debug=False)
    results = {"win": 0, "loss": 0, "tie": 0}
    games = int(os.environ.get("EVAL_GAMES", "10"))

    print(f"\n=======================================================", flush=True)
    print(f" Starting {games}-Game Matchup: {primary_name} vs Grimmsnarl ex", flush=True)
    print(f"=======================================================\n", flush=True)

    for i in range(games):
        if i % 2 == 0:
            winner = play_match(env, primary_name, primary_agent, "Grimmsnarl ex",
                                _grimm_agent, f"{primary_name}_vs_Grimmsnarl_{i+1}")
        else:
            winner = play_match(env, "Grimmsnarl ex", _grimm_agent, primary_name,
                                primary_agent, f"Grimmsnarl_vs_{primary_name}_{i+1}")

        if winner == primary_name:
            results["win"] += 1
        elif winner == "Grimmsnarl ex":
            results["loss"] += 1
        else:
            results["tie"] += 1

    total = games
    w = results["win"]
    l = results["loss"]
    t = results["tie"]
    pct = (w / total) * 100.0 if total > 0 else 0.0

    print(f"\n================ FINAL RESULTS ================", flush=True)
    print(f"{primary_name} vs Grimmsnarl ex: {w} Wins, {l} Losses, {t} Ties ({pct:.1f}% Win Rate)", flush=True)
    print(f"================================================\n", flush=True)


if __name__ == "__main__":
    main()

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Path resolution — nothing hardcoded, so moving this file does not break it.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
_GRANDPARENT = os.path.dirname(_PARENT)

AGENT_DIRNAME = "Alakazam_Courage"
BUILDER = "codex_sol_eclipse_alakazam.py"
PRIMARY_NAME = "Alakazam_V1"


def _first_existing(paths, what, fatal=True):
    for p in paths:
        if os.path.exists(p):
            return p
    print(f"{'ERROR' if fatal else 'note'}: could not locate {what}. Tried:", flush=True)
    for p in paths:
        print(f"   {p}", flush=True)
    if fatal:
        sys.exit(1)
    return None


# --- the agent, extracting it from the notebook builder if needed ----------
_PRIMARY_PATH = _first_existing([
    os.path.join(_HERE, AGENT_DIRNAME, "main.py"),
    os.path.join(_HERE, "main.py"),
    os.path.join(_PARENT, AGENT_DIRNAME, "main.py"),
], "the Alakazam main.py", fatal=False)

if _PRIMARY_PATH is None:
    builder = _first_existing([
        os.path.join(_HERE, BUILDER),
        os.path.join(_PARENT, BUILDER),
    ], f"{BUILDER} (to extract the agent from)")
    print(f"main.py not found - extracting from {builder}", flush=True)
    sys.path.insert(0, _HERE)
    from build_alakazam_agent import build
    if build(builder, os.path.join(_HERE, AGENT_DIRNAME)) != 0:
        sys.exit(1)
    _PRIMARY_PATH = os.path.join(_HERE, AGENT_DIRNAME, "main.py")

_AGENT_DIR = os.path.dirname(_PRIMARY_PATH)

# --- opponents -------------------------------------------------------------
_OPPONENTS_DIR = _first_existing([
    os.path.join(_HERE, "opponents"),
    os.path.join(_PARENT, "opponents"),
    os.path.join(_GRANDPARENT, "opponents"),
], "the 'opponents' folder")
sys.path.append(_OPPONENTS_DIR)


# --- the cg engine ---------------------------------------------------------
# sys.path[0] is the SCRIPT's directory, not the working directory, so cg can
# fall off the path just by moving this file. Walk up until we find it.
def _find_package_root(pkg, start, levels=6):
    d = start
    for _ in range(levels):
        for marker in ("__init__.py", "api.py"):
            if os.path.exists(os.path.join(d, pkg, marker)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


_CG_ROOT = None
# Check if cg package root is already in _AGENT_DIR or parent directories
candidates_to_check = [_AGENT_DIR, _HERE, _PARENT, _GRANDPARENT]
for c in candidates_to_check:
    if os.path.exists(os.path.join(c, "cg", "__init__.py")):
        _CG_ROOT = c
        break

if not _CG_ROOT:
    _CG_ROOT = _find_package_root("cg", _HERE)

if _CG_ROOT and _CG_ROOT not in sys.path:
    sys.path.insert(0, _CG_ROOT)

print(f"Agent     : {_PRIMARY_PATH}", flush=True)
print(f"Opponents : {_OPPONENTS_DIR}", flush=True)
print(f"cg engine : {_CG_ROOT or 'NOT FOUND'}", flush=True)

try:
    import cg.api  # noqa: F401
except ImportError as e:
    print(f"\nFATAL: cannot import cg.api ({e})", flush=True)
    print("Both the agent and the opponents need it.", flush=True)
    print(f"Searched upward from: {_HERE}", flush=True)
    sys.exit(1)

from kaggle_environments import make

# The agent reads deck.csv relative to its own folder or the cwd, so run from
# the agent directory to be safe.
os.chdir(_AGENT_DIR)

_spec = importlib.util.spec_from_file_location("alakazam_courage", _PRIMARY_PATH)
_primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_primary_module)

# --- battle logging, by wrapping rather than patching ----------------------
sys.path.insert(0, _HERE)
BATTLE_LOG = None
try:
    from agent_wrapper import wrap_agent, build_card_index
    primary_agent, BATTLE_LOG = wrap_agent(
        _primary_module.agent,
        profile="alakazam",
        card_index=build_card_index(),
        path=os.path.join(_HERE, "battle_log.txt"),
        keep_games=int(os.environ.get("DRAGAPULT_LOG_GAMES", "6")),
    )
    print(f"Battle log: {BATTLE_LOG.path}", flush=True)
except Exception as e:
    primary_agent = _primary_module.agent
    print(f"Battle log: DISABLED ({e})", flush=True)

primary_name = PRIMARY_NAME


def record_battle_result(primary_seat, winner_name):
    """Tell the logger who won, so games stop closing out as UNKNOWN."""
    if BATTLE_LOG is None:
        return
    try:
        if winner_name == primary_name:
            BATTLE_LOG.record_result(primary_seat)
        elif winner_name == "Tie":
            BATTLE_LOG.record_result(None)
        else:
            BATTLE_LOG.record_result(1 - primary_seat)
    except Exception as e:
        print(f"  (battle log result failed: {e})", flush=True)


import lucario_agent
import iono_agent
import dragapult_agent
import abomasnow_agent
import mcts_lucario_agent
import archaludon_cinderace_agent
import alakazam_agent

opponents = {
    "Alakazam ex V21": alakazam_agent.agent,
    "Lucario ex": lucario_agent.agent,
    "Iono Deck": iono_agent.agent,
    "Dragapult ex": dragapult_agent.agent,
    "Abomasnow ex": abomasnow_agent.agent,
    "MCTS Lucario": mcts_lucario_agent.agent,
    "Archaludon Cinderace": archaludon_cinderace_agent.agent,
}

REPLAY_DIR = os.path.join(_HERE, "replays_alakazam")
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
    results = {}
    games = int(os.environ.get("EVAL_GAMES", "10"))

    print(f"Starting evaluations for {primary_name}...", flush=True)

    for opp_name, opp_agent in opponents.items():
        results[opp_name] = {"win": 0, "loss": 0, "tie": 0}
        for i in range(games):
            clean = opp_name.replace(" ", "")
            if i % 2 == 0:
                primary_seat = 0
                winner = play_match(env, primary_name, primary_agent, opp_name,
                                    opp_agent, f"{primary_name}_vs_{clean}_{i+1}")
            else:
                primary_seat = 1
                winner = play_match(env, opp_name, opp_agent, primary_name,
                                    primary_agent, f"{clean}_vs_{primary_name}_{i+1}")

            record_battle_result(primary_seat, winner)

            if winner == primary_name:
                results[opp_name]["win"] += 1
            elif winner == opp_name:
                results[opp_name]["loss"] += 1
            else:
                results[opp_name]["tie"] += 1

    print(f"\n=== FINAL {primary_name} RESULTS ===", flush=True)
    total_wins = total_losses = 0
    for opp_name, st in results.items():
        print(f"vs {opp_name}: {st['win']} Wins, {st['loss']} Losses, {st['tie']} Ties",
              flush=True)
        total_wins += st["win"]
        total_losses += st["loss"]

    print(f"\nOverall Win Rate: "
          f"{(total_wins / max(1, total_wins + total_losses)) * 100:.1f}%")

    if BATTLE_LOG is not None:
        BATTLE_LOG.flush()
        print(f"\nBattle transcript: {BATTLE_LOG.path}", flush=True)


if __name__ == "__main__":
    main()

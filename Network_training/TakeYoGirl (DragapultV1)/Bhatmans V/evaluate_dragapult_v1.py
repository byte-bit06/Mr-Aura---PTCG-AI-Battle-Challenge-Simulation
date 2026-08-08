import importlib.util
import os
import sys
import os
os.environ["DRAGAPULT_DISABLE_SEARCH"] = "1"   # comment out to re-enable search

# ---------------------------------------------------------------------------
# Path resolution
#
# This script has lived in two places (Network_training/ and inside the agent
# folder), so nothing here hardcodes a folder name. Both main.py and the
# opponents package are located by searching a short candidate list relative
# to this file, and every output path is anchored to this file rather than to
# the current working directory.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
_GRANDPARENT = os.path.dirname(_PARENT)

_AGENT_DIRNAME = 'TakeYoGirl (DragapultV1)'


def _first_existing(paths, what):
    for p in paths:
        if os.path.exists(p):
            return p
    print(f'ERROR: could not locate {what}. Tried:', flush=True)
    for p in paths:
        print(f'   {p}', flush=True)
    sys.exit(1)


# --- the agent under test --------------------------------------------------
_PRIMARY_PATH = _first_existing([
    os.path.join(_HERE, 'main.py'),                      # script sits beside main.py
    os.path.join(_HERE, _AGENT_DIRNAME, 'main.py'),      # script sits one level above
    os.path.join(_PARENT, _AGENT_DIRNAME, 'main.py'),
], 'main.py')
_AGENT_DIR = os.path.dirname(_PRIMARY_PATH)

# --- the opponents package -------------------------------------------------
_OPPONENTS_DIR = _first_existing([
    os.path.join(_HERE, 'opponents'),
    os.path.join(_PARENT, 'opponents'),
    os.path.join(_GRANDPARENT, 'opponents'),
], "the 'opponents' folder")
sys.path.append(_OPPONENTS_DIR)


# --- the cg engine package -------------------------------------------------
# When you run `python foo.py`, sys.path[0] is the *script's* directory, not
# the working directory. Moving this script into the agent folder therefore
# dropped whatever directory contains `cg` off the import path. Walk up from
# here until we find it, and put it on the path before anything imports it.
def _find_package_root(pkg, start, levels=6):
    d = start
    for _ in range(levels):
        for marker in ('__init__.py', 'api.py'):
            if os.path.exists(os.path.join(d, pkg, marker)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


_CG_ROOT = None
try:
    import cg  # already importable (installed, or PYTHONPATH is set)
    _CG_ROOT = '(already on path)'
except ImportError:
    _CG_ROOT = _find_package_root('cg', _HERE)
    if _CG_ROOT:
        sys.path.insert(0, _CG_ROOT)

print(f'Agent     : {_PRIMARY_PATH}', flush=True)
print(f'Opponents : {_OPPONENTS_DIR}', flush=True)
print(f'cg engine : {_CG_ROOT or "NOT FOUND"}', flush=True)

try:
    import cg.api  # noqa: F401
except ImportError as e:
    print('', flush=True)
    print(f'FATAL: cannot import cg.api ({e})', flush=True)
    print('Without it the agent silently degrades to returning [0] for every', flush=True)
    print('decision, and the opponent agents will not import at all.', flush=True)
    print(f'Searched upward from: {_HERE}', flush=True)
    print('Fix: run from the directory containing cg/, or set PYTHONPATH to it.', flush=True)
    sys.exit(1)

from kaggle_environments import make

_spec = importlib.util.spec_from_file_location('takeyogirl_dragapult_v1', _PRIMARY_PATH)
_primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_primary_module)

primary_agent = _primary_module.agent
primary_name = "TakeYoGirl_DragapultV1"

# --- battle log wiring -----------------------------------------------------
# The logger lives inside the agent module, so its transcript is written next
# to main.py, NOT next to this script or the working directory.
BATTLE_LOG = getattr(_primary_module, 'BATTLE_LOG', None)
if BATTLE_LOG is not None:
    print(f'Battle log: {BATTLE_LOG.path}', flush=True)
else:
    print('Battle log: NOT WIRED', flush=True)
    # Say *why*, so this isn't a guessing game.
    if not os.path.exists(os.path.join(_AGENT_DIR, 'battle_log.py')):
        print(f'   battle_log.py is not in {_AGENT_DIR}', flush=True)
    elif 'BATTLE_LOG' not in open(_PRIMARY_PATH, encoding='utf-8',
                                 errors='replace').read():
        print('   main.py has no BATTLE_LOG block — run patch_main.py '
              'in the agent directory', flush=True)
    else:
        print('   main.py contains a BATTLE_LOG block but the module does not '
              'expose it —', flush=True)
        print('   the block was probably inserted inside a function or after an '
              'early return.', flush=True)
        print('   Search main.py for "BATTLE_LOG = " and check it sits at module '
              'level.', flush=True)


def record_battle_result(primary_seat, winner_name):
    """Tell the logger who won, so games stop closing out as UNKNOWN."""
    if BATTLE_LOG is None:
        return
    try:
        if winner_name == primary_name:
            BATTLE_LOG.record_result(primary_seat)
        elif winner_name == 'Tie':
            BATTLE_LOG.record_result(None)
        else:
            BATTLE_LOG.record_result(1 - primary_seat)
    except Exception as e:
        print(f'  (battle log result failed: {e})', flush=True)


import lucario_agent
import iono_agent
import dragapult_agent
import abomasnow_agent
import mcts_lucario_agent
import archaludon_cinderace_agent
import alakazam_agent

opponents = {
    'Alakazam ex V21': alakazam_agent.agent,
    'Lucario ex': lucario_agent.agent,
    'Iono Deck': iono_agent.agent,
    'Dragapult ex': dragapult_agent.agent,
    'Abomasnow ex': abomasnow_agent.agent,
    'MCTS Lucario': mcts_lucario_agent.agent,
    'Archaludon Cinderace': archaludon_cinderace_agent.agent,
}

REPLAY_DIR = os.path.join(_HERE, 'replays')
os.makedirs(REPLAY_DIR, exist_ok=True)


def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    print(f'Match: {p1_name} vs {p2_name} ({match_name})', flush=True)
    steps = env.run([p1_agent, p2_agent])
    r1 = steps[-1][0].reward
    r2 = steps[-1][1].reward

    html = env.render(mode='html')
    with open(os.path.join(REPLAY_DIR, f'{match_name}.html'), 'w', encoding='utf-8') as f:
        f.write(html)

    if r1 == 1:
        winner = p1_name
    elif r2 == 1:
        winner = p2_name
    else:
        winner = 'Tie'

    print(f'Winner: {winner}', flush=True)
    return winner


def main():
    env = make('cabt', debug=False)
    results = {}

    print(f'Starting evaluations for {primary_name}...', flush=True)

    for opp_name, opp_agent in opponents.items():
        results[opp_name] = {'win': 0, 'loss': 0, 'tie': 0}
        for i in range(10):
            clean_name = opp_name.replace(' ', '')

            if i % 2 == 0:
                primary_seat = 0
                winner = play_match(env, primary_name, primary_agent, opp_name, opp_agent,
                                    f'{primary_name}_vs_{clean_name}_{i+1}')
            else:
                primary_seat = 1
                winner = play_match(env, opp_name, opp_agent, primary_name, primary_agent,
                                    f'{clean_name}_vs_{primary_name}_{i+1}')

            record_battle_result(primary_seat, winner)

            if winner == primary_name:
                results[opp_name]['win'] += 1
            elif winner == opp_name:
                results[opp_name]['loss'] += 1
            else:
                results[opp_name]['tie'] += 1

    print(f'\n=== FINAL {primary_name} RESULTS ===', flush=True)
    total_wins = 0
    total_losses = 0
    for opp_name, stats in results.items():
        print(f"vs {opp_name}: {stats['win']} Wins, {stats['loss']} Losses, {stats['tie']} Ties",
              flush=True)
        total_wins += stats['win']
        total_losses += stats['loss']

    print(f"\nOverall Win Rate: {(total_wins / max(1, total_wins + total_losses)) * 100:.1f}%")

    if BATTLE_LOG is not None:
        BATTLE_LOG.flush()
        print(f'\nBattle transcript: {BATTLE_LOG.path}', flush=True)


if __name__ == '__main__':
    main()

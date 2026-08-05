"""
train_genetic_dragapult.py — genetic weight tuning for TakeYoGirl (DragapultV1).

Same pattern as train_genetic.py (the tuner already used for the Wall_* decks
in this repo): take the current best weights, spawn a population of mutants
(each numeric weight nudged +/- mutation_percent), play every mutant through
MATCHES_PER_MUTANT games against the real opponent pool in parallel, keep
whichever mutant won the most as the next generation's search base, repeat
until MAX_HOURS elapses.

Three files, all in the TakeYoGirl (DragapultV1) folder:
  dragapult_weights.json        best-ever weights found across every run so
                                 far. This is what main.py actually loads for
                                 real play, and what a fresh run resumes from
                                 if dragapult_search_state.json is missing —
                                 it only ever improves, never regresses, safe
                                 to use at any point mid-run or after a crash.
  dragapult_search_state.json   the GA's current search base (last
                                 generation's pick, not necessarily the best —
                                 this is exploration state, not a result).
                                 A fresh run resumes mutation from here so
                                 running this again tomorrow night continues
                                 the same search instead of restarting cold.
  training_progress.json        generation count, win rates, elapsed/remaining
                                 time, games played — check this for progress
"""

import copy
import importlib.util
import json
import multiprocessing
import os
import random
import sys
import time

from kaggle_environments import make

_HERE = os.path.dirname(os.path.abspath(__file__))
_PRIMARY_PATH = os.path.join(_HERE, "TakeYoGirl (DragapultV1)", "main.py")

sys.path.append(os.path.join(_HERE, "opponents"))

ENV_NAME = "cabt"

# Time-bounded, not generation-bounded — per-generation wall time isn't
# precisely predictable in advance, so GENERATIONS is just a hard safety
# ceiling that should never actually be reached.
MAX_HOURS = 8.0
GENERATIONS = 100000

POPULATION_SIZE = 16          # matches this machine's 16 cores: one full
                               # parallel wave of mutants per generation
MATCHES_PER_MUTANT = 20       # same signal quality as the existing Wall_* tuner
MUTATION_RATE = 0.25
MUTATION_PERCENT = 0.20

_DIR = os.path.join(_HERE, "TakeYoGirl (DragapultV1)")
WEIGHTS_FILE = os.path.join(_DIR, "dragapult_weights.json")           # best-ever; what main.py loads for real play
SEARCH_STATE_FILE = os.path.join(_DIR, "dragapult_search_state.json")  # GA's own exploration trail, resumed across runs
PROGRESS_FILE = os.path.join(_DIR, "training_progress.json")


def _load_primary_module():
    spec = importlib.util.spec_from_file_location("takeyogirl_dragapult_v1", _PRIMARY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_search_seed():
    """Resume point for a fresh run: prefer the GA's own last search state
    (continues exploration momentum across nights) over the best-ever file
    (which main.py already loads by default), over hardcoded defaults."""
    if os.path.exists(SEARCH_STATE_FILE):
        try:
            with open(SEARCH_STATE_FILE) as f:
                data = json.load(f)
            merged = dict(_primary_module.W)
            merged.update({k: v for k, v in data.items() if k in merged})
            return merged
        except Exception:
            pass
    return dict(_primary_module.W)


# Loaded once at import time. _primary_module.W already reflects
# dragapult_weights.json (best-ever) via main.py's own loader; _BASE_WEIGHTS
# is what generation 1 actually mutates from, preferring search state if any.
_primary_module = _load_primary_module()
_BASE_WEIGHTS = _load_search_seed()


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def mutate(weights, mutation_rate=MUTATION_RATE, mutation_percent=MUTATION_PERCENT):
    mutated = copy.deepcopy(weights)
    for key in mutated:
        if random.random() < mutation_rate:
            current = mutated[key]
            if current == 0:
                mutated[key] += random.uniform(-0.1, 0.1)
            else:
                mutated[key] += current * random.uniform(-mutation_percent, mutation_percent)
            mutated[key] = max(0.0, min(1.5, mutated[key]))
    return mutated


def _opponent_pool():
    import lucario_agent
    import iono_agent
    import dragapult_agent
    import abomasnow_agent
    import mcts_lucario_agent
    import archaludon_cinderace_agent
    import alakazam_agent
    return [
        lucario_agent.agent, iono_agent.agent, dragapult_agent.agent,
        abomasnow_agent.agent, mcts_lucario_agent.agent,
        archaludon_cinderace_agent.agent, alakazam_agent.agent,
    ]


def evaluate_mutant(mutant_weights):
    """Runs in its own worker process (multiprocessing re-imports this module
    fresh per worker), so mutating the module-level W here is isolated from
    every other worker's mutant."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

    wins = 0
    try:
        mod = _load_primary_module()
        mod.W.clear()
        mod.W.update(mutant_weights)
        agent_closure = mod.agent

        opponents = _opponent_pool()
        env = make(ENV_NAME, debug=False)
        for match_idx in range(MATCHES_PER_MUTANT):
            opponent = opponents[match_idx % len(opponents)]
            if random.random() < 0.5:
                steps = env.run([agent_closure, opponent])
                final_reward = steps[-1][0].reward
            else:
                steps = env.run([opponent, agent_closure])
                final_reward = steps[-1][1].reward
            if final_reward == 1:
                wins += 1
    except Exception as e:
        old_stderr.write(f"\nCRASH in mutant evaluation: {e}\n")
        wins = 0  # penalize crashes heavily
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    win_rate = wins / MATCHES_PER_MUTANT
    print(f"[Worker] Mutant evaluated -> Win Rate: {win_rate*100:.1f}%", flush=True)
    return win_rate


def _write_progress(generation, games_played, start_time, gen_win_rate, best_ever_rate, best_ever_gen):
    elapsed = time.time() - start_time
    per_gen = elapsed / max(1, generation)
    remaining = max(0.0, MAX_HOURS * 3600 - elapsed)
    save_json(PROGRESS_FILE, {
        "generation": generation,
        "games_played": games_played,
        "elapsed_hours": round(elapsed / 3600, 3),
        "target_hours": MAX_HOURS,
        "estimated_remaining_hours": round(remaining / 3600, 3),
        "seconds_per_generation_avg": round(per_gen, 1),
        "this_generation_win_rate_pct": round(gen_win_rate * 100, 1),
        "best_ever_win_rate_pct": round(best_ever_rate * 100, 1),
        "best_ever_generation": best_ever_gen,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


def _load_recorded_best():
    """The bar a fresh run must clear before it's allowed to overwrite
    dragapult_weights.json — without this, a cold restart's noisy first
    generation could stomp a genuinely better result a previous night found,
    since main.py's W only tells us the weights, not the win rate they
    earned."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                data = json.load(f)
            return data.get("best_ever_win_rate_pct", 0.0) / 100.0
        except Exception:
            pass
    return 0.0


def main():
    start_time = time.time()
    deadline = start_time + MAX_HOURS * 3600
    print(f"Starting genetic tuning: up to {MAX_HOURS}h, {POPULATION_SIZE} population x "
          f"{MATCHES_PER_MUTANT} matches/generation ({POPULATION_SIZE*MATCHES_PER_MUTANT} games/generation)", flush=True)

    base_weights = dict(_BASE_WEIGHTS)
    recorded_best_rate = _load_recorded_best()
    best_ever_weights, best_ever_rate, best_ever_gen = dict(_primary_module.W), recorded_best_rate, 0
    print(f"Resuming — bar to beat before dragapult_weights.json updates: {recorded_best_rate*100:.1f}%", flush=True)
    games_played = 0

    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())

    generation = 0
    try:
        while generation < GENERATIONS and time.time() < deadline:
            generation += 1
            print(f"\n--- Generation {generation} ({(time.time()-start_time)/3600:.2f}h elapsed) ---", flush=True)
            population = [base_weights] + [mutate(base_weights) for _ in range(POPULATION_SIZE - 1)]

            win_rates = pool.map(evaluate_mutant, population)
            games_played += POPULATION_SIZE * MATCHES_PER_MUTANT

            gen_best_rate, gen_best_weights = -1.0, base_weights
            for i, win_rate in enumerate(win_rates):
                if win_rate > gen_best_rate:
                    gen_best_rate, gen_best_weights = win_rate, population[i]
                if win_rate > best_ever_rate:
                    best_ever_rate, best_ever_weights, best_ever_gen = win_rate, population[i], generation

            print(f"Generation {generation} complete. This-gen best: {gen_best_rate*100:.1f}% | "
                  f"All-time best: {best_ever_rate*100:.1f}% (gen {best_ever_gen})", flush=True)

            base_weights = gen_best_weights
            save_json(SEARCH_STATE_FILE, base_weights)   # exploration trail — always updates
            save_json(WEIGHTS_FILE, best_ever_weights)   # real-play file — only ever improves
            _write_progress(generation, games_played, start_time, gen_best_rate, best_ever_rate, best_ever_gen)
    finally:
        pool.close()
        pool.join()

    print(f"\nGenetic tuning complete after {generation} generations / {games_played} games "
          f"({(time.time()-start_time)/3600:.2f}h). Best win rate: {best_ever_rate*100:.1f}% "
          f"(generation {best_ever_gen}). Saved to {WEIGHTS_FILE}", flush=True)


if __name__ == "__main__":
    main()

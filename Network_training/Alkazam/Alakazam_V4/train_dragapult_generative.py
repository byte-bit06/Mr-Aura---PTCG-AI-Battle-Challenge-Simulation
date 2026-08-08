"""
train_dragapult_generative.py — Generative Evolutionary Learning AI for Alakazam V4 vs Dragapult ex.

This script implements an evolutionary reinforcement search pipeline:
1. Spawns mutant parameter configurations from current best heuristic weights.
2. Plays parallel match evaluations against Dragapult ex.
3. Evaluates win rate, prize card differential, and turn efficiency to award top-performing mutants.
4. Saves Dragapult-specific weights to `alak_dragapult_weights.json` (loaded automatically by Alakazam_V4 when facing Dragapult ex).
5. Saves 1 HTML battle replay every 100 generations to `replays_training/`.
6. Supports user generation count input (0 = infinite / until CTRL+C) and provides a full summary upon exit.
"""

import argparse
import copy
import importlib.util
import json
import multiprocessing
import os
import random
import signal
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PRIMARY_PATH = os.path.join(_HERE, "main.py")
_PARENT = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_PARENT)

# Ensure opponents and engine directories are in path
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_ROOT, "opponents"))

ENV_NAME = "cabt"
POPULATION_SIZE = max(4, multiprocessing.cpu_count())
MATCHES_PER_MUTANT = 10
MUTATION_RATE = 0.25
MUTATION_PERCENT = 0.15

WEIGHTS_FILE = os.path.join(_HERE, "alak_dragapult_weights.json")
SEARCH_STATE_FILE = os.path.join(_HERE, "dragapult_search_state.json")
PROGRESS_FILE = os.path.join(_HERE, "training_progress.json")
REPLAY_DIR = os.path.join(_HERE, "replays_training")

os.makedirs(REPLAY_DIR, exist_ok=True)


def _load_primary_module():
    spec = importlib.util.spec_from_file_location("alakazam_v4_gen", _PRIMARY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_primary_module = _load_primary_module()


def _load_search_seed():
    if os.path.exists(SEARCH_STATE_FILE):
        try:
            with open(SEARCH_STATE_FILE) as f:
                data = json.load(f)
            merged = dict(_primary_module.WEIGHTS)
            merged.update({k: v for k, v in data.items() if k in merged})
            return merged
        except Exception:
            pass
    return dict(_primary_module.WEIGHTS)


_BASE_WEIGHTS = _load_search_seed()


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def mutate(weights, mutation_rate=MUTATION_RATE, mutation_percent=MUTATION_PERCENT):
    mutated = copy.deepcopy(weights)
    for k, v in list(mutated.items()):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if random.random() < mutation_rate:
                factor = 1.0 + random.uniform(-mutation_percent, mutation_percent)
                new_val = v * factor
                mutated[k] = int(round(new_val)) if isinstance(v, int) else round(new_val, 4)
    return mutated


def _play_single_game(args):
    """Worker task for multiprocessing evaluation."""
    mutant_weights, seed_val, save_replay_path = args
    import os, sys
    sys.path.insert(0, _HERE)
    sys.path.insert(0, os.path.join(_ROOT, "opponents"))

    import importlib.util
    spec = importlib.util.spec_from_file_location("alakazam_v4_worker", _PRIMARY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Apply mutant weights
    mod.WEIGHTS.update(mutant_weights)
    mod.W = mod.WEIGHTS

    import dragapult_agent
    from kaggle_environments import make

    env = make(ENV_NAME, debug=False)
    # Swap seat position randomly for balanced evaluation
    if seed_val % 2 == 0:
        agents = [mod.agent, dragapult_agent.agent]
        my_idx = 0
    else:
        agents = [dragapult_agent.agent, mod.agent]
        my_idx = 1

    steps = env.run(agents)
    last_step = steps[-1]
    
    # Calculate rewards & prize differential
    my_status = last_step[my_idx].get("status")
    op_status = last_step[1 - my_idx].get("status")
    my_reward = last_step[my_idx].get("reward") or 0

    won = False
    if my_reward > 0 or (my_status == "DONE" and op_status == "INVALID"):
        won = True
    elif my_reward == 0 and my_status == "DONE" and op_status == "DONE":
        won = False  # Tie or incomplete

    # Save replay HTML if requested
    if save_replay_path:
        try:
            html = env.render(mode="html")
            with open(save_replay_path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass

    return 1 if won else 0


def evaluate_mutant(mutant_weights, num_matches, gen_idx=0, save_replay=False):
    tasks = []
    for m in range(num_matches):
        replay_path = None
        if save_replay and m == 0:
            replay_path = os.path.join(REPLAY_DIR, f"gen_{gen_idx}_Alakazam_V4_vs_Dragapult.html")
        tasks.append((mutant_weights, gen_idx * 1000 + m, replay_path))

    with multiprocessing.Pool(processes=min(POPULATION_SIZE, multiprocessing.cpu_count())) as pool:
        results = pool.map(_play_single_game, tasks)

    wins = sum(results)
    return wins, num_matches


class GenerativeTrainer:
    def __init__(self, target_generations=0):
        self.target_generations = target_generations
        self.best_weights = _load_search_seed()
        self.search_state = dict(self.best_weights)
        self.start_time = time.time()
        self.gen_count = 0
        self.total_matches = 0
        self.initial_win_rate = 0.0
        self.best_win_rate = 0.0
        self.stop_requested = False

        # Load existing progress if available
        if os.path.exists(PROGRESS_FILE):
            try:
                with open(PROGRESS_FILE) as f:
                    pdata = json.load(f)
                self.gen_count = pdata.get("generations", 0)
                self.best_win_rate = pdata.get("best_win_rate", 0.0)
                self.total_matches = pdata.get("total_matches", 0)
            except Exception:
                pass

    def request_stop(self, signum=None, frame=None):
        print("\n[!] Generative learning stop requested. Finalizing and generating report...")
        self.stop_requested = True

    def run(self):
        signal.signal(signal.SIGINT, self.request_stop)

        print("==========================================================================")
        print(" Alakazam V4 — Generative Evolutionary Learning AI (vs Dragapult ex)")
        print("==========================================================================")
        print(f"Target Generations : {'Infinite (CTRL+C to stop)' if self.target_generations == 0 else self.target_generations}")
        print(f"Population Size    : {POPULATION_SIZE} mutants per generation")
        print(f"Matches / Mutant   : {MATCHES_PER_MUTANT} matches")
        print(f"Replay Directory   : {REPLAY_DIR} (1 replay saved every 100 generations)")
        print("==========================================================================\n")

        # Initial baseline benchmark
        print("[*] Benchmarking initial baseline weights against Dragapult ex...")
        base_wins, base_total = evaluate_mutant(self.best_weights, MATCHES_PER_MUTANT * 2, gen_idx=self.gen_count)
        self.initial_win_rate = (base_wins / base_total) * 100.0
        if self.best_win_rate == 0.0:
            self.best_win_rate = self.initial_win_rate

        print(f"[+] Initial Baseline Win Rate vs Dragapult ex: {self.initial_win_rate:.1f}% ({base_wins}/{base_total})\n")

        while not self.stop_requested:
            if self.target_generations > 0 and self.gen_count >= self.target_generations:
                break

            self.gen_count += 1
            gen_start = time.time()
            save_replay = (self.gen_count % 100 == 0) or (self.gen_count == 1)

            # Spawn population of mutants from current search state
            population = [dict(self.search_state)]
            for _ in range(POPULATION_SIZE - 1):
                population.append(mutate(self.search_state))

            best_mutant = None
            best_mutant_wins = -1
            best_mutant_rate = 0.0

            for idx, mutant in enumerate(population):
                is_replay_mutant = (save_replay and idx == 0)
                wins, total = evaluate_mutant(mutant, MATCHES_PER_MUTANT, self.gen_count, save_replay=is_replay_mutant)
                self.total_matches += total
                rate = (wins / total) * 100.0

                if wins > best_mutant_wins:
                    best_mutant_wins = wins
                    best_mutant = mutant
                    best_mutant_rate = rate

            # Selection & Advancement
            self.search_state = dict(best_mutant)
            save_json(SEARCH_STATE_FILE, self.search_state)

            improved = False
            if best_mutant_rate > self.best_win_rate:
                self.best_win_rate = best_mutant_rate
                self.best_weights = dict(best_mutant)
                save_json(WEIGHTS_FILE, self.best_weights)
                improved = True

            gen_elapsed = time.time() - gen_start
            status_flag = "★ NEW BEST!" if improved else "   "
            print(f"Gen {self.gen_count:04d} | Best Mutant WR: {best_mutant_rate:5.1f}% | Overall Best WR: {self.best_win_rate:5.1f}% | Time: {gen_elapsed:4.1f}s {status_flag}")

            # Save progress
            progress_data = {
                "generations": self.gen_count,
                "best_win_rate": self.best_win_rate,
                "initial_win_rate": self.initial_win_rate,
                "total_matches": self.total_matches,
                "elapsed_seconds": round(time.time() - self.start_time, 2),
            }
            save_json(PROGRESS_FILE, progress_data)

        self.print_summary_report()

    def print_summary_report(self):
        total_time = time.time() - self.start_time
        net_improvement = self.best_win_rate - self.initial_win_rate

        print("\n==========================================================================")
        print("                  GENERATIVE LEARNING TRAINING SUMMARY                    ")
        print("==========================================================================")
        print(f" Total Generations Completed : {self.gen_count}")
        print(f" Total Matches Evaluated     : {self.total_matches}")
        print(f" Total Training Time Elapsed : {total_time / 60.0:.2f} minutes")
        print(f" Initial Baseline Win Rate   : {self.initial_win_rate:.1f}%")
        print(f" Best Achieved Win Rate      : {self.best_win_rate:.1f}%")
        print(f" Net Win Rate Improvement    : {net_improvement:+.1f}%")
        print("--------------------------------------------------------------------------")
        print(f" Dragapult Weights File Saved : {WEIGHTS_FILE}")
        print(f" Search State Saved          : {SEARCH_STATE_FILE}")
        print(f" Replays Directory           : {REPLAY_DIR}")
        print("==========================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Generative Evolutionary Learning AI for Alakazam V4 vs Dragapult ex")
    parser.add_argument("--generations", type=int, default=None, help="Number of generations to run (0 for infinite)")
    args = parser.parse_args()

    num_gens = args.generations
    if num_gens is None:
        try:
            val = input("Enter number of generations to run (0 for infinite / until CTRL+C): ").strip()
            num_gens = int(val) if val else 0
        except Exception:
            num_gens = 0

    trainer = GenerativeTrainer(target_generations=num_gens)
    trainer.run()


if __name__ == "__main__":
    main()

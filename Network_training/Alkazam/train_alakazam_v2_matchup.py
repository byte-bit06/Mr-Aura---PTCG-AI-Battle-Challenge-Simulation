import copy
import importlib.util
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Dedicated Matchup Trainer for Alakazam V2 (Grimmsnarl ex & Dragapult ex)
# Optimizes separate profile parameter files until win rate >= 65%
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIR = os.path.join(_HERE, "Alakazam_V2_train")
PRIMARY_PATH = os.path.join(AGENT_DIR, "main.py")

OPPONENTS_DIR = os.path.join(_HERE, "opponents")
if not os.path.exists(OPPONENTS_DIR):
    OPPONENTS_DIR = os.path.join(_PARENT, "opponents")


def _worker_eval_matchup(genome, target_opponent="grimmsnarl", games_count=20):
    """Evaluates genome exclusively against Grimmsnarl ex or Dragapult ex."""
    import copy, importlib.util, os, sys
    from kaggle_environments import make

    _here = _HERE
    _parent = _PARENT
    _agent_dir = AGENT_DIR
    _opp_dir = OPPONENTS_DIR

    if _opp_dir not in sys.path:
        sys.path.append(_opp_dir)

    _cg_root = None
    for c in [_agent_dir, os.path.join(_here, "Alakazam_V2"), _here, _parent]:
        if os.path.exists(os.path.join(c, "cg", "__init__.py")):
            _cg_root = c
            break
    if _cg_root and _cg_root not in sys.path:
        sys.path.insert(0, _cg_root)

    spec = importlib.util.spec_from_file_location("alakazam_v2_train_worker", PRIMARY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.WEIGHTS.update(genome)
    p_agent = mod.agent

    # Load Target Opponent
    opp_agent = None
    if target_opponent == "grimmsnarl":
        _grimm_pkg = os.path.join(_opp_dir, "grimmsnarl_pkg")
        if os.path.exists(_grimm_pkg):
            if _grimm_pkg not in sys.path:
                sys.path.insert(0, _grimm_pkg)
            _old_cwd = os.getcwd()
            try:
                os.chdir(_grimm_pkg)
                import main as _grimm_module
                opp_agent = _grimm_module.agent
            finally:
                os.chdir(_old_cwd)
    elif target_opponent == "dragapult":
        _drag_path = os.path.join(_opp_dir, "dragapult_agent.py")
        if os.path.exists(_drag_path):
            _drag_spec = importlib.util.spec_from_file_location("dragapult_agent", _drag_path)
            _drag_module = importlib.util.module_from_spec(_drag_spec)
            _drag_spec.loader.exec_module(_drag_module)
            opp_agent = _drag_module.agent

    if opp_agent is None:
        return 0.0, 0.0, 0.0, 0.0, genome

    env = make("cabt", debug=False)

    total_wins = 0
    total_prizes_taken = 0
    total_prizes_conceded = 0
    total_game_fitness = 0.0

    for g in range(games_count):
        if g % 2 == 0:
            p1_a, p2_a = p_agent, opp_agent
            is_p1 = True
        else:
            p1_a, p2_a = opp_agent, p_agent
            is_p1 = False

        steps = env.run([p1_a, p2_a])
        r1 = steps[-1][0].reward
        r2 = steps[-1][1].reward

        if is_p1:
            win = 1 if r1 == 1 else (0 if r2 == 1 else 0.5)
        else:
            win = 1 if r2 == 1 else (0 if r1 == 1 else 0.5)

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
                        if is_p1:
                            p1_taken = 6 - p0_prz
                            p1_conceded = 6 - p1_prz
                        else:
                            p1_taken = 6 - p1_prz
                            p1_conceded = 6 - p0_prz
                        break

        match_reward = 2.0 if win == 1 else (-2.0 if win == 0 else 0.0)
        prize_reward = (p1_taken * 0.5) - (p1_conceded * 0.6)
        game_fitness = match_reward + prize_reward

        total_wins += win
        total_prizes_taken += p1_taken
        total_prizes_conceded += p1_conceded
        total_game_fitness += game_fitness

    win_rate = (total_wins / games_count) * 100.0
    avg_taken = total_prizes_taken / games_count
    avg_conc = total_prizes_conceded / games_count
    avg_fitness = win_rate + (total_game_fitness / games_count) * 10.0

    return avg_fitness, win_rate, avg_taken, avg_conc, genome


def mutate_genome(parent_genome, mutation_rate=0.30, mutation_scale=0.25):
    child = copy.deepcopy(parent_genome)
    for key in child:
        if random.random() < mutation_rate:
            change = random.gauss(0, mutation_scale)
            child[key] = max(1, int(child[key] * (1.0 + change)))
    return child


def train_matchup(target_opponent="grimmsnarl", target_win_rate=65.0, max_generations=100, pop_size=12, games_per_eval=16, max_workers=12):
    json_filename = f"alak_w_{target_opponent}.json"
    json_path = os.path.join(AGENT_DIR, json_filename)

    with open(json_path, "r") as f:
        base_genome = json.load(f)

    print(f"\n=========================================================================", flush=True)
    print(f" Starting Alakazam V2 Dedicated Training vs {target_opponent.upper()} EX")
    print(f" Target Win Rate: >= {target_win_rate}% | Profile File: {json_filename}")
    print(f"=========================================================================\n", flush=True)

    best_fitness, best_wr, best_taken, best_conc, _ = _worker_eval_matchup(base_genome, target_opponent, games_per_eval)
    best_genome = base_genome
    print(f"Baseline -> Win Rate: {best_wr:.1f}% | Prizes: +{best_taken:.2f} / -{best_conc:.2f} | Fitness: {best_fitness:.2f}\n", flush=True)

    population = [best_genome] + [mutate_genome(best_genome) for _ in range(pop_size - 1)]

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for gen in range(1, max_generations + 1):
            gen_start = time.time()
            futures = {executor.submit(_worker_eval_matchup, g, target_opponent, games_per_eval): i for i, g in enumerate(population)}

            results = []
            for future in as_completed(futures):
                results.append(future.result())

            results.sort(key=lambda x: x[0], reverse=True)
            gen_best_fitness, gen_wr, gen_taken, gen_conc, gen_best_genome = results[0]

            if gen_best_fitness > best_fitness:
                best_fitness = gen_best_fitness
                best_wr = gen_wr
                best_taken = gen_taken
                best_conc = gen_conc
                best_genome = gen_best_genome
                with open(json_path, "w") as f:
                    json.dump(best_genome, f, indent=4)
                print(f" *** NEW BEST vs {target_opponent.upper()} SAVED to {json_filename}! Win Rate: {best_wr:.1f}% | Prizes: +{best_taken:.2f} / -{best_conc:.2f} ***", flush=True)

            elapsed = time.time() - gen_start
            print(f"Gen {gen:2d} ({elapsed:.1f}s) | Gen Win Rate vs {target_opponent.upper()}: {gen_wr:.1f}% (+{gen_taken:.2f}/-{gen_conc:.2f}) | Overall Best: {best_wr:.1f}%", flush=True)

            if best_wr >= target_win_rate:
                print(f"\n SUCCESS! Target Win Rate >= {target_win_rate}% achieved for {target_opponent.upper()}! Final WR: {best_wr:.1f}%\n", flush=True)
                break

            survivors = [results[0][4], results[1][4], results[2][4]]
            next_pop = copy.deepcopy(survivors)
            while len(next_pop) < pop_size:
                next_pop.append(mutate_genome(random.choice(survivors)))
            population = next_pop


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--opp", choices=["grimmsnarl", "dragapult", "both"], default="both")
    args = parser.parse_args()

    if args.opp in ("grimmsnarl", "both"):
        print("\n=======================================================", flush=True)
        print(" PHASE 1: Training Alakazam V2 Profile vs GRIMMSNARL EX", flush=True)
        print("=======================================================\n", flush=True)
        train_matchup(target_opponent="grimmsnarl", target_win_rate=65.0, max_generations=100, pop_size=12, games_per_eval=16, max_workers=12)

    if args.opp in ("dragapult", "both"):
        print("\n=======================================================", flush=True)
        print(" PHASE 2: Training Alakazam V2 Profile vs DRAGAPULT EX", flush=True)
        print("=======================================================\n", flush=True)
        train_matchup(target_opponent="dragapult", target_win_rate=65.0, max_generations=100, pop_size=12, games_per_eval=16, max_workers=12)

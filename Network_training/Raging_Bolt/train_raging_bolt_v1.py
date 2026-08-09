import copy
import importlib.util
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Parallel Evolutionary Trainer for Raging Bolt V1
# Optimizes rb_w.json weights to maximize win rate across all opponents
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIR = os.path.join(_HERE, "Raging_Bolt_V1")
PRIMARY_PATH = os.path.join(AGENT_DIR, "main.py")

OPPONENTS_DIR = os.path.join(_PARENT, "Alkazam", "opponents")
if not os.path.exists(OPPONENTS_DIR):
    OPPONENTS_DIR = os.path.join(_HERE, "opponents")

# Copy opponent deck files into top20_decks if needed
TOP20_DIR = os.path.join(AGENT_DIR, "top20_decks")
os.makedirs(TOP20_DIR, exist_ok=True)


def _worker_eval(genome, games_per_opponent=4):
    """Evaluate a genome against all available opponents."""
    import importlib.util, os, sys, random
    from kaggle_environments import make

    _here = _HERE
    _parent = _PARENT
    _agent_dir = AGENT_DIR
    _opp_dir = OPPONENTS_DIR

    if _opp_dir not in sys.path:
        sys.path.append(_opp_dir)

    _cg_root = None
    for c in [_agent_dir, _here, _parent]:
        if os.path.exists(os.path.join(c, "cg", "__init__.py")):
            _cg_root = c
            break
    if _cg_root and _cg_root not in sys.path:
        sys.path.insert(0, _cg_root)

    spec = importlib.util.spec_from_file_location("rb_v1_worker", PRIMARY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.WEIGHTS.update(genome)
    p_agent = mod.agent

    # Load opponents
    opp_agents = {}
    for op_filename in os.listdir(_opp_dir):
        if op_filename.endswith(".py") and op_filename not in ("grimmsnarl_agent.py",):
            opp_path = os.path.join(_opp_dir, op_filename)
            try:
                opp_spec = importlib.util.spec_from_file_location(op_filename[:-3], opp_path)
                opp_mod = importlib.util.module_from_spec(opp_spec)
                opp_spec.loader.exec_module(opp_mod)
                if hasattr(opp_mod, "agent"):
                    opp_agents[op_filename] = opp_mod.agent
            except Exception:
                pass

    # Grimmsnarl pkg
    _grimm_pkg = os.path.join(_opp_dir, "grimmsnarl_pkg")
    if os.path.exists(_grimm_pkg):
        if _grimm_pkg not in sys.path:
            sys.path.insert(0, _grimm_pkg)
        _old_cwd = os.getcwd()
        try:
            os.chdir(_grimm_pkg)
            import main as _gm
            opp_agents["grimmsnarl"] = _gm.agent
        except Exception:
            pass
        finally:
            os.chdir(_old_cwd)

    env = make("cabt", debug=False)
    total_wins = 0
    total_games = 0
    total_prizes_taken = 0
    total_prizes_conceded = 0

    for opp_name, opp_agent in opp_agents.items():
        for g in range(games_per_opponent):
            if g % 2 == 0:
                steps = env.run([p_agent, opp_agent])
                r1 = steps[-1][0].reward
                win = 1 if r1 == 1 else 0
            else:
                steps = env.run([opp_agent, p_agent])
                r2 = steps[-1][1].reward
                win = 1 if r2 == 1 else 0

            total_wins += win
            total_games += 1

    win_rate = (total_wins / total_games) * 100.0 if total_games > 0 else 0.0
    fitness = win_rate

    return fitness, win_rate, genome


def mutate_genome(parent_genome, mutation_rate=0.30, mutation_scale=0.25):
    child = copy.deepcopy(parent_genome)
    for key in child:
        if random.random() < mutation_rate:
            change = random.gauss(0, mutation_scale)
            child[key] = max(1, int(child[key] * (1.0 + change)))
    return child


def train(target_win_rate=70.0, max_generations=100, pop_size=12, games_per_opponent=4, max_workers=12):
    json_path = os.path.join(AGENT_DIR, "rb_w.json")

    with open(json_path, "r") as f:
        base_genome = json.load(f)

    print(f"\n=========================================================================", flush=True)
    print(f" Starting Raging Bolt V1 Evolutionary Training")
    print(f" Target Win Rate: >= {target_win_rate}% | Profile File: rb_w.json")
    print(f"=========================================================================\n", flush=True)

    print(f"Evaluating Baseline Genome...", end="", flush=True)
    best_fitness, best_wr, _ = _worker_eval(base_genome, games_per_opponent)
    best_genome = base_genome
    print(f" Done! -> Win Rate: {best_wr:.1f}% | Fitness: {best_fitness:.2f}\n", flush=True)

    population = [best_genome] + [mutate_genome(best_genome) for _ in range(pop_size - 1)]

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for gen in range(1, max_generations + 1):
            gen_start = time.time()
            futures = {executor.submit(_worker_eval, g, games_per_opponent): i for i, g in enumerate(population)}

            results = []
            completed_cnt = 0
            for future in as_completed(futures):
                cand_res = future.result()
                results.append(cand_res)
                completed_cnt += 1
                print(f"  [Gen {gen}] Candidate {completed_cnt:2d}/{pop_size} | WR: {cand_res[1]:.1f}% | Fitness: {cand_res[0]:.2f}", flush=True)

            results.sort(key=lambda x: x[0], reverse=True)
            gen_best_fitness, gen_wr, gen_best_genome = results[0]

            if gen_best_fitness > best_fitness:
                best_fitness = gen_best_fitness
                best_wr = gen_wr
                best_genome = gen_best_genome
                with open(json_path, "w") as f:
                    json.dump(best_genome, f, indent=4)
                print(f" *** NEW BEST SAVED to rb_w.json! Win Rate: {best_wr:.1f}% ***", flush=True)

            elapsed = time.time() - gen_start
            print(f"Gen {gen:2d} ({elapsed:.1f}s) | Gen Best WR: {gen_wr:.1f}% | Overall Best: {best_wr:.1f}%", flush=True)

            if best_wr >= target_win_rate:
                print(f"\n SUCCESS! Target Win Rate >= {target_win_rate}% achieved! Final WR: {best_wr:.1f}%\n", flush=True)
                break

            survivors = [results[0][2], results[1][2], results[2][2]]
            next_pop = copy.deepcopy(survivors)
            while len(next_pop) < pop_size:
                next_pop.append(mutate_genome(random.choice(survivors)))
            population = next_pop


if __name__ == "__main__":
    train(target_win_rate=70.0, max_generations=100, pop_size=12, games_per_opponent=4, max_workers=12)

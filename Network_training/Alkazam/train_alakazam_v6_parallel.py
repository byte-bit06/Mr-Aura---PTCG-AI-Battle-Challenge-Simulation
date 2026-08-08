import copy
import importlib.util
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

# ---------------------------------------------------------------------------
# High-Performance 12-Hour Parallel Multi-Core Evolutionary Optimizer
# Optimized for 24-Core CPU Architecture
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIR = os.path.join(_HERE, "Alakazam_V6")
PRIMARY_PATH = os.path.join(AGENT_DIR, "main.py")
WEIGHTS_JSON_PATH = os.path.join(AGENT_DIR, "alak_w.json")

OPPONENTS_DIR = os.path.join(_HERE, "opponents")
if not os.path.exists(OPPONENTS_DIR):
    OPPONENTS_DIR = os.path.join(_PARENT, "opponents")


def _worker_eval_genome(genome, games_per_opp=10):
    """Isolated worker function for parallel process execution."""
    import copy, importlib.util, os, sys
    from kaggle_environments import make

    # Set up worker path environment
    _here = _HERE
    _parent = _PARENT
    _agent_dir = AGENT_DIR
    _opp_dir = OPPONENTS_DIR

    if _opp_dir not in sys.path:
        sys.path.append(_opp_dir)

    _cg_root = None
    for c in [_agent_dir, os.path.join(_here, "Alakazam_V5"), _here, _parent]:
        if os.path.exists(os.path.join(c, "cg", "__init__.py")):
            _cg_root = c
            break
    if _cg_root and _cg_root not in sys.path:
        sys.path.insert(0, _cg_root)

    # Import primary agent
    spec = importlib.util.spec_from_file_location("alakazam_v6_worker", PRIMARY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.WEIGHTS.update(genome)
    p_agent = mod.agent

    # Load opponents
    opps = {}
    
    # Dragapult ex
    _drag_path = os.path.join(_opp_dir, "dragapult_agent.py")
    if os.path.exists(_drag_path):
        _drag_spec = importlib.util.spec_from_file_location("dragapult_agent", _drag_path)
        _drag_module = importlib.util.module_from_spec(_drag_spec)
        _drag_spec.loader.exec_module(_drag_module)
        opps["Dragapult ex"] = _drag_module.agent

    # Grimmsnarl ex
    _grimm_pkg = os.path.join(_opp_dir, "grimmsnarl_pkg")
    if os.path.exists(_grimm_pkg):
        if _grimm_pkg not in sys.path:
            sys.path.insert(0, _grimm_pkg)
        _old_cwd = os.getcwd()
        try:
            os.chdir(_grimm_pkg)
            import main as _grimm_module
            opps["Grimmsnarl ex"] = _grimm_module.agent
        finally:
            os.chdir(_old_cwd)

    # Wall_V10 V3
    _wall_v10_path = os.path.abspath(os.path.join(_here, "..", "Wall_V10", "V3", "main.py"))
    if os.path.exists(_wall_v10_path):
        _wall_spec = importlib.util.spec_from_file_location("wall_v10_v3", _wall_v10_path)
        _wall_module = importlib.util.module_from_spec(_wall_spec)
        _wall_spec.loader.exec_module(_wall_module)
        opps["Wall_V10 V3"] = _wall_module.agent

    # Standard opponents
    for op_filename in os.listdir(_opp_dir):
        if op_filename.endswith(".py") and op_filename not in ("dragapult_agent.py", "grimmsnarl_agent.py", "alakazam_agent.py"):
            name_clean = op_filename.replace(".py", "").replace("_agent", "").replace("_", " ").title()
            opp_path = os.path.join(_opp_dir, op_filename)
            try:
                opp_spec = importlib.util.spec_from_file_location(op_filename[:-3], opp_path)
                opp_mod = importlib.util.module_from_spec(opp_spec)
                opp_spec.loader.exec_module(opp_mod)
                if hasattr(opp_mod, "agent"):
                    opps[name_clean] = opp_mod.agent
            except Exception:
                pass

    env = make("cabt", debug=False)

    total_wins = 0
    total_games = 0
    total_prizes_taken = 0
    total_prizes_conceded = 0

    for opp_name, opp_agent in opps.items():
        for g in range(games_per_opp):
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

            # Extract exact final prizes taken & conceded
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

            total_wins += win
            total_prizes_taken += p1_taken
            total_prizes_conceded += p1_conceded
            total_games += 1

    win_rate = (total_wins / total_games) * 100.0 if total_games > 0 else 0.0
    avg_prizes_taken = total_prizes_taken / total_games if total_games > 0 else 0.0
    avg_prizes_conceded = total_prizes_conceded / total_games if total_games > 0 else 0.0

    # Composite Multi-Objective Fitness: Win Rate % + 4.0 * (Prizes Taken - Prizes Conceded)
    fitness_score = win_rate + (avg_prizes_taken - avg_prizes_conceded) * 4.0
    return fitness_score, win_rate, avg_prizes_taken, avg_prizes_conceded, genome


def mutate_genome(parent_genome, mutation_rate=0.25, mutation_scale=0.18):
    child = copy.deepcopy(parent_genome)
    for key in child:
        if random.random() < mutation_rate:
            change = random.gauss(0, mutation_scale)
            child[key] = max(1, int(child[key] * (1.0 + change)))
    return child


def run_parallel_evolution(target_hours=12.0, pop_size=16, games_per_opp=10, max_workers=16):
    with open(WEIGHTS_JSON_PATH, "r") as f:
        base_genome = json.load(f)

    start_time = time.time()
    end_time = start_time + (target_hours * 3600.0)

    print(f"\n=========================================================================", flush=True)
    print(f" Starting 12-Hour Multi-Core Parallel Evolutionary Optimizer for Alakazam V6")
    print(f" Target Run Time : {target_hours:.1f} Hours ({target_hours*3600:.0f} Seconds)")
    print(f" Population Size : {pop_size} Candidates per Generation")
    print(f" Games/Opponent  : {games_per_opp} Games (Total {games_per_opp * 9} games per Candidate)")
    print(f" Parallel Cores  : {max_workers} Worker Processes")
    print(f"=========================================================================\n", flush=True)

    # Evaluate baseline genome
    best_fitness, best_wr, best_taken, best_conc, _ = _worker_eval_genome(base_genome, games_per_opp=games_per_opp)
    best_genome = base_genome
    print(f"Generation  0 (Baseline) -> Win Rate: {best_wr:.1f}% | Prizes: +{best_taken:.2f} / -{best_conc:.2f} | Fitness: {best_fitness:.2f}\n", flush=True)

    population = [best_genome] + [mutate_genome(best_genome) for _ in range(pop_size - 1)]
    generation = 1

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        while time.time() < end_time:
            gen_start = time.time()
            
            # Map evaluation across all 16 parallel CPU cores
            futures = [executor.submit(_worker_eval_genome, g, games_per_opp) for g in population]
            results = [f.result() for f in futures]

            results.sort(key=lambda x: x[0], reverse=True)
            gen_best_fitness, gen_wr, gen_taken, gen_conc, gen_best_genome = results[0]

            if gen_best_fitness > best_fitness:
                best_fitness = gen_best_fitness
                best_wr = gen_wr
                best_taken = gen_taken
                best_conc = gen_conc
                best_genome = gen_best_genome
                with open(WEIGHTS_JSON_PATH, "w") as f:
                    json.dump(best_genome, f, indent=4)
                print(f" *** NEW BEST GENOME SAVED to alak_w.json! Win Rate: {best_wr:.1f}% | Prizes: +{best_taken:.2f} / -{best_conc:.2f} ***", flush=True)

            elapsed_gen = time.time() - gen_start
            elapsed_total = (time.time() - start_time) / 3600.0
            remaining_hours = max(0.0, target_hours - elapsed_total)

            print(f"Gen {generation:3d} Complete ({elapsed_gen:.1f}s) | Gen Win Rate: {gen_wr:.1f}% (+{gen_taken:.2f}/-{gen_conc:.2f}) | Overall Best: {best_wr:.1f}% | Time Left: {remaining_hours:.2f} hrs", flush=True)

            # Breed next generation from top 3 elite survivors + cross-mutations
            survivors = [results[0][4], results[1][4], results[2][4]]
            next_pop = copy.deepcopy(survivors)
            while len(next_pop) < pop_size:
                parent = random.choice(survivors)
                next_pop.append(mutate_genome(parent))
            population = next_pop

            generation += 1

    print(f"\n=========================================================================", flush=True)
    print(f" 12-Hour Self-Learning Complete!")
    print(f" Final Best Win Rate       : {best_wr:.1f}%")
    print(f" Final Avg Prizes Taken    : {best_taken:.2f}")
    print(f" Final Avg Prizes Conceded : {best_conc:.2f}")
    print(f" Final Fitness Score       : {best_fitness:.2f}")
    print(f" Optimized weights saved to: {WEIGHTS_JSON_PATH}")
    print(f"=========================================================================\n", flush=True)


if __name__ == "__main__":
    # Target: 12 Hours, Pop Size: 16, Games per Opponent: 10, Max Worker Cores: 16
    run_parallel_evolution(target_hours=12.0, pop_size=16, games_per_opp=10, max_workers=16)

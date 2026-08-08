import copy
import importlib.util
import json
import os
import random
import sys
import time

# ---------------------------------------------------------------------------
# Self-Learning Evolutionary Weight Optimization Engine for Alakazam V6
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

AGENT_DIR = os.path.join(_HERE, "Alakazam_V6")
PRIMARY_PATH = os.path.join(AGENT_DIR, "main.py")
WEIGHTS_JSON_PATH = os.path.join(AGENT_DIR, "alak_w.json")

OPPONENTS_DIR = os.path.join(_HERE, "opponents")
if not os.path.exists(OPPONENTS_DIR):
    OPPONENTS_DIR = os.path.join(_PARENT, "opponents")
sys.path.append(OPPONENTS_DIR)

CG_ROOT = None
for c in [AGENT_DIR, os.path.join(_HERE, "Alakazam_V5"), _HERE, _PARENT]:
    if os.path.exists(os.path.join(c, "cg", "__init__.py")):
        CG_ROOT = c
        break

if CG_ROOT and CG_ROOT not in sys.path:
    sys.path.insert(0, CG_ROOT)

from kaggle_environments import make

# Load Primary Module
_spec = importlib.util.spec_from_file_location("alakazam_v6", PRIMARY_PATH)
primary_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(primary_module)
primary_agent = primary_module.agent

# Load Opponent Agents
opponents = {}

# 1. Dragapult ex
_drag_path = os.path.join(OPPONENTS_DIR, "dragapult_agent.py")
if os.path.exists(_drag_path):
    _drag_spec = importlib.util.spec_from_file_location("dragapult_agent", _drag_path)
    _drag_module = importlib.util.module_from_spec(_drag_spec)
    _drag_spec.loader.exec_module(_drag_module)
    opponents["Dragapult ex"] = _drag_module.agent

# 2. Grimmsnarl ex
_grimm_pkg = os.path.join(OPPONENTS_DIR, "grimmsnarl_pkg")
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

# 4. Standard Opponents
for op_filename in os.listdir(OPPONENTS_DIR):
    if op_filename.endswith(".py") and op_filename not in ("dragapult_agent.py", "grimmsnarl_agent.py", "alakazam_agent.py"):
        name_clean = op_filename.replace(".py", "").replace("_agent", "").replace("_", " ").title()
        opp_path = os.path.join(OPPONENTS_DIR, op_filename)
        try:
            opp_spec = importlib.util.spec_from_file_location(op_filename[:-3], opp_path)
            opp_mod = importlib.util.module_from_spec(opp_spec)
            opp_spec.loader.exec_module(opp_mod)
            if hasattr(opp_mod, "agent"):
                opponents[name_clean] = opp_mod.agent
        except Exception:
            pass


def play_game(env, p1_agent, p2_agent):
    steps = env.run([p1_agent, p2_agent])
    r1 = steps[-1][0].reward
    r2 = steps[-1][1].reward
    win = 1 if r1 == 1 else (0 if r2 == 1 else 0.5)

    # Extract exact final prizes taken & conceded from the last step observation dictionary
    p1_taken, p1_conceded = 0, 0
    for idx in range(len(steps) - 1, -1, -1):
        step = steps[idx]
        if isinstance(step, list) and len(step) > 0 and isinstance(step[0], dict):
            obs_dict = step[0].get("observation", {})
            if isinstance(obs_dict, dict) and "current" in obs_dict:
                curr = obs_dict["current"]
                if isinstance(curr, dict) and "players" in curr and len(curr["players"]) >= 2:
                    p0 = curr["players"][0]
                    p1 = curr["players"][1]
                    p0_prz = len(p0.get("prize", []))
                    p1_prz = len(p1.get("prize", []))
                    p1_taken = 6 - p0_prz
                    p1_conceded = 6 - p1_prz
                    break

    return win, p1_taken, p1_conceded


def evaluate_genome(env, genome, games_per_opp=2):
    # Update active weights in primary module
    primary_module.WEIGHTS.update(genome)
    
    total_wins = 0
    total_games = 0
    total_prizes_taken = 0
    total_prizes_conceded = 0
    
    for opp_name, opp_agent in opponents.items():
        for g in range(games_per_opp):
            if g % 2 == 0:
                win, taken, conc = play_game(env, primary_agent, opp_agent)
                total_wins += win
                total_prizes_taken += taken
                total_prizes_conceded += conc
            else:
                win, conc, taken = play_game(env, opp_agent, primary_agent)
                total_wins += (1 - win if win in (0, 1) else 0.5)
                total_prizes_taken += taken
                total_prizes_conceded += conc
            total_games += 1
            
    win_rate = (total_wins / total_games) * 100.0 if total_games > 0 else 0.0
    avg_prizes_taken = total_prizes_taken / total_games if total_games > 0 else 0.0
    avg_prizes_conceded = total_prizes_conceded / total_games if total_games > 0 else 0.0

    # Composite Fitness: 70% Win Rate + Net Prize Differential (Prizes Taken - Prizes Conceded)
    fitness_score = win_rate + (avg_prizes_taken - avg_prizes_conceded) * 3.0
    return fitness_score, win_rate, avg_prizes_taken, avg_prizes_conceded


def mutate_genome(parent_genome, mutation_rate=0.2, mutation_scale=0.15):
    child = copy.deepcopy(parent_genome)
    for key in child:
        if random.random() < mutation_rate:
            change = random.gauss(0, mutation_scale)
            child[key] = max(1, int(child[key] * (1.0 + change)))
    return child


def run_evolution(generations=15, pop_size=6, games_per_opp=2):
    env = make("cabt", debug=False)
    
    with open(WEIGHTS_JSON_PATH, "r") as f:
        base_genome = json.load(f)
        
    print(f"\n==========================================================", flush=True)
    print(f" Starting Self-Learning Evolution for Alakazam V6")
    print(f" Total Opponents: {len(opponents)} | Pop Size: {pop_size} | Generations: {generations}")
    print(f"==========================================================\n", flush=True)
    
    # Evaluate baseline genome
    best_fitness, best_wr, best_taken, best_conc = evaluate_genome(env, base_genome, games_per_opp=games_per_opp)
    best_genome = base_genome
    print(f"Generation  0 (Baseline) -> Win Rate: {best_wr:.1f}% | Avg Prizes Taken: {best_taken:.2f} | Avg Prizes Conceded: {best_conc:.2f} | Fitness: {best_fitness:.2f}\n", flush=True)
    
    population = [best_genome] + [mutate_genome(best_genome) for _ in range(pop_size - 1)]
    
    for gen in range(1, generations + 1):
        gen_start = time.time()
        scores = []
        
        for i, genome in enumerate(population):
            fitness, wr, taken, conc = evaluate_genome(env, genome, games_per_opp=games_per_opp)
            scores.append((fitness, wr, taken, conc, genome))
            
        scores.sort(key=lambda x: x[0], reverse=True)
        gen_best_fitness, gen_wr, gen_taken, gen_conc, gen_best_genome = scores[0]
        
        if gen_best_fitness > best_fitness:
            best_fitness = gen_best_fitness
            best_wr = gen_wr
            best_taken = gen_taken
            best_conc = gen_conc
            best_genome = gen_best_genome
            with open(WEIGHTS_JSON_PATH, "w") as f:
                json.dump(best_genome, f, indent=4)
            print(f" *** NEW BEST GENOME SAVED to alak_w.json! Win Rate: {best_wr:.1f}% | Prizes Taken: {best_taken:.2f} | Prizes Conceded: {best_conc:.2f} ***", flush=True)
            
        elapsed = time.time() - gen_start
        print(f"Generation {gen:2d}/{generations} Complete | Best Gen Win Rate: {gen_wr:.1f}% (Prizes: +{gen_taken:.2f} / -{gen_conc:.2f}) | Overall Best: {best_wr:.1f}% ({elapsed:.1f}s)", flush=True)
        
        # Breed next generation from top 2 survivors
        survivors = [scores[0][4], scores[1][4]]
        next_pop = copy.deepcopy(survivors)
        while len(next_pop) < pop_size:
            p = random.choice(survivors)
            next_pop.append(mutate_genome(p))
        population = next_pop

    print(f"\n==========================================================", flush=True)
    print(f" Self-Learning Complete! Final Best Win Rate: {best_wr:.1f}% | Avg Prizes Taken: {best_taken:.2f} | Avg Prizes Conceded: {best_conc:.2f}")
    print(f" Optimized weights saved to: {WEIGHTS_JSON_PATH}")
    print(f"==========================================================\n", flush=True)


if __name__ == "__main__":
    run_evolution(generations=10, pop_size=5, games_per_opp=2)

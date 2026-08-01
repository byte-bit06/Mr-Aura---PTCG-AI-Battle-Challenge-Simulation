import os
import json
import random
import copy
import multiprocessing
import sys
from kaggle_environments import make

sys.path.append(os.path.join(os.path.dirname(__file__), "opponents"))

import main as crustle_main
try:
    import lucario_agent
    import iono_agent
    import dragapult_agent
    import abomasnow_agent
    import mcts_lucario_agent
    import archaludon_cinderace_agent
except ImportError:
    lucario_agent = None
    iono_agent = None
    dragapult_agent = None
    abomasnow_agent = None
    mcts_lucario_agent = None
    archaludon_cinderace_agent = None

ENV_NAME = "cabt"
GENERATIONS = 50
POPULATION_SIZE = 50
MATCHES_PER_MUTANT = 20

WEIGHTS_FILE = os.path.join(os.path.dirname(__file__), "optimized_weights.json")

def load_base_weights():
    if os.path.exists(WEIGHTS_FILE):
        with open(WEIGHTS_FILE, "r") as f:
            return json.load(f)
    return crustle_main.W

def save_weights(weights):
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=4)

def mutate(weights, mutation_rate=0.2, mutation_percent=0.15):
    mutated = copy.deepcopy(weights)
    for key in mutated:
        if random.random() < mutation_rate:
            # Mutate by up to +/- 15% of the current weight's value
            current_val = mutated[key]
            # If the value is 0, bump it slightly so it can grow
            if current_val == 0:
                mutated[key] += random.uniform(-100.0, 100.0)
            else:
                mutated[key] += current_val * random.uniform(-mutation_percent, mutation_percent)
    return mutated

def create_agent_with_weights(custom_weights):
    def agent(obs_dict: dict) -> list[int]:
        # Inject mutant weights into the main engine
        crustle_main.W = custom_weights
        return crustle_main.agent(obs_dict)
    return agent

def evaluate_mutant(mutant_weights):
    import sys
    import os
    import random
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    
    agent_closure = create_agent_with_weights(mutant_weights)
    
    opponents = [agent_closure]
    if lucario_agent is not None:
        opponents.append(lucario_agent.agent)
    if iono_agent is not None:
        opponents.append(iono_agent.agent)
    if dragapult_agent is not None:
        opponents.append(dragapult_agent.agent)
    if abomasnow_agent is not None:
        opponents.append(abomasnow_agent.agent)
    if mcts_lucario_agent is not None:
        opponents.append(mcts_lucario_agent.agent)
    if archaludon_cinderace_agent is not None:
        opponents.append(archaludon_cinderace_agent.agent)
    
    wins = 0
    try:
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
        old_stderr.write(f"\\nCRASH in mutant evaluation: {e}\\n")
        wins = 0 # Penalize crashes heavily
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    win_rate = wins / MATCHES_PER_MUTANT
    print(f"[Worker] Mutant evaluated -> Win Rate: {win_rate*100:.1f}%", flush=True)
    return win_rate

def main():
    print("Starting Genetic Optimization Pipeline (100K Games) with Kaggle Meta Gauntlet...", flush=True)
    base_weights = load_base_weights()
    
    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())
    
    for generation in range(GENERATIONS):
        print(f"\n--- Generation {generation+1} ---", flush=True)
        population = [base_weights]
        for _ in range(POPULATION_SIZE - 1):
            population.append(mutate(base_weights))
            
        print(f"Evaluating {POPULATION_SIZE} mutants in parallel...", flush=True)
        
        win_rates = pool.map(evaluate_mutant, population)
        
        best_win_rate = -1
        best_weights = base_weights
        
        for i, win_rate in enumerate(win_rates):
            if win_rate > best_win_rate:
                best_win_rate = win_rate
                best_weights = population[i]
                
        print(f"\n=========================================", flush=True)
        print(f"🏆 Generation {generation+1} Completed!", flush=True)
        print(f"Best Win Rate: {best_win_rate*100:.1f}%", flush=True)
        print(f"--- Weight Evolution ---", flush=True)
        for k in best_weights:
            diff = best_weights[k] - base_weights.get(k, 0)
            if abs(diff) > 0.01:
                print(f"  {k}: {base_weights.get(k, 0):.2f} -> {best_weights[k]:.2f} ({diff:+.2f})", flush=True)
        print(f"=========================================\n", flush=True)
        
        base_weights = best_weights
        save_weights(base_weights)

    pool.close()
    print("\nGenetic training complete. Optimized weights saved.", flush=True)

if __name__ == "__main__":
    main()

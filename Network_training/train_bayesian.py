import os
import json
import random
import sys
import copy
from kaggle_environments import make
import optuna

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
TRIALS = 4000
MATCHES_PER_TRIAL = 20
WEIGHTS_FILE = os.path.join(os.path.dirname(__file__), "optimized_weights.json")

def save_weights(weights):
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=4)

def create_agent_with_weights(custom_weights):
    def agent(obs_dict: dict) -> list[int]:
        crustle_main.W = custom_weights
        return crustle_main.agent(obs_dict)
    return agent

def evaluate_weights(custom_weights):
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    
    agent_closure = create_agent_with_weights(custom_weights)
    
    opponents = [agent_closure]
    if lucario_agent is not None: opponents.append(lucario_agent.agent)
    if iono_agent is not None: opponents.append(iono_agent.agent)
    if dragapult_agent is not None: opponents.append(dragapult_agent.agent)
    if abomasnow_agent is not None: opponents.append(abomasnow_agent.agent)
    if mcts_lucario_agent is not None: opponents.append(mcts_lucario_agent.agent)
    if archaludon_cinderace_agent is not None: opponents.append(archaludon_cinderace_agent.agent)
    
    wins = 0
    try:
        env = make(ENV_NAME, debug=False)
        for match_idx in range(MATCHES_PER_TRIAL):
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
        old_stderr.write(f"\nCRASH in evaluation: {e}\n")
        wins = 0
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return wins / MATCHES_PER_TRIAL

def objective(trial):
    custom_weights = copy.deepcopy(crustle_main._WEIGHT_DEFAULTS)
    
    # Bayesian sampling: restrict search to within 50% of the mathematical baseline.
    for key, base_val in crustle_main._WEIGHT_DEFAULTS.items():
        if base_val == 0.0:
            custom_weights[key] = trial.suggest_float(key, -1000.0, 1000.0)
        elif base_val > 0:
            custom_weights[key] = trial.suggest_float(key, base_val * 0.5, base_val * 1.5)
        else:
            # For negative values, 1.5 is more negative (lower), 0.5 is less negative (higher)
            custom_weights[key] = trial.suggest_float(key, base_val * 1.5, base_val * 0.5)
            
    win_rate = evaluate_weights(custom_weights)
    return win_rate

def optuna_callback(study, trial):
    # Whenever a new best trial is found, save the weights!
    if study.best_trial.number == trial.number:
        print(f"\n[+] NEW BEST WIN RATE FOUND: {trial.value*100:.1f}% (Trial {trial.number})")
        # Extract best weights
        best_weights = copy.deepcopy(crustle_main._WEIGHT_DEFAULTS)
        for key in crustle_main._WEIGHT_DEFAULTS.keys():
            best_weights[key] = study.best_trial.params[key]
            
        save_weights(best_weights)

if __name__ == "__main__":
    import logging
    # Clean up optuna logging so it doesn't spam the console every single trial, just print progress manually
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    print("Starting Bayesian Optimization via Optuna (TPE)...", flush=True)
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=TRIALS, n_jobs=1, callbacks=[optuna_callback], show_progress_bar=True)
    
    print(f"\\nOptimization Finished! Best Win Rate: {study.best_value*100:.1f}%")

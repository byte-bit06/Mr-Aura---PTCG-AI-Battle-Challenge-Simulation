import json
import os
import copy
import random
from datetime import datetime

import main

DATASET_FILE = "dagger_dataset.jsonl"
HISTORY_DIR = "weight_history"

def load_dataset():
    if not os.path.exists(DATASET_FILE):
        print(f"Dataset {DATASET_FILE} not found.")
        return []
    
    data = []
    with open(DATASET_FILE, "r") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def evaluate_weights(dataset, test_weights):
    """
    Returns the accuracy (0.0 to 1.0) of test_weights matching human_choice.
    """
    if not dataset: return 0.0
    
    # Temporarily override main's weights
    original_weights = copy.deepcopy(main.W)
    main.W.update(test_weights)
    
    matches = 0
    for entry in dataset:
        obs = entry["obs"]
        human_choice = entry["human_choice"]
        
        # Must reset main's per-turn state to simulate correctly
        main._dict_pre_turn = -1 
        
        agent_choice = main._agent_dict(copy.deepcopy(obs))
        
        # Compare first index
        agent_idx = agent_choice[0] if isinstance(agent_choice, list) and agent_choice else -1
        human_idx = human_choice[0] if isinstance(human_choice, list) and human_choice else -1
        
        if agent_idx == human_idx:
            matches += 1
            
    # Restore
    main.W = original_weights
    
    return matches / len(dataset)

def optimize_weights(dataset):
    print(f"Loaded {len(dataset)} human-annotated examples.")
    
    base_weights = copy.deepcopy(main.W)
    best_acc = evaluate_weights(dataset, base_weights)
    best_weights = copy.deepcopy(base_weights)
    
    print(f"Baseline accuracy: {best_acc*100:.2f}%")
    
    # Simple Hill Climbing
    iterations = 500
    mutation_rate = 0.2
    mutation_scale = 0.5 # change up to 50%
    
    improved = False
    
    for i in range(iterations):
        test_weights = copy.deepcopy(best_weights)
        # Mutate
        for k in test_weights.keys():
            if random.random() < mutation_rate:
                change = 1.0 + random.uniform(-mutation_scale, mutation_scale)
                test_weights[k] = int(test_weights[k] * change)
                
        acc = evaluate_weights(dataset, test_weights)
        if acc > best_acc:
            best_acc = acc
            best_weights = copy.deepcopy(test_weights)
            improved = True
            print(f"Iter {i:3d} | New Best Accuracy: {best_acc*100:.2f}%")
            
        if best_acc >= 1.0:
            print("100% accuracy reached!")
            break

    if improved:
        print(f"\nFinal optimized accuracy: {best_acc*100:.2f}%")
        
        # Save to main optimized weights
        with open("optimized_weights.json", "w") as f:
            json.dump(best_weights, f, indent=4)
            
        # Save version history
        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = os.path.join(HISTORY_DIR, f"weights_{ts}.json")
        with open(history_file, "w") as f:
            json.dump(best_weights, f, indent=4)
            
        print(f"Updated weights saved to optimized_weights.json")
        print(f"Version backup saved to {history_file}")
    else:
        print("\nCould not improve upon baseline accuracy with simple hill climbing.")


if __name__ == "__main__":
    ds = load_dataset()
    if ds:
        optimize_weights(ds)
    else:
        print("Play some games using dagger_loop.py first to build the dataset!")

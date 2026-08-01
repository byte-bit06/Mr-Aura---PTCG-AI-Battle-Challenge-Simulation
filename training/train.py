# train.py
import random
import os
import pickle
from kaggle_environments import make
from agent import agent as candidate_agent

WEIGHTS_FILE = "agent_weights.pkl"

def get_weights():
    default_weights = [50.0, 20.0, 15.0, 15.0, 10.0, 1.0]
    if os.path.exists(WEIGHTS_FILE):
        with open(WEIGHTS_FILE, "rb") as f:
            return pickle.load(f)
    return default_weights

def save_weights(weights):
    with open(WEIGHTS_FILE, "wb") as f:
        pickle.dump(weights, f)

def mutate(weights):
    # Slightly nudge parameters to discover new strategic synergies
    return [w + random.uniform(-2.0, 2.0) for w in weights]

def run_simulation(deck):
    """
    Runs a local head-to-head match using the cabt environment engine.
    """
    try:
        env = make("cabt", configuration={"decks": [deck, deck]})
        env.run([candidate_agent, candidate_agent])
        
        # Determine winner from final states if available
        states = env.state
        if states and len(states) >= 2:
            # Check player statuses
            p1_status = getattr(states[0], "status", "")
            if p1_status == "DONE":
                return 1
        return 0
    except Exception:
        return 0

def main():
    with open("deck.csv") as f:
        deck = [int(line) for line in f.readlines() if line.strip()]

    current_weights = get_weights()
    print(f"Starting evolutionary training with weights: {current_weights}")

    generations = 5
    matches_per_gen = 3

    for gen in range(generations):
        print(f"\n--- Generation {gen + 1} of {generations} ---")
        
        population = [current_weights] + [mutate(current_weights) for _ in range(3)]
        scores = {}

        for idx, weights in enumerate(population):
            save_weights(weights)
            wins = 0
            for _ in range(matches_per_gen):
                wins += run_simulation(deck)
            scores[idx] = wins
            print(f"Candidate {idx} won {wins}/{matches_per_gen} test games.")

        best_idx = max(scores, key=scores.get)
        current_weights = population[best_idx]
        save_weights(current_weights)
        print(f"Generation {gen + 1} complete. Best candidate preserved.")

    print(f"\nTraining complete! Final weights saved to {WEIGHTS_FILE}")

if __name__ == "__main__":
    main()
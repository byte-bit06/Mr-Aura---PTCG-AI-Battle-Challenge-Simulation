import json
import os
import csv

def load_strategy_guide(root_dir):
    guide_path = os.path.join(root_dir, "data", "strategy_guide.txt")
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def load_card_data(root_dir):
    csv_path = os.path.join(root_dir, "data", "EN_Card_Data.csv")
    cards = {}
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0 or len(row) < 2: continue
                cards[row[0]] = row[1]
    return cards

def format_obs(obs):
    # Converts the raw JSON observation into a readable text block for the LLM
    # (We will expand this to be highly descriptive)
    return json.dumps(obs, indent=2)

def main():
    root_dir = os.path.dirname(os.path.dirname(__file__))
    input_file = os.path.join(root_dir, "data", "dagger_dataset.jsonl")
    output_file = os.path.join(root_dir, "llm_training", "formatted_dataset.json")
    
    strategy_guide = load_strategy_guide(root_dir)
    system_prompt = f"""You are an elite, world-champion Pokémon TCG AI.
You must output a short chain of logical reasoning, followed strictly by your chosen move wrapped in XML tags, like this:
<MOVE> 0 </MOVE>

Here is your strategy guide and manual:
{strategy_guide}
"""

    formatted_data = []
    
    if not os.path.exists(input_file):
        print(f"No dagger dataset found at {input_file}. Run the annotator first!")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            
            # The human choice is our ground truth (Chosen)
            # The heuristic choice is the rejected move (Rejected)
            human_choice = data.get("human_choice", [])
            heuristic_choice = data.get("heuristic_choice", [])
            
            if not human_choice:
                continue
                
            chosen_idx = human_choice[0]
            
            obs_text = format_obs(data.get("obs"))
            
            # We construct a conversational format compatible with ChatML/Unsloth
            conversation = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Current Game State:\n{obs_text}\nWhat is your move?"},
                {"role": "assistant", "content": f"Based on the optimal strategy, I select this option.\n<MOVE> {chosen_idx} </MOVE>"}
            ]
            
            formatted_data.append({"messages": conversation})
            
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(formatted_data, f, indent=2)
        
    print(f"Successfully formatted {len(formatted_data)} examples into {output_file}")

if __name__ == "__main__":
    main()

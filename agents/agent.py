# agent.py
import os
import pickle

WEIGHTS_FILE = "agent_weights.pkl"

def load_weights():
    # Default weights: [prize_progress, evolution_count, solrock_bonus, lunatone_bonus, attack_bonus, fallback_bias]
    default_weights = [50.0, 20.0, 15.0, 15.0, 10.0, 1.0]
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, "rb") as f:
                return pickle.load(f)
        except Exception:
            return default_weights
    return default_weights

def analyze_board(obs):
    """
    Scans the observation structure for macro indicators:
    evolved Lucarios, Solrock, Lunatone, and action intent.
    """
    # Safe extraction based on cabt engine observations
    current_state = obs.get("current", {})
    players = current_state.get("players", [])
    
    lucario_count = 0
    has_solrock = False
    has_lunatone = False

    if len(players) > 0:
        us = players[0]
        all_pkmn = []
        if hasattr(us, "active") and us.active:
            all_pkmn.append(us.active)
        if hasattr(us, "bench") and us.bench:
            all_pkmn.extend(us.bench)

        for p in all_pkmn:
            name = str(getattr(p, "name", "")).lower()
            if "lucario" in name:
                stage = getattr(p, "stage", 0)
                if stage > 0:
                    lucario_count += 1
            if "solrock" in name:
                has_solrock = True
            if "lunatone" in name:
                has_lunatone = True

    return {
        "lucario_count": lucario_count,
        "has_solrock": 1.0 if has_solrock else 0.0,
        "has_lunatone": 1.0 if has_lunatone else 0.0
    }

def agent(obs):
    """
    Kaggle-environments entry point function for cabt engine.
    """
    # cabt presents options under obs["select"]["option"] or obs.get("options")
    select_data = obs.get("select", {})
    legal_options = select_data.get("option") or obs.get("options") or []
    
    if not legal_options:
        return [] # Empty action block safety fallback

    # If only 1 choice is available, return its index/selection format
    if len(legal_options) == 1:
        max_count = select_data.get("maxCount", 1)
        return [0] * max_count

    weights = load_weights()
    board_metrics = analyze_board(obs)

    best_score = float('-inf')
    best_index = 0

    for idx, option in enumerate(legal_options):
        desc = str(option).lower()
        
        # Feature vector mapping
        is_attack = 1.0 if "attack" in desc or "damage" in desc else 0.0
        is_draw = 1.0 if "draw" in desc or "search" in desc else 0.0
        
        score = (
            board_metrics["lucario_count"] * weights[1] +
            board_metrics["has_solrock"] * weights[2] +
            board_metrics["has_lunatone"] * weights[3] +
            is_attack * weights[4] +
            weights[5]
        )
        
        if score > best_score:
            best_score = score
            best_index = idx

    max_count = select_data.get("maxCount", 1)
    return [best_index] * max_count
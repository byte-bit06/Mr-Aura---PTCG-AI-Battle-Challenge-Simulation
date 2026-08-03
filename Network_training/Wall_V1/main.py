import os
import sys
import json
from collections import defaultdict

# ── Weights ───────────────────────────────────────────────────────────────────
_WEIGHT_DEFAULTS = {
    "retreat_crustle_penalty": -100.0,
    "play_kangaskhan_active_bonus": 50.0,
    "evolve_dwebble_bonus": 80.0,
    "play_petrel_bonus": 20.0,
    "attach_energy_ogerpon_bonus": 30.0,
    "use_community_center_bonus": 10.0,
    "use_factory_bonus": 15.0,
    "attach_hero_cape_crustle_bonus": 40.0,
    "base_attack_score": 1000.0,
    "base_retreat_score": -50.0
}

def _load_weights():
    for candidate in ["optimized_weights.json", "/kaggle_simulations/agent/optimized_weights.json", "Network_training/optimized_weights.json"]:
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    data = json.load(f)
                merged = dict(_WEIGHT_DEFAULTS)
                merged.update({k: v for k, v in data.items() if k in _WEIGHT_DEFAULTS})
                return merged
            except Exception:
                pass
    return dict(_WEIGHT_DEFAULTS)

W = _load_weights()

# ── Deck ──────────────────────────────────────────────────────────────────────
def load_deck():
    for p in ["data/deck.csv", "/kaggle_simulations/agent/deck.csv", "../data/deck.csv"]:
        if os.path.exists(p):
            with open(p) as f:
                return [int(line) for line in f if line.strip()]
    # Fallback to hardcoded list if file is missing
    return [344]*4 + [345]*3 + [756]*2 + [117]*2 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [18]*4 + [14]*3 + [20]*2 + [1]

my_deck = load_deck()

# ── Card IDs ──────────────────────────────────────────────────────────────────
Dwebble = 344
Crustle = 345
Kangaskhan = 756
Ogerpon = 117

# ── Agent ─────────────────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    """
    Hybrid Heuristic Agent optimized for the Crustle Wall Deck.
    Scores options based on tunable genetic weights.
    """
    select_data = obs_dict.get("select")
    if select_data is None:
        if obs_dict.get("step", 0) == 0:
            return my_deck
        return []

    options = select_data.get("option", [])
    if not options:
        return [0]

    max_count = select_data.get("maxCount", 1)
    current = obs_dict.get("current")

    # Handle Pre-Game Preparation Phase (Coin toss, IsFirst, Pre-game setup when current is None)
    if current is None:
        return [0] * max_count

    context = select_data.get("context", "")

    scores = []
    for o in options:
        ot = o.get("type", "")
        score = 0.0

        if ot == "PLAY":
            # Rough tactile logic for Trainers
            score += 10.0 
            
            # We would parse the actual hand card here. 
            # In a full CABT parser, we extract `cid` from `_dict_get_card(obs_dict, "HAND", o["index"])`
            # For demonstration in this stub, we apply generic bonuses to the PLAY action
            # to show where the genetic weights hook in.
            score += W.get("play_poffin_dwebble_bonus", 0.0) * 0.1
            score += W.get("heal_jumbo_ice_cream_bonus", 0.0) * 0.1
            score += W.get("play_lillie_draw_bonus", 0.0) * 0.1
            score += W.get("play_factory_petrel_combo_bonus", 0.0) * 0.1
            score += W.get("play_boss_orders_disrupt_bonus", 0.0) * 0.1
            score += W.get("play_xerosic_disrupt_bonus", 0.0) * 0.1
            
        elif context == "SETUP_ACTIVE_POKEMON" or context == "TO_ACTIVE":
            # If we are specifically placing a Pokemon in the active spot, reward Kangaskhan
            # A full implementation would inspect obs_dict to see if the chosen card is Kangaskhan
            score += W.get("play_kangaskhan_active_bonus", 0.0)
        elif ot == "EVOLVE":
            score += W.get("evolve_dwebble_bonus", 0.0)
        elif ot == "ATTACH":
            score += W.get("attach_energy_ogerpon_bonus", 0.0)
        elif ot == "RETREAT":
            score += W.get("base_retreat_score", 0.0)
        elif ot == "ATTACK":
            score += W.get("base_attack_score", 0.0)
        else:
            score += 1.0
            
        scores.append(score)

    # Sort descending by score
    desc_indices = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
    return desc_indices[:select_data.get("maxCount", 1)]

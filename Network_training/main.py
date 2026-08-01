import os
import sys
import json
from collections import defaultdict

# ── Weights ───────────────────────────────────────────────────────────────────
_WEIGHT_DEFAULTS = {
    "base_evolve_score": 80000.0,
    "base_play_score": 60000.0,
    "base_attach_score": 40000.0,
    "base_retreat_score": 20000.0,
    "base_attack_score": 1000.0,
    "play_poffin_dwebble_bonus": 5000.0,
    "heal_jumbo_ice_cream_bonus": 5000.0,
    "play_lillie_draw_bonus": 4000.0,
    "play_morty_draw_bonus": 2000.0,
    "play_factory_petrel_combo_bonus": 6000.0,
    "play_boss_orders_disrupt_bonus": 4500.0,
    "play_xerosic_disrupt_bonus": 3000.0,
    "play_colress_tenacity_bonus": 3500.0,
    "play_hilda_bonus": 3000.0,
    "use_community_center_bonus": 2000.0,
    "play_pokegear_bonus": 1000.0,
    "play_kangaskhan_active_bonus": 5000.0,
    "evolve_dwebble_bonus": 5000.0,
    "attach_energy_ogerpon_bonus": 2000.0,
    "attach_hero_cape_crustle_bonus": 4000.0,
    "attack_lethal_bonus": 5000.0,
    "panic_heal_multiplier": 2.5,
    "late_game_disrupt_multiplier": 2.0,
    "retreat_cost_penalty": 0.0,
    "retreat_crustle_penalty": 0.0,
    "switch_to_crustle_ex_bonus": 8000.0,
    "switch_to_ogerpon_ability_bonus": 8000.0,
    "switch_to_wall_bonus": 5000.0,
    "attach_energy_saturation_penalty": -50000.0,
    "attach_bench_wall_bonus": 8000.0,
    "play_kangaskhan_late_game_penalty": -100000.0,
    "play_boss_orders_lethal_active_penalty": -50000.0,
    "play_boss_orders_pivot_bonus": 20000.0,
    "play_boss_orders_bench_out_bonus": 10000.0,
    "switch_lethal_active_penalty": -50000.0,
    "switch_pivot_bonus": 20000.0,
    "play_draw_supporter_bricking_bonus": 50000.0,
    "active_wall_ex_bonus": 20000.0,
    "active_wall_ability_bonus": 20000.0,
    "active_dwebble_has_crustle_bonus": 10000.0,
    "active_energy_multiplier": 10000.0,
    "attach_energy_saturation_penalty_extreme": -100000.0,
    "attack_nullified_penalty": -100000.0,
    "attack_lethal_bench_0_bonus": 200000.0,
    "attack_lethal_bench_1_bonus": 50000.0,
    "attack_lethal_bench_2plus_bonus": 10000.0,
    "target_bench_base_score": 10000.0,
    "target_bench_lethal_bonus": 50000.0
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

import csv

_CARD_DB = {}

def _load_card_database():
    global _CARD_DB
    if _CARD_DB: return
    for candidate in ["EN_Card_Data.csv", "data/EN_Card_Data.csv", "/kaggle_simulations/agent/EN_Card_Data.csv"]:
        if os.path.exists(candidate):
            try:
                with open(candidate, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            cid = int(row["Card ID"])
                            _CARD_DB[cid] = row
                        except ValueError:
                            pass
                break
            except Exception:
                pass

def _get_card_id(obs_dict, option, my_index):
    if "index" not in option: return None
    idx = option["index"]
    try:
        players = obs_dict["current"]["players"]
        area = option.get("area")
        if area == 2: return players[my_index]["hand"][idx]["id"]
        elif area == 4: return players[my_index]["active"][idx]["id"]
        elif area == 6: return players[my_index]["bench"][idx]["id"]
    except Exception:
        pass
    return None

def extract_state(obs_dict):
    current = obs_dict.get("current")
    if not current: return None
    my_idx = current.get("yourIndex", 0)
    opp_idx = 1 - my_idx
    
    my_player = current["players"][my_idx]
    opp_player = current["players"][opp_idx]
    
    state = {
        "turn": current.get("turn", 0),
        "my_idx": my_idx,
        "my_prizes": len(my_player.get("prize", [])),
        "opp_prizes": len(opp_player.get("prize", [])),
        "my_hand_size": my_player.get("handCount", 0),
        "my_hand_ids": [],
        "my_active_hp": 0,
        "my_active_max_hp": 0,
        "my_active_id": None,
        "my_active_energy": 0,
        "my_bench": [],
        "opp_active_hp": 0,
        "opp_active_max_hp": 0,
        "opp_active_weakness": None,
        "opp_active_energy": 0,
        "opp_bench": []
    }
    
    if my_player.get("hand"):
        state["my_hand_ids"] = [c.get("id") for c in my_player["hand"] if "id" in c]
        
    if my_player.get("active") and my_player["active"][0]:
        act = my_player["active"][0]
        state["my_active_hp"] = act.get("hp", 0)
        state["my_active_max_hp"] = act.get("maxHp", 0)
        state["my_active_id"] = act.get("id")
        state["my_active_energy"] = len(act.get("energies", []))
        
    for b in my_player.get("bench", []):
        if b: state["my_bench"].append({"id": b.get("id"), "hp": b.get("hp", 0), "energy": len(b.get("energies", []))})
        
    if opp_player.get("active") and opp_player["active"][0]:
        act = opp_player["active"][0]
        state["opp_active_hp"] = act.get("hp", 0)
        state["opp_active_max_hp"] = act.get("maxHp", 0)
        state["opp_active_energy"] = len(act.get("energies", []))
        opp_id = act.get("id")
        state["opp_active_id"] = opp_id
        if opp_id and opp_id in _CARD_DB:
            state["opp_active_weakness"] = _CARD_DB[opp_id].get("Weakness")
            
    for b in opp_player.get("bench", []):
        if b: 
            ret_cost = 0
            b_id = b.get("id")
            if b_id in _CARD_DB:
                try: ret_cost = int(_CARD_DB[b_id].get("Retreat", 0))
                except: pass
            state["opp_bench"].append({"id": b_id, "hp": b.get("hp", 0), "energy": len(b.get("energies", [])), "retreat": ret_cost})
            
    return state

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
        return my_deck

    options = select_data.get("option", [])
    if not options:
        return []

    _load_card_database()
    state = extract_state(obs_dict)

    # Pre-calculate if our current active's attacks are nullified by opponent's immunity
    attack_is_nullified = False
    if state and state.get("opp_active_id") and state.get("my_active_id"):
        opp_db = _CARD_DB.get(state["opp_active_id"], {})
        eff = opp_db.get("Effect Explanation", "")
        opp_immune_to_ex = ("Prevent all damage" in eff and "from" in eff and " ex" in eff.lower())
        opp_immune_to_abilities = ("Prevent all damage" in eff and "from" in eff and "Ability" in eff)
        
        my_db = _CARD_DB.get(state["my_active_id"], {})
        my_name = my_db.get("Card Name", "")
        my_cat = my_db.get("Category", "")
        my_eff = my_db.get("Effect Explanation", "")
        my_is_ex = (" ex" in my_name.lower() or my_db.get("ex") == "True" or my_db.get("megaEx") == "True")
        my_has_ability = ("Ability" in my_cat or "Ability" in my_eff or "Ability" in my_db.get("Move Name", ""))
        
        if opp_immune_to_ex and my_is_ex: attack_is_nullified = True
        if opp_immune_to_abilities and my_has_ability: attack_is_nullified = True

    context = select_data.get("context", "")

    scores = []
    for o in options:
        ot = o.get("type", "")
        score = 0.0

        if ot == "PLAY":
            score += W.get("base_play_score", 60000.0)
            cid = _get_card_id(obs_dict, o, state["my_idx"] if state else 0)
            
            # Late game Kangaskhan Ban
            if cid == Kangaskhan and state and state["my_prizes"] <= 3:
                # Exception: we need a lot of damage to win the game (e.g. against high HP threats)
                if state.get("opp_active_hp", 0) < 130:
                    score += W.get("play_kangaskhan_late_game_penalty", -100000.0)
                
            if cid in [1219, 1225]: # Jumbo Ice Cream or similar heal
                base = W.get("heal_jumbo_ice_cream_bonus", 5000.0)
                if state and state["my_active_hp"] > 0 and state["my_active_hp"] <= 60:
                    base *= W.get("panic_heal_multiplier", 2.5)
                score += base
            elif cid in [1182, 1187]: # Boss's Orders, Xerosic
                base = -500.0 # Penalty to not waste
                if state:
                    valid_boss = False
                    
                    # Determine our lethal threshold
                    my_id = state["my_active_id"]
                    lethal_threshold = 60
                    if my_id == Crustle: lethal_threshold = 130
                    elif my_id == Ogerpon: lethal_threshold = 140
                    elif my_id == Kangaskhan and state.get("my_active_energy", 0) >= 3: 
                        lethal_threshold = 100 # Can comfortably snipe weak targets
                    
                    can_lethal_active = (not attack_is_nullified and state.get("opp_active_hp", 0) > 0 and state.get("opp_active_hp", 0) <= lethal_threshold)
                    
                    if cid == 1182 and can_lethal_active:
                        # We ALREADY have a knockout on the active! Don't Boss away a free prize card!
                        base += W.get("play_boss_orders_lethal_active_penalty", -50000.0)
                    else:
                        if attack_is_nullified:
                            base += W.get("play_boss_orders_pivot_bonus", 20000.0) # High priority to pivot away from an immune wall
                        
                        valid_boss = False
                        # Snipe if they have a vulnerable Pokemon on bench
                        if any(0 < b["hp"] <= lethal_threshold for b in state["opp_bench"]): 
                            valid_boss = True # Snipe
                            
                        # Only allow walls to stall/evade! If Kangaskhan is out, only Boss if sniping!
                        if state.get("my_active_id") in [Crustle, Ogerpon]:
                            if state["opp_active_energy"] == 0 and any(b["energy"] >= 2 for b in state["opp_bench"]): 
                                valid_boss = True # Evasion
                            if state["my_active_energy"] < 2 and any(b["retreat"] >= 3 and b["energy"] == 0 for b in state["opp_bench"]): 
                                valid_boss = True # Stall
                            
                        if valid_boss:
                            base = W.get("play_boss_orders_disrupt_bonus", 4500.0)
                            # If their bench is tiny, bossing and knocking out is huge
                            if len(state["opp_bench"]) <= 1:
                                base += W.get("play_boss_orders_bench_out_bonus", 10000.0)
                            if state["opp_prizes"] <= 2:
                                base *= W.get("late_game_disrupt_multiplier", 2.0)
                            
                    if cid == 1187 and state.get("opp_hand_size", 0) >= 5: # Xerosic on big hand
                        base = W.get("play_xerosic_disrupt_bonus", 3000.0)
                score += base
            elif cid == 1123: # Switch
                score -= 200.0
                if state and state["my_active_id"] == Kangaskhan:
                    can_lethal_active = (not attack_is_nullified and state.get("opp_active_hp", 0) > 0 and state.get("opp_active_hp", 0) <= 100)
                    
                    if can_lethal_active:
                        # DO NOT switch if we are about to knock it out! Take the prize card!
                        score += W.get("switch_lethal_active_penalty", -50000.0)
                    else:
                        if attack_is_nullified:
                            score += W.get("switch_pivot_bonus", 20000.0) # MUST switch out of immune lock
                            
                        opp_is_ex = False
                        opp_has_ability = False
                        if state.get("opp_active_id"):
                            opp_db = _CARD_DB.get(state["opp_active_id"], {})
                            name = opp_db.get("Card Name", "")
                            eff = opp_db.get("Effect Explanation", "")
                            cat = opp_db.get("Category", "")
                            if " ex" in name or opp_db.get("ex") == "True" or opp_db.get("megaEx") == "True":
                                opp_is_ex = True
                            if "Ability" in cat or "Ability" in eff or "Ability" in opp_db.get("Move Name", ""):
                                opp_has_ability = True
                        
                        if opp_is_ex and any(b["id"] == Crustle and b["energy"] >= 2 for b in state["my_bench"]):
                            score += W.get("switch_to_crustle_ex_bonus", 8000.0)
                        elif opp_has_ability and not opp_is_ex and any(b["id"] == Ogerpon and b["energy"] >= 2 for b in state["my_bench"]):
                            score += W.get("switch_to_ogerpon_ability_bonus", 8000.0)
                        elif any(b["id"] in [Crustle, Ogerpon] and b["energy"] >= 2 for b in state["my_bench"]):
                            score += W.get("switch_to_wall_bonus", 5000.0)
            elif cid == 1227: # Lillie's Determination
                base = W.get("play_lillie_draw_bonus", 4000.0)
                if state and state["my_hand_size"] < 4: 
                    base += W.get("play_draw_supporter_bricking_bonus", 50000.0) # Exponential scale up to prevent bricking
                score += base
            elif cid == 1238: # Morty's Conviction
                score += W.get("play_morty_draw_bonus", 2000.0)
            elif cid == 1086: # Buddy-Buddy Poffin
                base = W.get("play_poffin_dwebble_bonus", 5000.0)
                if state and not any(b["id"] == Dwebble for b in state["my_bench"]):
                    base += 5000.0 # High priority if no Dwebbles
                score += base
            elif cid == 1257: # Community Center
                score += W.get("use_community_center_bonus", 2000.0)
            elif cid == 1197: # Team Rocket's Petrel
                base = W.get("play_petrel_bonus", 2000.0)
                if state and state.get("stadium_id") == 1242: # Factory is active
                    base += W.get("play_factory_petrel_combo_bonus", 6000.0)
                if state and state["my_hand_size"] < 4:
                    base += W.get("play_draw_supporter_bricking_bonus", 50000.0) # Exponential scale up to prevent bricking
                score += base
            elif cid == 1147: # Pokegear
                score += W.get("play_pokegear_bonus", 1000.0)
            elif cid == 1194: # Colress's Tenacity
                score += W.get("play_colress_tenacity_bonus", 3500.0)
            elif cid == 1225: # Hilda
                score += W.get("play_hilda_bonus", 3000.0)
            elif cid in [Dwebble, Crustle]:
                score += 500.0
            
        elif context == "SETUP_ACTIVE_POKEMON" or context == "TO_ACTIVE":
            cid = _get_card_id(obs_dict, o, state["my_idx"] if state else 0)
            
            # Evaluate opponent active attributes for proper wall deployment
            opp_is_ex = False
            opp_has_ability = False
            if state and state.get("opp_active_id"):
                opp_db = _CARD_DB.get(state["opp_active_id"], {})
                name = opp_db.get("Card Name", "")
                eff = opp_db.get("Effect Explanation", "")
                cat = opp_db.get("Category", "")
                if " ex" in name or opp_db.get("ex") == "True" or opp_db.get("megaEx") == "True":
                    opp_is_ex = True
                if "Ability" in cat or "Ability" in eff or "Ability" in opp_db.get("Move Name", ""):
                    opp_has_ability = True
                    
            if opp_is_ex and cid == Crustle:
                score += W.get("active_wall_ex_bonus", 20000.0) # High priority to wall EX
            elif opp_has_ability and not opp_is_ex and cid == Ogerpon:
                score += W.get("active_wall_ability_bonus", 20000.0) # High priority to wall Ability non-EX
            else:
                is_turn_2 = (state and state["turn"] == 1)
                has_crustle = (state and 345 in state["my_hand_ids"])
                if is_turn_2 and has_crustle and cid == Dwebble:
                    score += W.get("active_dwebble_has_crustle_bonus", 10000.0)
                elif cid == Kangaskhan:
                    score += W.get("play_kangaskhan_active_bonus", 5000.0)
                    
            # Heavily prioritize picking Pokemon that ALREADY have energy to avoid stranding unenergized ones
            target_idx = o.get("inPlayIndex", -1)
            if state and "my_bench" in state and 0 <= target_idx < len(state["my_bench"]):
                energy_on_card = state["my_bench"][target_idx]["energy"]
                score += energy_on_card * W.get("active_energy_multiplier", 10000.0)
                
        elif ot == "EVOLVE":
            score += W.get("base_evolve_score", 80000.0)
            score += W.get("evolve_dwebble_bonus", 5000.0)
        elif ot == "ATTACH":
            score += W.get("base_attach_score", 40000.0)
            target_area = o.get("inPlayArea") # if option is pokemon target
            target_idx = o.get("inPlayIndex", 0)
            is_active = (target_area == 4)
            is_bench = (target_area == 6)
            cid = _get_card_id(obs_dict, o, state["my_idx"] if state else 0)
            
            if cid == 1159: # Hero's Cape
                score += W.get("attach_hero_cape_crustle_bonus", 4000.0)
                
            if state:
                target_id = None
                target_energy = 0
                if is_active:
                    target_id = state["my_active_id"]
                    target_energy = state["my_active_energy"]
                elif is_bench and target_idx < len(state["my_bench"]):
                    target_id = state["my_bench"][target_idx]["id"]
                    target_energy = state["my_bench"][target_idx]["energy"]

                if target_id is not None:
                    # Kangaskhan, Crustle, and Ogerpon all only need 3 energy to attack.
                    # We count cards (so Double Colorless counts as 1). 
                    # Once they hit 3 cards, they are fully saturated and MUST NOT get more energy.
                    max_energy = 3
                    
                    if target_energy >= max_energy:
                        score += W.get("attach_energy_saturation_penalty_extreme", -100000.0) # Instantly lock priority below zero to force bench loading!
                    else:
                        if is_bench and target_id in [Crustle, Ogerpon]:
                            score += W.get("attach_bench_wall_bonus", 8000.0)
            score += W.get("attach_energy_ogerpon_bonus", 2000.0)
        elif ot == "RETREAT":
            score += W.get("base_retreat_score", 20000.0)
            retreat_cost = 0
            if state and state["my_active_id"] in _CARD_DB:
                try:
                    retreat_cost = int(_CARD_DB[state["my_active_id"]].get("Retreat", 0))
                except Exception:
                    pass
            score += (retreat_cost * W.get("retreat_cost_penalty", -1500.0))
            if state and state["my_active_id"] == Crustle:
                score += W.get("retreat_crustle_penalty", -2000.0)
        elif ot == "ATTACK":
            score += W.get("base_attack_score", 1000.0)
            if attack_is_nullified:
                score += W.get("attack_nullified_penalty", -100000.0) # NEVER attack if nullified
            elif state and state["opp_active_hp"] > 0:
                # Identify if we have lethal based on our main attackers
                can_lethal = False
                my_id = state["my_active_id"]
                hp = state["opp_active_hp"]
                if my_id == Crustle and hp <= 130: can_lethal = True
                elif my_id == Ogerpon and hp <= 140: can_lethal = True
                elif hp <= 60: can_lethal = True # Fallback for basic attacks
                
                if can_lethal:
                    lethal_score = W.get("attack_lethal_bonus", 5000.0)
                    
                    # Massively reward knockouts when they have few bench Pokemon
                    bench_count = len(state["opp_bench"])
                    if bench_count == 0:
                        lethal_score += W.get("attack_lethal_bench_0_bonus", 200000.0) # Instant bench-out win! Override all plays!
                    elif bench_count == 1:
                        lethal_score += W.get("attack_lethal_bench_1_bonus", 50000.0)  # Push for near bench-out
                    else:
                        lethal_score += W.get("attack_lethal_bench_2plus_bonus", 10000.0)  # General knockout is always great
                        
                    score += lethal_score
        elif o.get("inPlayArea") == 7:
            # Targeting Opponent Bench (e.g. Boss's Orders resolution)
            target_idx = o.get("inPlayIndex", -1)
            if state and "opp_bench" in state and 0 <= target_idx < len(state["opp_bench"]):
                hp = state["opp_bench"][target_idx]["hp"]
                score += W.get("target_bench_base_score", 10000.0) - hp # We want the lowest HP!
                
                my_id = state.get("my_active_id")
                lethal_threshold = 60
                if my_id == Crustle: lethal_threshold = 130
                elif my_id == Ogerpon: lethal_threshold = 140
                elif my_id == Kangaskhan and state.get("my_active_energy", 0) >= 3: 
                    lethal_threshold = 100
                    
                if hp <= lethal_threshold:
                    score += W.get("target_bench_lethal_bonus", 50000.0) # Huge bonus for picking a target we can one-shot!
        else:
            score += 1.0
            
        scores.append(score)

    # Sort descending by score
    desc_indices = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
    return desc_indices[:select_data.get("maxCount", 1)]

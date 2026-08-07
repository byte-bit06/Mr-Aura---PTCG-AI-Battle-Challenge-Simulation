"""
Wall_V10 Agent — Replay Winner Analytics Adaptation Engine
============================================================
Incorporates winning move-by-move analytics & dynamically tuned weights
learned from replay analysis into the Crustle Wall decision engine.
"""

import os
import sys
import json
import csv

# ── Card Database & Deck Loader ───────────────────────────────────────────────
_CARD_DB = {}
def _load_card_database():
    global _CARD_DB
    if _CARD_DB: return
    try:
        base_dir = os.path.dirname(__file__)
    except NameError:
        base_dir = "/kaggle_simulations/agent"
    for candidate in ["EN_Card_Data.csv", "data/EN_Card_Data.csv", "/kaggle_simulations/agent/EN_Card_Data.csv", "../data/EN_Card_Data.csv"]:
        for p in [candidate, os.path.join(base_dir, candidate)]:
            if os.path.exists(p):
                try:
                    with open(p, mode='r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            try:
                                cid = int(row["Card ID"])
                                _CARD_DB[cid] = row
                            except: pass
                    if _CARD_DB: return
                except: pass

def load_deck():
    try:
        dir_path = os.path.dirname(__file__)
        local_deck = os.path.join(dir_path, "deck.csv")
        if os.path.exists(local_deck):
            try:
                with open(local_deck) as f:
                    return [int(line) for line in f if line.strip()]
            except: pass
    except NameError:
        pass
    return [344]*4 + [345]*4 + [117]*3 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [1]*5 + [14]*3 + [20]*2

my_deck = load_deck()
_load_card_database()

try:
    from cg.api import all_card_data
    _CG_CARD_TABLE = {c.cardId: c for c in all_card_data()}
except Exception:
    _CG_CARD_TABLE = {}

def is_card_ex(cid):
    if not cid: return False
    c = _CG_CARD_TABLE.get(cid)
    if c: return getattr(c, 'ex', False) or getattr(c, 'megaEx', False)
    if cid in _CARD_DB: return str(_CARD_DB[cid].get("EX", "false")).lower() == "true"
    return False

def card_has_ability(cid):
    if not cid: return False
    c = _CG_CARD_TABLE.get(cid)
    if c: return len(getattr(c, 'abilities', [])) > 0 or getattr(c, 'ability', None) is not None
    if cid in _CARD_DB: return len(_CARD_DB[cid].get("Abilities", [])) > 0
    return False

# ── Card Constants ─────────────────────────────────────────────────────────────
Dwebble = 344
Crustle = 345
Ogerpon = 117
SwitchCard = 14
BossOrders = 20
HerosCape = 1242
Petrel = 1194
Lillie = 1225
JumboIceCream = 1187
CommunityCenter = 1197
Xerosic = 1257
Morty = 1123
TRFactory = 1159
GrassEnergy = 18
MistEnergy = 11
NestBall = 1122
UltraBall = 1147
HeavyBall = 1086
BuddyPuffin = 1121
EarthenVessel = 1227
Iono = 1182
Arven = 1219

# ── Weights Loader ─────────────────────────────────────────────────────────────
_WEIGHT_DEFAULTS = {
    "W_PRIZE_MULT":             1050,
    "W_ENERGY_SCORE":            180,
    "W_TOOL_SCORE":              120,
    "W_STAGE2_SCORE":            280,
    "W_STAGE1_SCORE":            150,
    "W_ACTIVE_BONUS":            250,
    "W_TARGET_ACTIVE_BONUS":     350,
    "W_ENERGY_ACTIVE_BIAS":       15,
    "W_ENERGY_BASE":            8500,
    "W_ENERGY_NEED_BONUS":       120,
    "W_ENERGY_SURPLUS_PENALTY":   50,
    "W_EVOLVE_BASE":            9500,
    "W_TRAINER_BASE":          10500,
    "W_POKEMON_BASE":          20000,
    "W_RETREAT_SCORE":          1800,
    "W_ATTACK_SCORE":           1250,
}

def _load_weights():
    try:
        base_dir = os.path.dirname(__file__)
    except NameError:
        base_dir = "/kaggle_simulations/agent"
    for w_path in ["optimized_weights.json", os.path.join(base_dir, "optimized_weights.json")]:
        if os.path.exists(w_path):
            try:
                with open(w_path) as f:
                    data = json.load(f)
                merged = dict(_WEIGHT_DEFAULTS)
                merged.update({k: v for k, v in data.items() if k in _WEIGHT_DEFAULTS})
                return merged
            except: pass
    return dict(_WEIGHT_DEFAULTS)

W = _load_weights()

# ── Board Info Extractor ───────────────────────────────────────────────────────
def extract_board_info(obs_dict):
    current = obs_dict.get("current")
    if not current: return {}
    
    my_idx = current.get("yourIndex", 0)
    opp_idx = 1 - my_idx
    
    my_player = current["players"][my_idx]
    opp_player = current["players"][opp_idx]
    
    hand = [c.get("id") for c in my_player.get("hand", []) if "id" in c]
    
    my_active_list = my_player.get("active", [])
    my_active = my_active_list[0] if len(my_active_list) > 0 else None
    
    opp_active_list = opp_player.get("active", [])
    opp_active = opp_active_list[0] if len(opp_active_list) > 0 else None
    
    my_bench = [b for b in my_player.get("bench", []) if b]
    opp_bench = [b for b in opp_player.get("bench", []) if b]
    
    opp_active_id = opp_active.get("id") if opp_active else None
    opp_is_ex = is_card_ex(opp_active_id)
    opp_has_ability = card_has_ability(opp_active_id)

    if opp_is_ex:
        optimal_active = Crustle
    elif opp_has_ability:
        optimal_active = Ogerpon
    else:
        optimal_active = Crustle

    turn = current.get("turn", 1)
    opp_hand_raw = opp_player.get("hand")
    opp_hand_count = opp_player.get("handCount") if opp_player.get("handCount") is not None else len(opp_hand_raw if opp_hand_raw else [])
    
    return {
        "my_idx": my_idx,
        "turn": turn,
        "hand": hand,
        "hand_size": my_player.get("handCount", len(hand)),
        "my_active": my_active,
        "my_active_id": my_active.get("id") if my_active else None,
        "my_active_hp": my_active.get("hp", 0) if my_active else 0,
        "my_active_max_hp": my_active.get("maxHp", 0) if my_active else 0,
        "my_active_energy": len(my_active.get("energies", [])) if my_active else 0,
        "my_bench": my_bench,
        "opp_active": opp_active,
        "opp_active_id": opp_active_id,
        "opp_active_hp": opp_active.get("hp", 0) if opp_active else 0,
        "opp_bench": opp_bench,
        "opp_is_ex": opp_is_ex,
        "opp_has_ability": opp_has_ability,
        "opp_hand_count": opp_hand_count,
        "optimal_active": optimal_active,
        "my_prizes": len(my_player.get("prize", [])),
        "opp_prizes": len(opp_player.get("prize", [])),
    }

def sanitize_action(chosen_indices: list[int], select_data: dict) -> list[int]:
    options = select_data.get("option", [])
    n_opts = len(options)
    if n_opts == 0:
        return [0]

    max_count = select_data.get("maxCount", 1)
    min_count = select_data.get("minCount", 1)

    # 1. Unique sampling without replacement (preserve option priority)
    unique = []
    for idx in chosen_indices:
        if 0 <= idx < n_opts and idx not in unique:
            unique.append(idx)

    # 2. Fill with remaining available unique indices if below minCount
    if len(unique) < min_count:
        for i in range(n_opts):
            if i not in unique:
                unique.append(i)
                if len(unique) >= min_count:
                    break

    # 3. Enforce action length bounds: minCount <= len(action) <= maxCount
    target_count = min(max_count, max(min_count, len(unique)))
    return unique[:target_count]

# ── Main Agent Entry Point ────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None:
        if obs_dict.get("step", 0) == 0:
            return my_deck
        return []

    options = select_data.get("option")
    if not options:
        return [0]

    current = obs_dict.get("current")

    # Handle Pre-Game Preparation Phase (Coin toss, IsFirst, Pre-game setup when current is None)
    if current is None:
        return sanitize_action([0], select_data)

    info = extract_board_info(obs_dict)
    context = select_data.get("context", "")

    # Phase 1: Setup / Mulligan Lead Selection
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper() or "FIRST" in str(context).upper():
        optimal_lead = info.get("optimal_active", Crustle)
        for lead_choice in [optimal_lead, Dwebble, Ogerpon]:
            for idx, o in enumerate(options):
                cid = o.get("cardId") or o.get("id")
                if cid == lead_choice:
                    return sanitize_action([idx], select_data)
        return sanitize_action([0], select_data)

    # Phase 2: Scored Option Engine
    scored_options = []
    my_active_id = info.get("my_active_id")
    my_energy = info.get("my_active_energy", 0)
    opp_hp = info.get("opp_active_hp", 999)
    opp_bench = info.get("opp_bench", [])

    my_dmg = 0
    if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
    elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140

    for idx, o in enumerate(options):
        score = 0
        ot = str(o.get("type", "")).upper()

        # ATTACK
        if "ATTACK" in ot or ot in ["5"]:
            score = W["W_ATTACK_SCORE"] + (6 - info.get("my_prizes", 6)) * W["W_PRIZE_MULT"]
            # Lethal KO bonus
            if my_dmg >= opp_hp and opp_hp > 0:
                score += 50000
            # Bench-out finish bonus
            if len(opp_bench) == 0:
                score += 200000

        # ATTACH ENERGY
        elif "ATTACH" in ot or ot in ["4"]:
            score = W["W_ENERGY_BASE"] + W["W_ENERGY_NEED_BONUS"]
            if my_energy < 3:
                score += W["W_ENERGY_ACTIVE_BIAS"] * 100

        # EVOLVE / PLAY
        elif "PLAY" in ot or ot in ["1", "3"]:
            score = W["W_EVOLVE_BASE"] + W["W_TRAINER_BASE"]

        # RETREAT
        elif "RETREAT" in ot or ot in ["6"]:
            score = W["W_RETREAT_SCORE"]

        # ABILITY
        elif "ABILITY" in ot or ot in ["2"]:
            score = 15000

        else:
            score = 100

        scored_options.append((score, idx))

    scored_options.sort(key=lambda x: x[0], reverse=True)
    desc_indices = [i for _, i in scored_options]
    return sanitize_action(desc_indices, select_data)

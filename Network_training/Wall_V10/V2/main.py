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
        base_dir = os.path.dirname(__file__)
    except NameError:
        base_dir = "/kaggle_simulations/agent"
    for p in [os.path.join(base_dir, "deck.csv"), "deck.csv", "/kaggle_simulations/agent/deck.csv"]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    cards = [int(line) for line in f if line.strip()]
                    if len(cards) == 60: return cards
            except: pass
    return [344]*4 + [345]*3 + [756]*2 + [117]*2 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [1]*5 + [14]*3 + [20]*2

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
    for w_path in [os.path.join(base_dir, "optimized_weights.json"),
                   "optimized_weights.json",
                   "/kaggle_simulations/agent/optimized_weights.json"]:
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

def _get_val(obj, key, default=None):
    if not obj: return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def rank_active_candidate(pokemon, optimal_active_id):
    if not pokemon: return -999999.0
    cid = _get_val(pokemon, "id")
    hp = _get_val(pokemon, "hp", 0)
    energies = _get_val(pokemon, "energies") or []
    energy_count = len(energies)
    
    # Fix 4: Active Promotion Rank Function
    # Score = (Energy Attached * 3000) + (Current HP * 100) - (Is Combo Piece * 5000)
    is_combo_piece = 1 if (cid == Dwebble and energy_count == 0) else 0
    score = (energy_count * 3000.0) + (hp * 100.0) - (is_combo_piece * 5000.0)
    
    if cid == optimal_active_id:
        score += 10000.0  # Bonus for matching optimal active wall
    return score

def score_discard_option(cid, hand, bench_and_active_ids):
    # Fix 2: Discard Penalty Matrix
    # High Discard Penalty (-50,000): Win-condition Supporters & key evolution targets
    if cid in {BossOrders, Iono, Lillie, Arven}:
        return -50000.0
    if cid == Crustle and Dwebble in bench_and_active_ids:
        return -50000.0  # Don't discard evolution matching benched Dwebble!
    if cid in {Ogerpon, Kangaskhan} and cid not in bench_and_active_ids:
        return -40000.0

    # Low Discard Penalty: Extra Energy cards or duplicate basic search items
    grass_cnt = hand.count(GrassEnergy) if isinstance(hand, list) else 0
    mist_cnt = hand.count(MistEnergy) if isinstance(hand, list) else 0
    if cid in {GrassEnergy, MistEnergy} and (grass_cnt + mist_cnt > 2):
        return 10000.0  # Safe energy discard
    if isinstance(hand, list) and hand.count(cid) > 1:
        return 8000.0   # Safe duplicate item discard

    return 1000.0

def score_search_option(cid, hand, bench_and_active_ids, bench_count):
    # Fix 1: Search Prerequisite Masking
    # Rule 1: Mask Stage 1 evolution if no matching Basic is in play!
    if cid == Crustle and Dwebble not in bench_and_active_ids:
        return -50000.0  # Mask unplayable evolution card!
    
    # Rule 2: Prioritize Dwebble if Dwebble is missing from play!
    if cid == Dwebble and Dwebble not in bench_and_active_ids:
        return 180000.0  # High priority search for missing basic!
    
    # Rule 3: Prioritize Crustle if Dwebble IS on bench!
    if cid == Crustle and Dwebble in bench_and_active_ids:
        return 190000.0  # Search ready-to-evolve Stage 1!
    
    # Rule 4: Mask redundant basic search if bench is full
    if cid in bench_and_active_ids and bench_count >= 5:
        return -20000.0
        
    return 10000.0

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

    try:
        info = extract_board_info(obs_dict)
        context = select_data.get("context", "")
        context_str = str(context).upper()

        # Fix 4: Active Promotion Rank Function (Setup / Active Promotion Phase)
        if "SETUP" in context_str or "ACTIVE" in context_str or "SWITCH" in context_str or "FIRST" in context_str:
            optimal_lead = info.get("optimal_active", Crustle)
            my_bench = info.get("my_bench", [])
            
            # Rank candidates using Active Promotion Rank Function
            best_idx = 0
            best_rank = -999999.0
            for idx, o in enumerate(options):
                cid = o.get("cardId") or o.get("id")
                # Check option candidate match in bench or hand
                matched_pkmn = None
                for b in my_bench:
                    if _get_val(b, "id") == cid:
                        matched_pkmn = b
                        break
                r_score = rank_active_candidate(matched_pkmn, optimal_lead) if matched_pkmn else 0.0
                if cid == optimal_lead: r_score += 20000.0
                elif cid == Dwebble: r_score += 15000.0
                elif cid == Ogerpon: r_score += 10000.0

                if r_score > best_rank:
                    best_rank = r_score
                    best_idx = idx

            return sanitize_action([best_idx], select_data)

        # Phase 2: Scored Option Engine & Strict Turn Hierarchy
        scored_options = []
        my_active = info.get("my_active")
        my_active_id = info.get("my_active_id")
        my_hp = info.get("my_active_hp", 0)
        my_max_hp = info.get("my_active_max_hp", 1)
        hp_pct = my_hp / float(my_max_hp) if my_max_hp > 0 else 1.0
        my_energy = info.get("my_active_energy", 0)
        opp_hp = info.get("opp_active_hp", 999)
        opp_bench = info.get("opp_bench", [])
        hand = info.get("hand", [])
        my_bench = info.get("my_bench", [])
        bench_count = len(my_bench)

        bench_and_active_ids = [_get_val(b, "id") for b in my_bench if _get_val(b, "id")]
        if my_active_id: bench_and_active_ids.append(my_active_id)

        # Calculate expected attack damage
        my_dmg = 0
        if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
        elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140
        elif my_active_id == Kangaskhan and my_energy >= 3: my_dmg = 100

        # Track pre-attack useful actions to penalize premature END turn
        has_useful_pre_attack_action = False

        for idx, o in enumerate(options):
            score = 0.0
            o_type = o.get("type", -1)
            ot_str = str(o_type).upper()
            cid = o.get("cardId") or o.get("id") or o.get("cardIdActive") or o.get("cardIdTarget")

            # Context Check for Discard / Search selections
            if "DISCARD" in context_str:
                score = score_discard_option(cid, hand, bench_and_active_ids)
            elif "SEARCH" in context_str or "DECK" in context_str:
                score = score_search_option(cid, hand, bench_and_active_ids, bench_count)

            # ── Fix 3: Early-Bench Priority Heuristic (Play Basics to Bench BEFORE Supporters!) ──
            elif (o_type in {1, 7} or "PLAY" in ot_str) and cid in {Dwebble, Ogerpon, Kangaskhan} and bench_count < 5:
                score = 180000.0  # Top Early Turn Priority! Starts 1-turn evolution clock!
                has_useful_pre_attack_action = True

            # ── 1. DRAW & SEARCH SUPPORTERS (Priority 1: Play early to draw cards!) ──
            elif o_type in {7, 3} and cid in {Lillie, Carmine, Arven, Iono, Pokégear, BuddyPuffin, NestBall, UltraBall, HeavyBall, EarthenVessel}:
                score = 120000.0
                has_useful_pre_attack_action = True

            # ── 2. EVOLUTION (Priority 2: Evolve Dwebble to Crustle) ──
            elif (o_type in {6, 7, 9} or "EVOLVE" in ot_str) and (cid == Crustle):
                score = 140000.0  # Instant Crustle evolution wall!
                has_useful_pre_attack_action = True

            # ── 3. FOCUSED ENERGY ATTACHMENT (Priority 3: Primary Attacker Focus!) ──
            elif o_type in {8, 4} or "ATTACH" in ot_str:
                in_play_area = o.get("inPlayArea")
                in_play_idx = o.get("inPlayIndex", 0)
                is_active_target = (in_play_area in {3, 4, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
                
                # Determine current energy on target Pokemon
                if is_active_target:
                    target_energy = my_energy
                else:
                    target_energy = 0
                    if in_play_idx is not None and 0 <= in_play_idx < len(my_bench):
                        b_pkmn = my_bench[in_play_idx]
                        b_energies = _get_val(b_pkmn, "energies") or []
                        target_energy = len(b_energies)

                # Hard Stop: Absolute block on energy attachment if target already has 3+ energy
                if target_energy >= 3:
                    score = -999999.0  # HARD BAN surplus energy beyond 3 (hoarding prevention)
                elif is_active_target:
                    score = 85000.0 + (3 - target_energy) * 10000.0  # Active Attacker focus
                    if is_card_ex(my_active_id):
                        score += 20000.0
                else:
                    # Benched target with < 3 energy
                    if my_energy < 3:
                        score = 10000.0  # Active needs energy first! Do NOT spread!
                    else:
                        score = 35000.0  # Active powered, energy to benched attacker!
                has_useful_pre_attack_action = True

            # ── 4. STADIUMS, HEALING & ABILITIES (Priority 4) ──
            elif o_type in {7, 10} or cid in {CommunityCenter, JumboIceCream, TRFactory, HerosCape, Xerosic, Petrel}:
                score = 50000.0
                has_useful_pre_attack_action = True

            # ── 5. ATTACKING (Priority 5 & Fix 5: Recoil & Damage Efficiency Check) ──
            elif o_type in {13, 5} or "ATTACK" in ot_str:
                # Fix 5: Recoil Check
                recoil_dmg = _get_val(o, "recoilDamage", 0) or _get_val(o, "selfDamage", 0)
                if recoil_dmg > 0 and (recoil_dmg >= my_hp or (my_dmg < 20 and my_dmg < opp_hp)):
                    score = -999999.0  # Mask inefficient / suicidal recoil attack!
                else:
                    score = 75000.0 + W["W_ATTACK_SCORE"] + (6 - info.get("my_prizes", 6)) * W["W_PRIZE_MULT"]
                    if my_dmg >= opp_hp and opp_hp > 0:
                        score += 50000.0  # Lethal KO bonus
                    if len(opp_bench) == 0:
                        score += 200000.0  # Bench-out finish bonus

            # ── 6. PANIC RETREAT GUARD (Mask Out Unless Low HP / Special Condition) ──
            elif o_type in {12, 8} or "RETREAT" in ot_str:
                is_special_condition = any([
                    _get_val(my_active, "poisoned"),
                    _get_val(my_active, "burned"),
                    _get_val(my_active, "asleep"),
                    _get_val(my_active, "confused"),
                    _get_val(my_active, "paralyzed")
                ])
                if hp_pct < 0.30 or is_special_condition:
                    score = 15000.0  # Legitimate emergency retreat!
                else:
                    score = -999999.0  # HARD BAN PANIC RETREAT! Save energy & active wall!

            # ── 7. END TURN (Priority 6: Mask/Penalize if useful actions remain) ──
            elif o_type in {14} or "END" in ot_str:
                if has_useful_pre_attack_action:
                    score = -100000.0  # Mask End Turn when net-positive actions remain!
                else:
                    score = -500.0

            else:
                score = 100.0

            scored_options.append((score, idx))

        scored_options.sort(key=lambda x: x[0], reverse=True)
        desc_indices = [i for _, i in scored_options]
        return sanitize_action(desc_indices, select_data)
    except Exception:
        return sanitize_action([0], select_data)

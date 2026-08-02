"""
Wall_V10 Agent — Replay Winner Analytics Adaptation Engine (V2 Normalized Engine)
================================================================================
Incorporates winning move-by-move analytics & dynamically tuned weights
learned from replay analysis into the Crustle/Ogerpon Wall decision engine.

Key Principles:
  - Mathematically Normalized Scoring Engine (Feature values bounded in [0.0, 1.0]).
  - Strict Priority Tiers with Weight Modulation (W parameters properly scale subscores).
  - Crustle Wall: Blocks all Pokémon ex (takes no damage from ex).
  - Ogerpon Wall: Blocks all Pokémon with abilities (Cornerstone Mask Ogerpon ex).
  - Early-Game Kangaskhan ex: Rush early KOs before opponent sets up.
  - Late-Game Hard Ban: -float('inf') ban on playing, promoting, or energizing Kangaskhan in late game.
  - Hard Limits: Uses -float('inf') for absolute non-negotiable bans.
"""

import os
import sys
import json
import csv
from math import inf

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
Kangaskhan = 756
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

# ── Weights Loader & Normalization Scale ───────────────────────────────────────
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

# Normalized Weight Coefficients (Scaled to ~ [0.1, 2.0] for balanced weight modulation)
w_prize   = W.get("W_PRIZE_MULT", 1050) / 1000.0
w_energy  = W.get("W_ENERGY_BASE", 8500) / 10000.0
w_evolve  = W.get("W_EVOLVE_BASE", 9500) / 10000.0
w_trainer = W.get("W_TRAINER_BASE", 10500) / 10000.0
w_pokemon = W.get("W_POKEMON_BASE", 20000) / 20000.0
w_attack  = W.get("W_ATTACK_SCORE", 1250) / 1000.0
w_retreat = W.get("W_RETREAT_SCORE", 1800) / 1000.0
w_tool    = W.get("W_TOOL_SCORE", 120) / 1000.0

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

    if not opp_is_ex:
        for b in opp_bench:
            bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
            if is_card_ex(bid):
                opp_is_ex = True
                break
    if not opp_has_ability:
        for b in opp_bench:
            bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
            if card_has_ability(bid):
                opp_has_ability = True
                break

    # Wall Method Selection:
    # 1. If Opponent has EX Pokémon -> Crustle wall blocks EXs
    # 2. If Opponent has Ability Pokémon -> Ogerpon wall blocks Ability Pokémon
    # 3. Otherwise default to Crustle
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

def rank_active_candidate(pokemon, optimal_active_id, is_early_game=False):
    if not pokemon: return -float('inf')
    cid = _get_val(pokemon, "id")
    hp = _get_val(pokemon, "hp", 0)
    max_hp = _get_val(pokemon, "maxHp", 200) or 200
    energies = _get_val(pokemon, "energies") or []
    energy_count = len(energies)
    
    # HARD BAN: Never promote Kangaskhan ex to active in late game!
    if cid == Kangaskhan and not is_early_game:
        return -float('inf')
    
    # Normalized Subscore (bounded in 0.0 - 100.0 range)
    energy_norm = min(energy_count / 3.0, 1.0)
    hp_norm = min(hp / float(max_hp), 1.0) if max_hp > 0 else 0.5
    is_combo_piece = 1.0 if (cid == Dwebble and energy_count == 0) else 0.0
    
    score = (energy_norm * 30.0) + (hp_norm * 20.0) - (is_combo_piece * 25.0)
    
    if cid == optimal_active_id:
        score += 100.0  # Optimal wall match (Crustle vs EX, Ogerpon vs Ability)
    elif cid == Dwebble:
        score += 75.0
    elif cid == Ogerpon:
        score += 60.0
    elif cid == Kangaskhan and is_early_game:
        score += 50.0   # Early game aggressive KO pressure
    return score

def score_discard_option(cid, hand, bench_and_active_ids):
    # Normalized Discard Scores (-10.0 to +2.0 scale)
    if cid in {BossOrders, Iono, Lillie, Arven}:
        return -10.0
    if cid == Crustle and Dwebble in bench_and_active_ids:
        return -10.0  # Don't discard evolution matching benched Dwebble!
    if cid in {Ogerpon, Kangaskhan} and cid not in bench_and_active_ids:
        return -8.0

    grass_cnt = hand.count(GrassEnergy) if isinstance(hand, list) else 0
    mist_cnt = hand.count(MistEnergy) if isinstance(hand, list) else 0
    if cid in {GrassEnergy, MistEnergy} and (grass_cnt + mist_cnt > 2):
        return 2.0  # Safe energy discard
    if isinstance(hand, list) and hand.count(cid) > 1:
        return 1.5  # Safe duplicate item discard

    return 0.0

def score_search_option(cid, hand, bench_and_active_ids, bench_count, is_early_game=True):
    # Normalized Search Scores (-10.0 to +10.0 scale)
    if cid == Crustle and Dwebble not in bench_and_active_ids:
        return -10.0  # Mask unplayable evolution card!
    
    if cid == Dwebble and Dwebble not in bench_and_active_ids:
        return 9.0  # High priority search for missing basic!
    
    if cid == Crustle and Dwebble in bench_and_active_ids:
        return 10.0  # Search ready-to-evolve Stage 1!
    
    if cid == Kangaskhan and not is_early_game:
        return -float('inf')

    if cid in bench_and_active_ids and bench_count >= 5:
        return -4.0
        
    return 1.0

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

    # Handle Pre-Game Preparation Phase
    if current is None:
        return sanitize_action([0], select_data)

    try:
        info = extract_board_info(obs_dict)
        context = select_data.get("context", "")
        context_str = str(context).upper()

        turn_num = info.get("turn", 1)
        my_prizes = info.get("my_prizes", 6)
        hand_size = info.get("hand_size", 5)
        is_early_game = (turn_num <= 4 or my_prizes >= 5)

        # Active Promotion Rank Function (Setup / Active Promotion Phase)
        if "SETUP" in context_str or "ACTIVE" in context_str or "SWITCH" in context_str or "FIRST" in context_str:
            optimal_lead = info.get("optimal_active", Crustle)
            my_bench = info.get("my_bench", [])
            
            best_idx = 0
            best_rank = -float('inf')
            for idx, o in enumerate(options):
                cid = o.get("cardId") or o.get("id")
                matched_pkmn = None
                for b in my_bench:
                    if _get_val(b, "id") == cid:
                        matched_pkmn = b
                        break
                r_score = rank_active_candidate(matched_pkmn, optimal_lead, is_early_game) if matched_pkmn else 0.0
                if cid == optimal_lead:
                    r_score += 100.0
                elif cid == Dwebble:
                    r_score += 75.0
                elif cid == Ogerpon:
                    r_score += 60.0
                elif cid == Kangaskhan:
                    if is_early_game:
                        r_score += 50.0
                    else:
                        r_score = -float('inf')  # HARD BAN Kangaskhan active promotion in late game!

                if r_score > best_rank:
                    best_rank = r_score
                    best_idx = idx

            return sanitize_action([best_idx], select_data)

        # Scored Option Engine & Normalized Priority Tiers
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
        optimal_lead = info.get("optimal_active", Crustle)

        bench_and_active_ids = [_get_val(b, "id") for b in my_bench if _get_val(b, "id")]
        if my_active_id: bench_and_active_ids.append(my_active_id)

        # Calculate expected attack damage
        my_dmg = 0
        if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
        elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140
        elif my_active_id == Kangaskhan and my_energy >= 3: my_dmg = 100

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
                score = score_search_option(cid, hand, bench_and_active_ids, bench_count, is_early_game)

            # ── TIER 8 (Base 800.0): EARLY BENCH PRIORITY (Play Basics to Bench) ──
            elif (o_type in {1, 7} or "PLAY" in ot_str) and cid in {Dwebble, Ogerpon, Kangaskhan} and bench_count < 5:
                if cid == Kangaskhan and not is_early_game:
                    score = -float('inf')  # HARD BAN playing Kangaskhan ex in late game!
                elif cid == Ogerpon and optimal_lead == Ogerpon:
                    subscore = w_pokemon * 5.0 + ((5 - bench_count) / 5.0) * 2.0 + 3.0  # High priority vs Ability opponents
                    score = 800.0 + subscore
                    has_useful_pre_attack_action = True
                else:
                    subscore = w_pokemon * 5.0 + ((5 - bench_count) / 5.0) * 2.0
                    score = 800.0 + subscore
                    has_useful_pre_attack_action = True

            # ── TIER 7 (Base 700.0): EVOLUTION (Evolve Dwebble to Crustle) ──
            elif (o_type in {6, 7, 9} or "EVOLVE" in ot_str) and (cid == Crustle):
                subscore = w_evolve * 5.0 + (3.0 if optimal_lead == Crustle else 0.0)
                score = 700.0 + subscore
                has_useful_pre_attack_action = True

            # ── TIER 6 (Base 600.0): DRAW & SEARCH SUPPORTERS ──
            elif o_type in {7, 3} and cid in {Lillie, Carmine, Arven, Iono, Pokégear, BuddyPuffin, NestBall, UltraBall, HeavyBall, EarthenVessel}:
                subscore = w_trainer * 5.0 + (3.0 if hand_size <= 3 else 1.0)
                score = 600.0 + subscore
                has_useful_pre_attack_action = True

            # ── TIER 5 (Base 500.0): FOCUSED ENERGY ATTACHMENT ──
            elif o_type in {8, 4} or "ATTACH" in ot_str:
                in_play_area = o.get("inPlayArea")
                in_play_idx = o.get("inPlayIndex", 0)
                is_active_target = (in_play_area in {3, 4, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
                
                target_cid = my_active_id if is_active_target else None
                target_energy = my_energy if is_active_target else 0
                
                if not is_active_target:
                    if in_play_idx is not None and 0 <= in_play_idx < len(my_bench):
                        b_pkmn = my_bench[in_play_idx]
                        target_cid = _get_val(b_pkmn, "id")
                        b_energies = _get_val(b_pkmn, "energies") or []
                        target_energy = len(b_energies)

                # HARD BAN: Never attach energy to Kangaskhan ex in late game!
                if target_cid == Kangaskhan and not is_early_game:
                    score = -float('inf')
                # HARD BAN: Absolute block on energy attachment if target already has 3+ energy (hoarding prevention)
                elif target_energy >= 3:
                    score = -float('inf')
                elif is_active_target:
                    need_norm = (3 - target_energy) / 3.0
                    subscore = w_energy * 5.0 + need_norm * 3.0 + (1.0 if is_card_ex(my_active_id) else 0.0)
                    score = 500.0 + subscore
                else:
                    # Benched target with < 3 energy
                    if my_energy < 3:
                        score = 100.0  # Active needs energy first! Do NOT spread!
                    else:
                        need_norm = (3 - target_energy) / 3.0
                        subscore = w_energy * 2.5 + need_norm * 1.5
                        score = 500.0 + subscore
                has_useful_pre_attack_action = True

            # ── TIER 4 (Base 400.0): ATTACKING ──
            elif o_type in {13, 5} or "ATTACK" in ot_str:
                recoil_dmg = _get_val(o, "recoilDamage", 0) or _get_val(o, "selfDamage", 0)
                if recoil_dmg > 0 and (recoil_dmg >= my_hp or (my_dmg < 20 and my_dmg < opp_hp)):
                    score = -float('inf')  # Mask suicidal or inefficient recoil attack!
                else:
                    prize_norm = (6 - my_prizes) / 6.0
                    subscore = w_attack * 5.0 + w_prize * prize_norm * 3.0
                    if my_dmg >= opp_hp and opp_hp > 0:
                        subscore += 5.0  # Lethal KO bonus
                    if len(opp_bench) == 0:
                        subscore += 10.0  # Bench-out finish bonus
                    score = 400.0 + subscore

            # ── TIER 3 (Base 300.0): STADIUMS, HEALING & TOOLS ──
            elif o_type in {7, 10} or cid in {CommunityCenter, JumboIceCream, TRFactory, HerosCape, Xerosic, Petrel}:
                subscore = w_tool * 5.0
                score = 300.0 + subscore
                has_useful_pre_attack_action = True

            # ── TIER 2 (Base 200.0): EMERGENCY RETREAT ──
            elif o_type in {12, 8} or "RETREAT" in ot_str:
                is_special_condition = any([
                    _get_val(my_active, "poisoned"),
                    _get_val(my_active, "burned"),
                    _get_val(my_active, "asleep"),
                    _get_val(my_active, "confused"),
                    _get_val(my_active, "paralyzed")
                ])
                if hp_pct < 0.30 or is_special_condition:
                    subscore = w_retreat * 5.0 + (1.0 - hp_pct) * 3.0
                    score = 200.0 + subscore  # Emergency retreat!
                else:
                    score = -float('inf')  # HARD BAN panic retreat! Preserve active wall & energy!

            # ── TIER 1 (Base 100.0): NEUTRAL / MISCELLANEOUS ──
            elif o_type in {14} or "END" in ot_str:
                if has_useful_pre_attack_action:
                    score = -50.0  # Penalize ending turn when useful actions remain!
                else:
                    score = 0.0

            else:
                score = 100.0

            scored_options.append((score, idx))

        scored_options.sort(key=lambda x: x[0], reverse=True)
        desc_indices = [i for _, i in scored_options]
        return sanitize_action(desc_indices, select_data)
    except Exception:
        return sanitize_action([0], select_data)

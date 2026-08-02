"""
Wall_V10 Agent — Replay Winner Analytics Adaptation Engine (V2 Strict Rules Engine)
====================================================================================
Incorporates winning move-by-move analytics & strict hard-coded strategic rules:

Hard-Coded Strategic Directives (Fully resolved via position-to-card ID resolver):
  1. Early-Game Kangaskhan Active Lead: Kangaskhan ex is ALWAYS prioritized as active lead in early game (Turn 0 setup) for aggressive early KOs.
  2. Pokégear 3.0 Restriction: Never play Pokégear 3.0 if a supporter is already in hand or played this turn.
     - Pokégear Search Selection: ALWAYS prioritize Lillie (Score: 80,000) over any other Supporter in Pokégear top 7.
  3. Early-Game Dwebble Priority: Put Dwebble down immediately and prioritize searching Dwebble until AT LEAST 2 are in play (Score: 100,000). Once 2 Dwebble/Crustle are in play, stop searching Dwebble and pivot to Crustle/Ogerpon.
  4. Opening Hand Energy Attachment: If opening hand lacks Dwebble/Ogerpon/search items, attach any energy in hand immediately.
  5. Lillie Supporter Sequencing: Always play all playable Pokémon, evolutions, and items BEFORE playing Lillie.
  6. Ultra Ball Restriction: Only play Ultra Ball if needed to get Dwebble (< 2 in play), or to find Crustle / Ogerpon when needed.
  7. Retreat Guard & Wall Safety: Never retreat if active takes 0 damage (walling). Only retreat if active takes damage AND a benched wall takes 0 damage.
  8. Ogerpon Bench Limit: Never play more than 2 Ogerpon unless opponent active has an ability.
  9. Boss's Orders Strict Conditions: Only play Boss's Orders if active has >= 3 energy AND can KO a benched target that has higher prize value or >= 2 more energy than opponent active.
"""

import os
import sys
import json
import csv
from math import inf

RULE_LOG_FILE = os.path.join(os.path.dirname(__file__), "live_rule_executions.log")

def log_rule_execution(msg):
    sys.stderr.write(f"{msg}\n")
    try:
        with open(RULE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass

# Clear old log file on start
try:
    with open(RULE_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== WALL_V10 V2 IF-STATEMENT & STRATEGIC RULE EXECUTION LOG ===\n\n")
except Exception:
    pass

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

# ── Correct Card Constants ─────────────────────────────────────────────────────
Dwebble       = 344
Crustle       = 345
Ogerpon       = 117
Kangaskhan    = 756
SwitchCard    = 1123
BossOrders    = 1182
HerosCape     = 1159
Petrel        = 1219
Lillie        = 1227
Hilda         = 1225
Colress       = 1194
Morty         = 1187
Xerosic       = 1197
JumboIceCream = 1147
CommunityCenter = 1242
TRFactory     = 1257
GrassEnergy   = 1
MistEnergy    = 11
SpikyEnergy   = 14
RockEnergy    = 20
UltraBall     = 1121
BuddyPuffin   = 1086
Pokégear      = 1122

SUPPORTERS_SET = {Lillie, Petrel, Hilda, Colress, Morty, Xerosic, BossOrders}

def get_card_name(cid):
    if not cid: return "Pre-Game Mulligan / Confirm Draw"
    names = {
        344: "Dwebble",
        345: "Crustle",
        117: "Cornerstone Mask Ogerpon ex",
        756: "Mega Kangaskhan ex",
        1122: "Pokégear 3.0",
        1121: "Ultra Ball",
        1086: "Buddy-Buddy Poffin",
        1123: "Switch",
        1182: "Boss's Orders",
        1227: "Lillie's Determination",
        1219: "Petrel",
        1225: "Hilda",
        1194: "Colress's Tenacity",
        1187: "Morty's Conviction",
        1197: "Xerosic's Machinations",
        1147: "Jumbo Ice Cream",
        1159: "Hero's Cape",
        1242: "Community Center",
        1257: "Team Rocket's Factory",
        1: "Basic Grass Energy",
        11: "Mist Energy",
        14: "Spiky Energy",
        20: "Rock Fighting Energy"
    }
    return names.get(cid, f"Card #{cid}")

# ── Weights Loader ─────────────────────────────────────────────────────────────
_WEIGHT_DEFAULTS = {
    "W_TIER_EARLY_BENCH":       800.0,
    "W_TIER_EVOLVE":            700.0,
    "W_TIER_TRAINER":           600.0,
    "W_TIER_ENERGY":            500.0,
    "W_TIER_ATTACK":            400.0,
    "W_TIER_TOOL_HEAL":         300.0,
    "W_TIER_RETREAT":           200.0,
    "W_TIER_NEUTRAL":           100.0,
    "W_PRIZE_MULT":             1050.0,
    "W_ENERGY_SCORE":            180.0,
    "W_TOOL_SCORE":              120.0,
    "W_STAGE2_SCORE":            280.0,
    "W_STAGE1_SCORE":            150.0,
    "W_ACTIVE_BONUS":            250.0,
    "W_TARGET_ACTIVE_BONUS":     350.0,
    "W_ENERGY_ACTIVE_BIAS":       15.0,
    "W_ENERGY_BASE":            8500.0,
    "W_ENERGY_NEED_BONUS":       120.0,
    "W_ENERGY_SURPLUS_PENALTY":   50.0,
    "W_EVOLVE_BASE":            9500.0,
    "W_TRAINER_BASE":          10500.0,
    "W_POKEMON_BASE":          20000.0,
    "W_RETREAT_SCORE":          1800.0,
    "W_ATTACK_SCORE":           1250.0,
    "W_WALL_MATCH_BONUS":        100.0,
    "W_DWEBBLE_ACTIVE_RANK":      75.0,
    "W_OGERPON_ACTIVE_RANK":      60.0,
    "W_KANGASKHAN_EARLY_RANK":    50.0,
    "W_ENERGY_RANK_MULT":         30.0,
    "W_HP_RANK_MULT":             20.0,
    "W_COMBO_PIECE_PENALTY":      25.0,
    "W_SEARCH_CRUSTLE_READY":     10.0,
    "W_SEARCH_DWEBBLE_MISSING":    15.0,
    "W_SEARCH_KANGASKHAN_EMERGENCY": 3.0,
    "W_SEARCH_NEUTRAL":            1.0,
    "W_DISCARD_KEY_SUPPORTER":   -10.0,
    "W_DISCARD_KEY_EVO":         -10.0,
    "W_DISCARD_SAFE_ENERGY":       2.0,
    "W_DISCARD_SAFE_DUPLICATE":    1.5,
    "W_LETHAL_KO_BONUS":           5.0,
    "W_BENCH_OUT_BONUS":          10.0,
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

w_prize   = W.get("W_PRIZE_MULT", 1050.0) / 1000.0
w_energy  = W.get("W_ENERGY_BASE", 8500.0) / 10000.0
w_evolve  = W.get("W_EVOLVE_BASE", 9500.0) / 10000.0
w_trainer = W.get("W_TRAINER_BASE", 10500.0) / 10000.0
w_pokemon = W.get("W_POKEMON_BASE", 20000.0) / 20000.0
w_attack  = W.get("W_ATTACK_SCORE", 1250.0) / 1000.0
w_retreat = W.get("W_RETREAT_SCORE", 1800.0) / 1000.0
w_tool    = W.get("W_TOOL_SCORE", 120.0) / 1000.0

# ── Universal Option-to-Card ID Resolver ──────────────────────────────────────
def resolve_card_id(o, info, current, select_data):
    if not o or not isinstance(o, dict): return None
    cid = o.get('cardId') or o.get('id') or o.get('cardIdActive') or o.get('cardIdTarget')
    if cid is not None: return cid
    
    area = o.get('area')
    idx = o.get('index')
    if idx is None: idx = o.get('cardIndex') or o.get('handIndex')
    
    hand = info.get('hand', [])
    looking = current.get('looking', []) if isinstance(current, dict) else []
    deck = select_data.get('deck', []) if isinstance(select_data, dict) else []

    # Area 2 = Hand
    if area == 2 or (area is None and idx is not None and o.get('type') in {1, 3, 7, 8, 9}):
        if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
            c_val = hand[idx]
            return c_val.get('id') if isinstance(c_val, dict) else c_val
            
    # Area 12 = Looking / Search Deck Modal
    if area == 12 or (area is None and isinstance(looking, list) and len(looking) > 0):
        if isinstance(looking, list) and idx is not None and 0 <= idx < len(looking):
            c_val = looking[idx]
            return c_val.get('id') if isinstance(c_val, dict) else c_val

    # Area 1 = Deck List
    if area == 1:
        if isinstance(deck, list) and idx is not None and 0 <= idx < len(deck):
            c_val = deck[idx]
            return c_val.get('id') if isinstance(c_val, dict) else c_val
        elif isinstance(looking, list) and idx is not None and 0 <= idx < len(looking):
            c_val = looking[idx]
            return c_val.get('id') if isinstance(c_val, dict) else c_val
            
    # Area 4 / 5 / 6 / 14 = Bench / Active / Opponent Field
    if area in {4, 5, 6, 14}:
        my_bench = info.get('my_bench', [])
        opp_bench = info.get('opp_bench', [])
        if idx is not None:
            if area == 4 and isinstance(my_bench, list) and 0 <= idx < len(my_bench):
                c_val = my_bench[idx]
                return c_val.get('id') if isinstance(c_val, dict) else c_val
            elif area in {5, 6, 14} and isinstance(opp_bench, list) and 0 <= idx < len(opp_bench):
                c_val = opp_bench[idx]
                return c_val.get('id') if isinstance(c_val, dict) else c_val
            elif isinstance(opp_bench, list) and 0 <= idx < len(opp_bench):
                c_val = opp_bench[idx]
                return c_val.get('id') if isinstance(c_val, dict) else c_val
            elif isinstance(my_bench, list) and 0 <= idx < len(my_bench):
                c_val = my_bench[idx]
                return c_val.get('id') if isinstance(c_val, dict) else c_val

    return None

# ── Board Info Extractor ───────────────────────────────────────────────────────
def extract_board_info(obs_dict):
    current = obs_dict.get("current")
    if not current: return {}
    
    my_idx = current.get("yourIndex", 0)
    opp_idx = 1 - my_idx
    
    my_player = current["players"][my_idx]
    opp_player = current["players"][opp_idx]
    
    hand = [c.get("id") if isinstance(c, dict) else c for c in my_player.get("hand", []) if c is not None]
    
    my_active_list = my_player.get("active", [])
    my_active = my_active_list[0] if len(my_active_list) > 0 else None
    
    opp_active_list = opp_player.get("active", [])
    opp_active = opp_active_list[0] if len(opp_active_list) > 0 else None
    
    my_bench_raw = my_player.get("bench") or my_player.get("benchArea") or my_player.get("benched") or []
    opp_bench_raw = opp_player.get("bench") or opp_player.get("benchArea") or opp_player.get("benched") or []
    
    my_bench = []
    for b in my_bench_raw:
        if not b: continue
        if isinstance(b, dict): my_bench.append(b)
        elif isinstance(b, (int, float)): my_bench.append({"id": int(b), "hp": 200, "energies": []})

    opp_bench = []
    for b in opp_bench_raw:
        if not b: continue
        if isinstance(b, dict): opp_bench.append(b)
        elif isinstance(b, (int, float)): opp_bench.append({"id": int(b), "hp": 200, "energies": []})
    
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
        "opp_active_energy": len(opp_active.get("energies", [])) if opp_active else 0,
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
    
    # RULE 1: KANGASKHAN EX IS TOP PRIORITY ACTIVE LEAD IN EARLY GAME (Turn 0 Setup)!
    if cid == Kangaskhan and is_early_game:
        log_rule_execution(f"  [RULE APPLIED] Early-Game Kangaskhan Active Lead Priority: Kangaskhan ex (Card #756) assigned TOP Rank Score 1000.0!")
        return 1000.0

    # HARD BAN: Never promote Kangaskhan ex to active in late game!
    if cid == Kangaskhan and not is_early_game:
        log_rule_execution(f"  [RULE APPLIED] Late-Game Kangaskhan Active Promotion HARD BANNED (-inf)")
        return -float('inf')
    
    energy_norm = min(energy_count / 3.0, 1.0)
    hp_norm = min(hp / float(max_hp), 1.0) if max_hp > 0 else 0.5
    is_combo_piece = 1.0 if (cid == Dwebble and energy_count == 0) else 0.0
    
    score = (energy_norm * W.get("W_ENERGY_RANK_MULT", 30.0)) + (hp_norm * W.get("W_HP_RANK_MULT", 20.0)) - (is_combo_piece * W.get("W_COMBO_PIECE_PENALTY", 25.0))
    
    if cid == optimal_active_id:
        score += W.get("W_WALL_MATCH_BONUS", 100.0)
    elif cid == Dwebble:
        score += W.get("W_DWEBBLE_ACTIVE_RANK", 75.0)
    elif cid == Ogerpon:
        score += W.get("W_OGERPON_ACTIVE_RANK", 60.0)
    return score

def score_discard_option(cid, hand, bench_and_active_ids):
    if cid in {BossOrders, Lillie, Petrel, Hilda, Colress, Morty, Xerosic}:
        log_rule_execution(f"  [IF EXECUTED] score_discard_option -> Key Supporter Discard Protection Penalty (-10.0)")
        return W.get("W_DISCARD_KEY_SUPPORTER", -10.0)
    if cid == Crustle and Dwebble in bench_and_active_ids:
        log_rule_execution(f"  [IF EXECUTED] score_discard_option -> Crustle Evolution Discard Protection Penalty (-10.0)")
        return W.get("W_DISCARD_KEY_EVO", -10.0)
    if cid in {Ogerpon, Kangaskhan} and cid not in bench_and_active_ids:
        return W.get("W_DISCARD_KEY_EVO", -10.0)

    grass_cnt = hand.count(GrassEnergy) if isinstance(hand, list) else 0
    mist_cnt = hand.count(MistEnergy) if isinstance(hand, list) else 0
    if cid in {GrassEnergy, MistEnergy} and (grass_cnt + mist_cnt > 2):
        return W.get("W_DISCARD_SAFE_ENERGY", 2.0)
    if isinstance(hand, list) and hand.count(cid) > 1:
        return W.get("W_DISCARD_SAFE_DUPLICATE", 1.5)

    return 0.0

def score_search_option(cid, hand, bench_and_active_ids, bench_count, is_early_game=True, dwebble_in_play=0, opp_has_ability=False, hand_size=5):
    # ── 1. DWEBBLE SEARCH PRIORITY (< 2 IN PLAY) ──
    if dwebble_in_play < 2:
        if cid == Dwebble:
            log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 1: Dwebble (Card #344) matched with dwebble_in_play={dwebble_in_play} (<2) -> MAX Score 100,000.0 assigned!")
            return 100000.0  # Absolute MAX priority for Dwebble!
        elif cid == Ogerpon and not opp_has_ability:
            return -100.0  # Focus on Dwebble first when < 2 in play!
    else:
        # ── 2. ONCE 2 DWEBBLE/CRUSTLE IN PLAY: STOP SEARCHING DWEBBLE, PIVOT TO CRUSTLE/OGERPON ──
        if cid == Dwebble:
            log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 1: 2 Dwebble already in play -> Dwebble search deprioritized (Score 10.0)")
            return 10.0

    # ── 3. LILLIE SEARCH PRIORITY (POKÉGEAR 3.0 / SUPPORTER SEARCH) ──
    if cid == Lillie:
        log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 2: Lillie (Card #1227) matched -> TOP Pokégear/Supporter Score 80,000.0 assigned!")
        return 80000.0   # Absolute MAX priority for Lillie!

    # ── 4. CRUSTLE EVOLUTION SEARCH ──
    if cid == Crustle:
        if Dwebble in bench_and_active_ids:
            log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 3: Crustle matched with benched Dwebble -> Score 50,000.0 assigned!")
            return 50000.0
        return -1000.0

    # ── 5. OTHER SUPPORTERS (POKÉGEAR FALLBACKS) ──
    if cid in SUPPORTERS_SET:
        if cid == BossOrders:
            return 100.0
        log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 4: Fallback Supporter ({get_card_name(cid)}) matched -> Score 500.0 assigned")
        return 500.0

    # ── 6. OGERPON SEARCH LIMIT ──
    if cid == Ogerpon:
        if opp_has_ability or bench_and_active_ids.count(Ogerpon) < 1:
            return 20000.0
        if bench_and_active_ids.count(Ogerpon) >= 2:
            log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 5: 3rd Ogerpon Search HARD BANNED (-inf)")
            return -float('inf')
        return -100.0

    # ── 7. KANGASKHAN SEARCH ──
    if cid == Kangaskhan:
        if not is_early_game:
            if bench_count < 2: return 1000.0
            log_rule_execution(f"  [IF EXECUTED] score_search_option Branch 6: Late-Game Kangaskhan Search HARD BANNED (-inf)")
            return -float('inf')
        return 2000.0

    if cid in bench_and_active_ids and bench_count >= 5:
        return -100.0
        
    return 100.0

def sanitize_action(chosen_indices: list[int], select_data: dict) -> list[int]:
    options = select_data.get("option", [])
    n_opts = len(options)
    if n_opts == 0:
        return [0]

    max_count = select_data.get("maxCount", 1)
    min_count = select_data.get("minCount", 1)

    unique = []
    for idx in chosen_indices:
        if 0 <= idx < n_opts and idx not in unique:
            unique.append(idx)

    if len(unique) < min_count:
        for i in range(n_opts):
            if i not in unique:
                unique.append(i)
                if len(unique) >= min_count:
                    break

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

    if current is None:
        return sanitize_action([0], select_data)

    try:
        info = extract_board_info(obs_dict)
        context = select_data.get("context", "")
        context_str = str(context).upper()
        raw_context_val = select_data.get("context")

        turn_num = info.get("turn", 1)
        my_prizes = info.get("my_prizes", 6)
        hand_size = info.get("hand_size", 5)
        hand = info.get("hand", [])
        my_bench = info.get("my_bench", [])
        bench_count = len(my_bench)
        my_active = info.get("my_active")
        my_active_id = info.get("my_active_id")
        my_hp = info.get("my_active_hp", 0)
        my_max_hp = info.get("my_active_max_hp", 1)
        hp_pct = my_hp / float(my_max_hp) if my_max_hp > 0 else 1.0
        my_energy = info.get("my_active_energy", 0)
        opp_hp = info.get("opp_active_hp", 999)
        opp_active_energy = info.get("opp_active_energy", 0)
        opp_bench = info.get("opp_bench", [])
        opp_is_ex = info.get("opp_is_ex", False)
        opp_has_ability = info.get("opp_has_ability", False)
        optimal_lead = info.get("optimal_active", Crustle)

        bench_and_active_ids = [_get_val(b, "id") for b in my_bench if _get_val(b, "id")]
        if my_active_id: bench_and_active_ids.append(my_active_id)

        field_counts = {}
        for cid_item in bench_and_active_ids:
            field_counts[cid_item] = field_counts.get(cid_item, 0) + 1

        dwebble_in_play = field_counts.get(Dwebble, 0) + field_counts.get(Crustle, 0)
        ogerpon_in_play = field_counts.get(Ogerpon, 0)

        is_early_game = (turn_num <= 4 or my_prizes >= 5)

        # ── SPECIAL HANDLING FOR CONTEXT 41 / 42 / 38 (PRE-GAME SETUP & MULLIGAN PROMPT) ──
        if raw_context_val in {41, 42, 38}:
            log_rule_execution(f"\n[PRE-GAME SETUP] Context {raw_context_val}: Confirming Mulligan / Initial Card Draw (Option 0)")
            return sanitize_action([0], select_data)

        # Directive 1 Check: Opening hand energy attachment requirement
        has_setup_pieces = any(c in {Dwebble, Ogerpon, BuddyPuffin, UltraBall} for c in hand)
        must_attach_opening_energy = (turn_num <= 2 and not has_setup_pieces)

        # Robust Detection of Deck Search / Card Selection Modal across all integer & string contexts
        is_search_modal = (
            current.get("looking") is not None or
            raw_context_val in {5, 7, 8, 12, 19} or
            any(kw in context_str for kw in ["SEARCH", "DECK", "LOOKING", "CHOOSE", "SELECT", "POFFIN", "FETCH", "FIND", "VIEW", "BALL"]) or
            select_data.get("reason") is not None
        )

        # Expected attack damage
        my_dmg = 0
        if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
        elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140
        elif my_active_id == Kangaskhan and my_energy >= 3: my_dmg = 100

        # Helper state checks for strict rules
        has_other_supporter_in_hand = any(c in {Lillie, Petrel, Hilda, Colress, Morty, Xerosic} for c in hand)
        supporter_played = getattr(current, "supporterPlayed", False) or False

        # Rule 3 Helper: Check if hand contains ANY playable Pokemon, evolution, or item BEFORE Lillie
        has_playable_before_lillie = False
        if Lillie in hand:
            if Dwebble in hand and bench_count < 5: has_playable_before_lillie = True
            if Crustle in hand and Dwebble in bench_and_active_ids: has_playable_before_lillie = True
            if Ogerpon in hand and bench_count < 5 and (opp_has_ability or ogerpon_in_play < 2): has_playable_before_lillie = True
            if Kangaskhan in hand and bench_count < 5 and (is_early_game or bench_count < 2): has_playable_before_lillie = True
            if any(c in {BuddyPuffin, UltraBall, SwitchCard, HerosCape, CommunityCenter, TRFactory, JumboIceCream} for c in hand):
                has_playable_before_lillie = True

        # Rule 5 Helper: Wall Safety & Damage Immunity Check
        active_takes_zero_damage = False
        if my_active_id == Crustle and opp_is_ex:
            active_takes_zero_damage = True
        elif my_active_id == Ogerpon and opp_has_ability:
            active_takes_zero_damage = True

        benched_wall_takes_zero = False
        for b in my_bench:
            bid = _get_val(b, "id")
            if bid == Crustle and opp_is_ex: benched_wall_takes_zero = True
            if bid == Ogerpon and opp_has_ability: benched_wall_takes_zero = True

        active_name = get_card_name(my_active_id)
        log_rule_execution(f"\n[Turn {turn_num} DECISION STEP] Active: {active_name} (HP: {my_hp}/{my_max_hp}, E: {my_energy}) | Bench: {bench_count} | Dwebble in Play: {dwebble_in_play} | Context: {context_str} (Raw: {raw_context_val})")

        # Active Promotion Rank Function (Setup / Active Promotion Phase)
        if ("SETUP" in context_str or "ACTIVE" in context_str or "SWITCH" in context_str or "FIRST" in context_str or raw_context_val in {1, 2}) and not is_search_modal:
            best_idx = 0
            best_rank = -float('inf')
            is_going_second = (raw_context_val == 2 or turn_num > 1 or info.get("turn", 0) > 0 or info.get("isSecond", False))
            has_crustle_in_hand = (Crustle in hand)

            for idx, o in enumerate(options):
                cid = resolve_card_id(o, info, current, select_data)
                matched_pkmn = None
                for b in my_bench:
                    if _get_val(b, "id") == cid:
                        matched_pkmn = b
                        break

                if is_going_second and has_crustle_in_hand:
                    if cid == Dwebble:
                        r_score = 1500.0 # Going 2nd with Crustle in hand -> Evolve Dwebble on turn 1!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Dwebble Priority 1500.0 (Going 2nd with Crustle in hand!)")
                    elif cid == Kangaskhan:
                        r_score = 1000.0
                    elif cid == Ogerpon:
                        r_score = 300.0
                    else:
                        r_score = 50.0
                else:
                    if cid == Kangaskhan:
                        r_score = 1000.0 # Default Lead with Kangaskhan ex to use draw ability!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Kangaskhan ex Lead Priority 1000.0 (Draw Ability Starter!)")
                    elif cid == Dwebble:
                        r_score = 500.0
                    elif cid == Ogerpon:
                        r_score = 300.0
                    else:
                        r_score = 50.0

                log_rule_execution(f"  [IF EXECUTED] Active Promotion Branch -> Option {idx} ({get_card_name(cid)}) Rank Score: {r_score}")

                if r_score > best_rank:
                    best_rank = r_score
                    best_idx = idx

            chosen_cid = resolve_card_id(options[best_idx], info, current, select_data)
            log_rule_execution(f"  => CHOSEN ACTIVE PROMOTION: {get_card_name(chosen_cid)} (Option {best_idx})")
            return sanitize_action([best_idx], select_data)

        # Scored Option Engine & Strict Directives
        scored_options = []
        has_useful_pre_attack_action = False

        for idx, o in enumerate(options):
            score = 0.0
            o_type = o.get("type", -1)
            ot_str = str(o_type).upper()
            
            # Universal Option-to-Card ID Resolution!
            cid = resolve_card_id(o, info, current, select_data)
            c_name = get_card_name(cid)

            # ── BRANCH 1: DISCARD / DECK SEARCH / OPPONENT BENCH TARGET SELECTION MODAL ──
            if "DISCARD" in context_str:
                log_rule_execution(f"  [IF EXECUTED] Branch 1A: Discard Context matched for Option {idx} ({c_name})")
                score = score_discard_option(cid, hand, bench_and_active_ids)
            elif is_search_modal:
                log_rule_execution(f"  [IF EXECUTED] Branch 1B: Deck Search Modal matched for Option {idx} ({c_name})")
                score = score_search_option(cid, hand, bench_and_active_ids, bench_count, is_early_game, dwebble_in_play, opp_has_ability, hand_size)
            elif ("TARGET" in context_str or "BENCH" in context_str or "SELECT" in context_str or raw_context_val in {3, 4, 14, 15}) and len(opp_bench) > 0:
                # Target Selection Modal for Opponent Benched Pokemon (Boss's Orders target selection!)
                b_hp = 999
                b_energies = 0
                b_retreat = 0
                b_match = None
                for b_item in opp_bench:
                    if isinstance(b_item, dict) and _get_val(b_item, "id") == cid:
                        b_match = b_item
                        b_hp = _get_val(b_item, "hp", 999)
                        b_energies = len(_get_val(b_item, "energies") or [])
                        b_retreat = _get_val(b_item, "retreatCost", 0) or _get_val(b_item, "retreat_cost", 0)
                        break

                if b_retreat == 0 and cid in {Kangaskhan, Abomasnow, Snorlax, Archaludon}:
                    b_retreat = 3

                opp_active_hp = _get_val(my_active, "hp", 999) if isinstance(my_active, dict) else 999
                opp_active_can_be_kodd = (my_dmg > 0 and my_dmg >= opp_active_hp)

                cond_A = (my_energy >= 3 and my_dmg > 0 and my_dmg >= b_hp and not opp_active_can_be_kodd)
                cond_B = (b_energies >= 2 or (b_energies >= 1 and is_card_ex(cid))) and (opp_active_energy == 0 or not is_card_ex(info.get("opp_active_id")))
                cond_C = (b_retreat >= 3 and b_energies == 0)

                if cond_A:
                    score = 95000.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Boss's Target Selected (Condition A KO: {c_name}) -> Score 95000.0!")
                elif cond_B:
                    score = 90000.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Boss's Target Selected (Condition B Building: {c_name}) -> Score 90000.0!")
                elif cond_C:
                    score = 85000.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Boss's Target Selected (Condition C Trap: {c_name}) -> Score 85000.0!")
                else:
                    score = 500.0 + (100.0 if is_card_ex(cid) else 0.0)
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Default Opponent Bench Target Selected ({c_name}) -> Score {score}")

            # ── BRANCH 2: POKÉGEAR 3.0 RESTRICTION ──
            elif cid == Pokégear:
                if has_other_supporter_in_hand or supporter_played:
                    log_rule_execution(f"  [IF EXECUTED] Branch 2: Pokégear 3.0 HARD BANNED (-inf): Supporter already in hand/played!")
                    score = -float('inf')
                else:
                    log_rule_execution(f"  [IF EXECUTED] Branch 2: Pokégear 3.0 Allowed -> Score 600.0")
                    score = 600.0 + w_trainer * 2.0
                    has_useful_pre_attack_action = True

            # ── BRANCH 3: ULTRA BALL RESTRICTION ──
            elif cid == UltraBall:
                valid_ultraball = (
                    (dwebble_in_play < 2 and Dwebble not in hand) or
                    (Dwebble in bench_and_active_ids and Crustle not in hand) or
                    (opp_has_ability and ogerpon_in_play < 2 and Ogerpon not in hand)
                )
                if not valid_ultraball:
                    log_rule_execution(f"  [IF EXECUTED] Branch 3: Ultra Ball HARD BANNED (-inf): No target requirement met!")
                    score = -float('inf')
                else:
                    log_rule_execution(f"  [IF EXECUTED] Branch 3: Ultra Ball Allowed -> Score 650.0")
                    score = 650.0 + w_trainer * 3.0
                    has_useful_pre_attack_action = True

            # ── BRANCH 4: LILLIE SUPPORTER SEQUENCING ──
            elif cid == Lillie:
                if has_playable_before_lillie:
                    log_rule_execution(f"  [IF EXECUTED] Branch 4: Lillie Supporter HARD BANNED (-inf): Playable cards still in hand!")
                    score = -float('inf')
                else:
                    log_rule_execution(f"  [IF EXECUTED] Branch 4: Lillie Supporter Allowed -> Score 600.0")
                    score = 600.0 + w_trainer * 5.0
                    has_useful_pre_attack_action = True

            # ── BRANCH 5: BOSS'S ORDERS STRICT CONDITIONS (DIRECTIVE A, B, C) ──
            elif cid == BossOrders:
                valid_boss_target = False
                target_reason = ""
                opp_active_hp = _get_val(my_active, "hp", 999) if isinstance(my_active, dict) else 999
                opp_active_can_be_kodd = (my_dmg > 0 and my_dmg >= opp_active_hp)

                for b in opp_bench:
                    if not isinstance(b, dict): continue
                    b_id = _get_val(b, "id")
                    b_hp = _get_val(b, "hp", 999)
                    b_energies = len(_get_val(b, "energies") or [])
                    b_retreat_cost = _get_val(b, "retreatCost", 0) or _get_val(b, "retreat_cost", 0)
                    
                    if b_retreat_cost == 0 and b_id in {Kangaskhan, Abomasnow, Snorlax, Archaludon}:
                        b_retreat_cost = 3

                    # Condition A: Can KO bench Pokemon AND cannot KO active
                    cond_A = (my_energy >= 3 and my_dmg > 0 and my_dmg >= b_hp and not opp_active_can_be_kodd)

                    # Condition B: Opponent building benched Pokemon (energy >= 2 or EX/evolved) vs sacrifice active (0 energy)
                    b_is_building = (b_energies >= 2 or (b_energies >= 1 and is_card_ex(b_id)))
                    opp_active_is_sacrifice = (opp_active_energy == 0 or not is_card_ex(info.get("opp_active_id")))
                    cond_B = (b_is_building and opp_active_is_sacrifice)

                    # Condition C: Benched Pokemon has retreat cost >= 3 and 0 energy attached
                    cond_C = (b_retreat_cost >= 3 and b_energies == 0)

                    if cond_A:
                        valid_boss_target = True
                        target_reason = f"Condition A (Bench KO on {get_card_name(b_id)} while active un-KOable)"
                        break
                    elif cond_B:
                        valid_boss_target = True
                        target_reason = f"Condition B (Targeting building {get_card_name(b_id)} vs sacrifice active)"
                        break
                    elif cond_C:
                        valid_boss_target = True
                        target_reason = f"Condition C (Trapping heavy {get_card_name(b_id)} with 0 energy & retreat >= 3)"
                        break

                if not valid_boss_target:
                    log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders HARD BANNED (-inf): None of Conditions A, B, or C met!")
                    score = -float('inf')
                else:
                    log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders Allowed -> Score 700.0 [{target_reason}]")
                    score = 700.0 + w_trainer * 5.0
                    has_useful_pre_attack_action = True

            # ── BRANCH 6: BENCH PLAYS (Dwebble Priority & Ogerpon Limit) ──
            elif (o_type in {1, 7} or "PLAY" in ot_str) and cid in {Dwebble, Ogerpon, Kangaskhan} and bench_count < 5:
                if cid == Ogerpon and not opp_has_ability and ogerpon_in_play >= 2:
                    log_rule_execution(f"  [IF EXECUTED] Branch 6: 3rd Ogerpon Bench Deployment HARD BANNED (-inf): Opponent active has no ability!")
                    score = -float('inf')
                elif cid == Kangaskhan and not is_early_game:
                    if bench_count < 2:
                        subscore = w_pokemon * 2.0
                        score = 800.0 + subscore
                        has_useful_pre_attack_action = True
                    else:
                        log_rule_execution(f"  [IF EXECUTED] Branch 6: Late-Game Kangaskhan Bench Deployment HARD BANNED (-inf)")
                        score = -float('inf')
                elif cid == Dwebble and dwebble_in_play < 2:
                    subscore = w_pokemon * 5.0 + 50.0
                    score = 900.0 + subscore
                    log_rule_execution(f"  [IF EXECUTED] Branch 6: Early Dwebble Bench Play Priority Matched -> Score {score}!")
                    has_useful_pre_attack_action = True
                elif cid == Ogerpon and optimal_lead == Ogerpon:
                    subscore = w_pokemon * 5.0 + 10.0
                    score = 800.0 + subscore
                    has_useful_pre_attack_action = True
                else:
                    subscore = w_pokemon * 5.0
                    score = 800.0 + subscore
                    has_useful_pre_attack_action = True

            # ── BRANCH 7: EVOLUTION (Evolve Dwebble to Crustle) ──
            elif (o_type in {6, 7, 9} or "EVOLVE" in ot_str) and (cid == Crustle):
                subscore = w_evolve * 5.0 + (3.0 if optimal_lead == Crustle else 0.0)
                score = 700.0 + subscore
                log_rule_execution(f"  [IF EXECUTED] Branch 7: Crustle Evolution Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── BRANCH 8: OTHER DRAW SUPPORTERS / ITEMS ──
            elif o_type in {7, 3} and (cid in SUPPORTERS_SET or cid in {BuddyPuffin, UltraBall, Pokégear, SwitchCard, HerosCape, CommunityCenter, TRFactory, JumboIceCream}):
                subscore = w_trainer * 5.0 + (3.0 if hand_size <= 3 else 1.0)
                score = 600.0 + subscore
                log_rule_execution(f"  [IF EXECUTED] Branch 8: Draw Supporter / Item Play Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── BRANCH 9: FOCUSED ENERGY ATTACHMENT ──
            elif o_type in {8, 4} or "ATTACH" in ot_str:
                tier_base = W.get("W_TIER_ENERGY", 500.0)
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

                if target_cid == Kangaskhan and not is_early_game:
                    log_rule_execution(f"  [IF EXECUTED] Branch 9: Late-Game Kangaskhan Energy Attachment HARD BANNED (-inf)")
                    score = -float('inf')
                elif target_energy >= 3:
                    log_rule_execution(f"  [IF EXECUTED] Branch 9: Energy Hoarding HARD BANNED (-inf): Target already has {target_energy} energies (>= 3)!")
                    score = -float('inf')
                elif is_active_target:
                    need_norm = (3 - target_energy) / 3.0
                    subscore = w_energy * 5.0 + need_norm * 3.0 + (1.0 if is_card_ex(my_active_id) else 0.0)
                    if must_attach_opening_energy:
                        log_rule_execution(f"  [IF EXECUTED] Branch 9: Opening Energy Attachment Exception Matched -> Score 950.0!")
                        score = 950.0 + subscore
                    else:
                        log_rule_execution(f"  [IF EXECUTED] Branch 9: Active Energy Attachment Matched -> Score {tier_base + subscore}")
                        score = tier_base + subscore
                else:
                    if my_energy < 3:
                        score = 100.0
                    else:
                        need_norm = (3 - target_energy) / 3.0
                        subscore = w_energy * 2.5 + need_norm * 1.5
                        score = tier_base + subscore
                has_useful_pre_attack_action = True

            # ── BRANCH 10: ATTACKING ──
            elif o_type in {13, 5} or "ATTACK" in ot_str:
                tier_base = W.get("W_TIER_ATTACK", 400.0)
                recoil_dmg = _get_val(o, "recoilDamage", 0) or _get_val(o, "selfDamage", 0)
                if recoil_dmg > 0 and (recoil_dmg >= my_hp or (my_dmg < 20 and my_dmg < opp_hp)):
                    score = -float('inf')
                else:
                    prize_norm = (6 - my_prizes) / 6.0
                    subscore = w_attack * 5.0 + w_prize * prize_norm * 3.0
                    if my_dmg >= opp_hp and opp_hp > 0:
                        subscore += W.get("W_LETHAL_KO_BONUS", 5.0)
                    if len(opp_bench) == 0:
                        subscore += W.get("W_BENCH_OUT_BONUS", 10.0)
                    score = tier_base + subscore
                log_rule_execution(f"  [IF EXECUTED] Branch 10: Attack Option Matched -> Score {score}")

            # ── BRANCH 11: HERO'S CAPE & STADIUMS / HEALING ──
            elif o_type in {7, 10} or cid in {HerosCape, CommunityCenter, JumboIceCream, TRFactory}:
                tier_base = W.get("W_TIER_TOOL_HEAL", 300.0)
                if cid == HerosCape:
                    score = 850.0 + w_tool * 5.0  # Hero's Cape +100 HP Tool equipped immediately!
                    log_rule_execution(f"  [IF EXECUTED] Branch 11: Hero's Cape +100 HP Tool Equipping Matched -> Score {score}")
                else:
                    subscore = w_tool * 5.0
                    score = tier_base + subscore
                    log_rule_execution(f"  [IF EXECUTED] Branch 11: Stadium / Healing Item Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── BRANCH 12: RETREAT GUARD & WALL SAFETY ──
            elif o_type in {12, 8} or "RETREAT" in ot_str:
                if active_takes_zero_damage:
                    log_rule_execution(f"  [IF EXECUTED] Branch 12: Retreat Guard HARD BANNED (-inf): Active is an immune wall!")
                    score = -float('inf')
                else:
                    is_special_condition = any([
                        _get_val(my_active, "poisoned"),
                        _get_val(my_active, "burned"),
                        _get_val(my_active, "asleep"),
                        _get_val(my_active, "confused"),
                        _get_val(my_active, "paralyzed")
                    ])
                    if benched_wall_takes_zero or hp_pct < 0.30 or is_special_condition:
                        subscore = w_retreat * 5.0 + (1.0 - hp_pct) * 3.0
                        score = 200.0 + subscore
                        log_rule_execution(f"  [IF EXECUTED] Branch 12: Retreat Pivot Matched -> Score {score}")
                    else:
                        log_rule_execution(f"  [IF EXECUTED] Branch 12: Retreat Guard HARD BANNED (-inf): Active takes damage but no benched wall ready!")
                        score = -float('inf')

            # ── BRANCH 13: END TURN ──
            elif o_type in {14} or "END" in ot_str:
                if has_useful_pre_attack_action:
                    score = -50.0
                else:
                    score = 0.0
                log_rule_execution(f"  [IF EXECUTED] Branch 13: End Turn Matched -> Score {score}")

            else:
                score = W.get("W_TIER_NEUTRAL", 100.0)
                log_rule_execution(f"  [IF EXECUTED] Branch 14: Neutral Fallback Matched -> Score {score}")

            scored_options.append((score, idx))

        scored_options.sort(key=lambda x: x[0], reverse=True)
        best_score, best_idx = scored_options[0]
        chosen_cid = resolve_card_id(options[best_idx], info, current, select_data)
        
        log_rule_execution(f"  => FINAL EXECUTION SELECTION: Option {best_idx} ({get_card_name(chosen_cid)}) with Highest Score: {best_score}\n")

        desc_indices = [i for _, i in scored_options]
        return sanitize_action(desc_indices, select_data)
    except Exception as e:
        log_rule_execution(f"  [EXCEPTION] {e}")
        return sanitize_action([0], select_data)

"""
Wall_V5 Agent — Replay Winner Analytics Adaptation Engine (Card ID Resolver & V5 Scoring Engine)
================================================================================================
Fixes Card ID constants, implements positional-to-card ID resolver, and adds action sanitizer to prevent invalid step disqualifications.
"""

import os
import sys
import json
import csv

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
        f.write("=== WALL_V5 IF-STATEMENT & STRATEGIC RULE EXECUTION LOG ===\n\n")
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
    if area == 2 or (area is None and idx is not None and o.get('type') in {1, 3, 6, 7, 8, 9, 11, 12, 13}):
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
            
    # Area 4 = Bench / Active
    if area == 4:
        my_bench = info.get('my_bench', [])
        if isinstance(my_bench, list) and idx is not None and 0 <= idx < len(my_bench):
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

    if opp_is_ex:
        optimal_active = Crustle
    elif opp_has_ability:
        optimal_active = Ogerpon
    else:
        optimal_active = Crustle

    turn = current.get("turn", 1)
    
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
        "optimal_active": optimal_active,
        "my_prizes": len(my_player.get("prize", [])),
        "opp_prizes": len(opp_player.get("prize", [])),
    }

def _get_val(obj, key, default=None):
    if not obj: return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def check_boss_conditions(info):
    opp_active_hp = info.get("opp_active_hp", 0)
    opp_bench = info.get("opp_bench", [])
    my_active_id = info.get("my_active_id")
    my_energy = info.get("my_active_energy", 0)
    
    my_dmg = 0
    if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
    elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140
    elif my_active_id == Kangaskhan and my_energy >= 3: my_dmg = 100
    
    if my_energy < 3 or my_dmg <= 0: return False

    active_koable = (my_dmg >= opp_active_hp and opp_active_hp > 0)
    if not active_koable and my_dmg > 0:
        for b in opp_bench:
            b_hp = _get_val(b, "hp", 999)
            if b_hp <= my_dmg:
                return True
                
    opp_active_energy = len(_get_val(info.get("opp_active"), "energies") or [])
    for b in opp_bench:
        b_energies = len(_get_val(b, "energies") or [])
        if b_energies >= opp_active_energy + 2:
            return True
                
    return False

def score_search_option(cid, hand, bench_and_active_ids, bench_count, dwebble_in_play=0, opp_has_ability=False):
    if dwebble_in_play < 2:
        if cid == Dwebble:
            log_rule_execution(f"  [IF EXECUTED] score_search_option -> Dwebble search priority (<2 in play): MAX Score 100,000.0!")
            return 100000.0
    else:
        if cid == Dwebble:
            return 10.0

    if cid == Lillie:
        log_rule_execution(f"  [IF EXECUTED] score_search_option -> Lillie Pokégear Search Priority: TOP Score 80,000.0!")
        return 80000.0

    if cid == Crustle and Dwebble in bench_and_active_ids:
        return 50000.0

    if cid in SUPPORTERS_SET:
        return 500.0

    if cid == Ogerpon:
        if opp_has_ability or bench_and_active_ids.count(Ogerpon) < 1:
            return 20000.0
        if bench_and_active_ids.count(Ogerpon) >= 2:
            return -float('inf')
        return -100.0

    return 100.0

# ── Main Agent Function ────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None:
        if obs_dict.get("step", 0) == 0:
            return my_deck
        return []

    options = select_data.get("option", [])
    if not options: return sanitize_action([0], select_data)
    
    current = obs_dict.get("current")
    if current is None: return sanitize_action([0], select_data)
    
    try:
        info = extract_board_info(obs_dict)
        context = select_data.get("context", "")
        context_str = str(context).upper()
        raw_context_val = select_data.get("context")

        # Pre-Game Mulligan / Setup Prompt Handling
        if raw_context_val in {41, 42, 38}:
            log_rule_execution(f"\n[PRE-GAME SETUP] Context {raw_context_val}: Confirming Mulligan / Initial Card Draw (Option 0)")
            return sanitize_action([0], select_data)

        hand = info.get("hand", [])
        my_bench = info.get("my_bench", [])
        bench_count = len(my_bench)
        my_active_id = info.get("my_active_id")
        my_energy = info.get("my_active_energy", 0)
        turn_num = info.get("turn", 1)
        is_early_game = turn_num <= 4

        bench_and_active_ids = [_get_val(b, "id") for b in my_bench if _get_val(b, "id")]
        if my_active_id: bench_and_active_ids.append(my_active_id)

        field_counts = {}
        for cid_item in bench_and_active_ids:
            field_counts[cid_item] = field_counts.get(cid_item, 0) + 1

        dwebble_in_play = field_counts.get(Dwebble, 0) + field_counts.get(Crustle, 0)
        opp_has_ability = info.get("opp_has_ability", False)

        is_search_modal = (
            current.get("looking") is not None or
            raw_context_val in {5, 7, 8, 12, 19} or
            any(kw in context_str for kw in ["SEARCH", "DECK", "LOOKING", "CHOOSE", "SELECT", "POFFIN", "FETCH", "FIND", "VIEW", "BALL"]) or
            select_data.get("reason") is not None
        )

        log_rule_execution(f"\n[Turn {turn_num} DECISION STEP] Active: {get_card_name(my_active_id)} (E: {my_energy}) | Bench: {bench_count} | Dwebble in Play: {dwebble_in_play} | Context: {context_str} (Raw: {raw_context_val})")

        # ── Phase 1: Active Promotion / Setup Lead Selection ─────────────────────
        if ("SETUP" in context_str or "ACTIVE" in context_str or "SWITCH" in context_str or raw_context_val == 1) and not is_search_modal:
            optimal_lead = info.get("optimal_active", Crustle)
            best_idx = 0
            best_rank = -float('inf')

            for idx, o in enumerate(options):
                cid = resolve_card_id(o, info, current, select_data)
                c_name = get_card_name(cid)
                r_score = 0.0

                if cid == Kangaskhan and is_early_game:
                    r_score = 1000.0  # Top rank active lead in early game!
                elif cid == optimal_lead:
                    r_score = 500.0
                elif cid == Dwebble:
                    r_score = 300.0
                elif cid == Ogerpon:
                    r_score = 200.0
                else:
                    r_score = 10.0

                log_rule_execution(f"  [IF EXECUTED] Active Promotion Branch -> Option {idx} ({c_name}) Rank Score: {r_score}")

                if r_score > best_rank:
                    best_rank = r_score
                    best_idx = idx

            chosen_cid = resolve_card_id(options[best_idx], info, current, select_data)
            log_rule_execution(f"  => CHOSEN ACTIVE PROMOTION: {get_card_name(chosen_cid)} (Option {best_idx})")
            return sanitize_action([best_idx], select_data)

        # ── Phase 2: Option Scoring Engine ───────────────────────────────────────
        scored_options = []
        has_useful_pre_attack_action = False
        
        for idx, o in enumerate(options):
            o_type = o.get("type", -1)
            ot_str = str(o_type).upper()
            
            # Universal Positional-to-Card ID Resolver!
            cid = resolve_card_id(o, info, current, select_data)
            c_name = get_card_name(cid)
            score = 0.0

            if "DISCARD" in context_str:
                score = 0.0
            elif is_search_modal:
                log_rule_execution(f"  [IF EXECUTED] Branch 1: Deck Search Modal matched for Option {idx} ({c_name})")
                score = score_search_option(cid, hand, bench_and_active_ids, bench_count, dwebble_in_play, opp_has_ability)

            # ── Boss's Orders Evaluation ──────────────────────────────────────────
            elif cid == BossOrders:
                if not check_boss_conditions(info):
                    log_rule_execution(f"  [IF EXECUTED] Branch 2: Boss's Orders HARD BANNED (-inf): Conditions not met!")
                    score = -float('inf')
                else:
                    log_rule_execution(f"  [IF EXECUTED] Branch 2: Boss's Orders Allowed -> Score 500,000.0")
                    score = 500000.0
                    has_useful_pre_attack_action = True

            # ── Energy Attachment Protocols ───────────────────────────────────────
            elif o_type in {11, 8, 4} or "ATTACH" in ot_str:
                in_play_area = o.get("inPlayArea")
                in_play_idx = o.get("inPlayIndex", 0)
                
                target_energy = 0
                target_id = None
                
                is_active_target = (in_play_area in {3, 4, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
                
                if is_active_target and info.get("my_active"):
                    target_energy = info["my_active_energy"]
                    target_id = info["my_active_id"]
                elif isinstance(in_play_idx, int) and 0 <= in_play_idx < len(info["my_bench"]):
                    b = info["my_bench"][in_play_idx]
                    target_energy = len(b.get("energies", []))
                    target_id = b.get("id")
                    
                # HARD BAN: Stop attaching if target already has 3+ energies!
                if target_energy >= 3:
                    log_rule_execution(f"  [IF EXECUTED] Branch 3: Energy Hoarding HARD BANNED (-inf): Target has {target_energy} energies (>= 3)!")
                    score = -float('inf')
                else:
                    optimal_id = info.get("optimal_active")
                    is_grass = (cid == GrassEnergy)
                    
                    if target_energy == 2:
                        base_e = 110000.0
                    elif target_energy == 1:
                        base_e = 90000.0
                    else:
                        base_e = 70000.0
                        
                    if is_grass: base_e += 15000.0
                    if target_id == optimal_id: base_e += 10000.0
                    elif target_id in {Crustle, Dwebble, Ogerpon}: base_e += 5000.0
                        
                    score = base_e
                    log_rule_execution(f"  [IF EXECUTED] Branch 3: Energy Attachment Matched -> Score {score}")
                    has_useful_pre_attack_action = True

            # ── Hero's Cape Tool Attachment ──────────────────────────────────────
            elif (o_type in {6, 7, 10, 12} or "TOOL" in ot_str) and cid == HerosCape:
                log_rule_execution(f"  [IF EXECUTED] Branch 4: Hero's Cape Tool Matched -> Score 1,400,000.0")
                score = 1400000.0
                has_useful_pre_attack_action = True

            # ── Evolution Protocol (Evolve Dwebble -> Crustle ASAP!) ────────────
            elif (o_type in {6, 7, 9} or "EVOLVE" in ot_str) and cid == Crustle:
                log_rule_execution(f"  [IF EXECUTED] Branch 5: Crustle Evolution Matched -> Score 1,350,000.0")
                score = 1350000.0
                has_useful_pre_attack_action = True

            # ── Deck Search Items (Ultra Ball, Buddy Poffin, Pokégear, etc.) ──────
            elif (o_type in {6, 7, 13} or "TRAINER" in ot_str) and cid in {UltraBall, BuddyPuffin, Pokégear, EarthenVessel, Arven, Iono, HeavyBall, NestBall}:
                log_rule_execution(f"  [IF EXECUTED] Branch 6: Search Item / Supporter Matched ({c_name}) -> Score 850,000.0")
                score = 850000.0
                has_useful_pre_attack_action = True

            # ── Hand Size < 4 Supporter Logic ─────────────────────────────────────
            elif (o_type in {6, 7, 3} or "SUPPORTER" in ot_str) and info.get("hand_size", 5) < 4 and cid in {Petrel, Lillie}:
                score = 400000.0 if cid == Petrel else 350000.0
                log_rule_execution(f"  [IF EXECUTED] Branch 7: Hand Size < 4 Supporter ({c_name}) -> Score {score}")
                has_useful_pre_attack_action = True

            # ── Mid-Game Switch & Pivot Logic ─────────────────────────────────────
            elif (o_type in {6, 7} or "SWITCH" in ot_str) and cid == SwitchCard:
                current_active_id = info.get("my_active_id")
                optimal_id = info.get("optimal_active")
                
                if current_active_id != optimal_id:
                    bench_has_optimal = any(_get_val(b, "id") == optimal_id for b in info.get("my_bench", []))
                    score = 500000.0 if bench_has_optimal else 10000.0
                else:
                    score = -10000.0
                log_rule_execution(f"  [IF EXECUTED] Branch 8: Switch Card Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── Healing Items (Jumbo Ice Cream / Community Center) ────────────────
            elif (o_type in {6, 7} or "ITEM" in ot_str) and cid in {JumboIceCream, CommunityCenter}:
                if info.get("my_active_hp", 999) < info.get("my_active_max_hp", 999):
                    score = 350000.0
                else:
                    score = -5000.0
                log_rule_execution(f"  [IF EXECUTED] Branch 9: Healing Item ({c_name}) Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── Disruption Supporters & Control ──────────────────────────────────
            elif (o_type in {6, 7} or "SUPPORTER" in ot_str) and cid in {Xerosic, Morty, TRFactory}:
                score = 200000.0
                log_rule_execution(f"  [IF EXECUTED] Branch 10: Control Supporter ({c_name}) Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── Bench Priority (Deploy Dwebble / Ogerpon) ───────────────────────
            elif (o_type in {1, 6, 7} or "PLAY" in ot_str) and cid in {Dwebble, Ogerpon, Kangaskhan} and bench_count < 5:
                if bench_count == 0:
                    score = 1300000.0
                elif bench_count == 1:
                    score = 500000.0
                else:
                    score = 150000.0
                log_rule_execution(f"  [IF EXECUTED] Branch 11: Bench Deployment ({c_name}) Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── Attack Protocol (Superb Scissors / Ogerpon) ──────────────────────
            elif o_type in {15, 13, 5} or "ATTACK" in ot_str:
                score = 700000.0
                log_rule_execution(f"  [IF EXECUTED] Branch 12: Attack Option Matched -> Score {score}")

            # ── End Turn Option ──────────────────────────────────────────────────
            elif o_type in {14} or "END" in ot_str:
                if has_useful_pre_attack_action:
                    score = -50.0
                else:
                    score = 0.0
                log_rule_execution(f"  [IF EXECUTED] Branch 13: End Turn Matched -> Score {score}")

            else:
                score = 1.0
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

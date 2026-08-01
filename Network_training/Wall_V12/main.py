import os
import sys
import json
import csv
from collections import Counter

# ── Card Database & Deck Loader ───────────────────────────────────────────────
_CARD_DB = {}
def _load_card_database():
    global _CARD_DB
    if _CARD_DB: return
    for candidate in ["EN_Card_Data.csv", "data/EN_Card_Data.csv", "/kaggle_simulations/agent/EN_Card_Data.csv", "../data/EN_Card_Data.csv"]:
        if os.path.exists(candidate):
            try:
                with open(candidate, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            cid = int(row["Card ID"])
                            _CARD_DB[cid] = row
                        except: pass
            except: pass

def load_deck():
    try:
        dir_path = os.path.dirname(__file__)
        local_deck = os.path.join(dir_path, "deck.csv")
        if os.path.exists(local_deck):
            try:
                with open(local_deck) as f:
                    cards = [int(line) for line in f if line.strip()]
                    if len(cards) == 60: return cards
            except: pass
    except NameError:
        pass
    for p in ["deck.csv", "/kaggle_simulations/agent/deck.csv"]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    cards = [int(line) for line in f if line.strip()]
                    if len(cards) == 60: return cards
            except: pass
    return [344]*4 + [345]*4 + [117]*3 + [756]*2 + [1227]*4 + [1182]*4 + [1219]*3 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [18]*4 + [14]*3 + [20]*2

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
    if c:
        if getattr(c, 'ex', False) or getattr(c, 'megaEx', False) or getattr(c, 'isEx', False):
            return True
        name = getattr(c, 'name', '') or ''
        if ' ex' in name.lower() or ' mega ' in name.lower():
            return True
    if cid in _CARD_DB:
        row = _CARD_DB[cid]
        val = str(row.get("EX", "")).strip().lower()
        if val == "true": return True
        card_name = str(row.get("Card Name", "")).lower()
        if " ex" in card_name or " mega " in card_name: return True
    return False

def card_has_ability(cid):
    if not cid: return False
    c = _CG_CARD_TABLE.get(cid)
    if c:
        abilities = getattr(c, 'abilities', None) or getattr(c, 'ability', None)
        if abilities: return True
    if cid in _CARD_DB:
        row = _CARD_DB[cid]
        abilities_str = str(row.get("Abilities", "")).strip()
        if abilities_str and abilities_str != "[]" and abilities_str.lower() != "none":
            return True
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
GrassEnergy = 18
MistEnergy = 11
NestBall = 1122
UltraBall = 1147
HeavyBall = 1086
BuddyPuffin = 1121
EarthenVessel = 1227
Iono = 1182
Arven = 1219

# ── Archetype Signature Engine ───────────────────────────────────────────────
_BUILTIN_TEMPLATES = [
    ("Alakazam_ex", Counter([741, 742, 743, 65, 66, 305, 1079, 1081, 1086, 1097, 1129, 1152, 1182, 1184, 1197, 1225, 1227, 1231, 1247, 5, 19])),
    ("Lucario_ex", Counter([677, 678, 673, 674, 675, 676, 1102, 1123, 1141, 1142, 1152, 1159, 1182, 1192, 1227, 1252, 6])),
    ("Dragapult_ex", Counter([119, 120, 121, 1122, 1147, 1079, 1182, 1219, 1227, 18, 5])),
    ("Archaludon", Counter([169, 190, 1122, 1147, 1219, 1227, 1])),
    ("Iono_Deck", Counter([265, 1182, 1219, 1122, 1147, 14, 20])),
]

_TEMPLATES = []
for _d in ("/kaggle_simulations/agent/top20_decks", "top20_decks", "../top20_decks"):
    if os.path.isdir(_d):
        for _fn in sorted(os.listdir(_d)):
            if not _fn.endswith(".csv"): continue
            try:
                with open(os.path.join(_d, _fn)) as _f:
                    _ids = [int(x) for x in _f.read().split() if x.strip()][:60]
                if len(_ids) == 60:
                    _TEMPLATES.append((_fn, Counter(_ids), _ids))
            except Exception: pass
        break

if not _TEMPLATES:
    for name, cnt in _BUILTIN_TEMPLATES:
        _TEMPLATES.append((name, cnt, list(cnt.elements())))

def _op_visible(current, opp_idx):
    opp = current["players"][opp_idx]
    seen = Counter()
    for c in opp.get("discard", []) or []:
        if isinstance(c, dict) and "id" in c: seen[c["id"]] += 1
    for p in (opp.get("active", []) or []) + (opp.get("bench", []) or []):
        if not p or not isinstance(p, dict): continue
        if "id" in p: seen[p["id"]] += 1
        for c in p.get("energyCards", []) or []:
            if isinstance(c, dict) and "id" in c: seen[c["id"]] += 1
        for c in p.get("tools", []) or []:
            if isinstance(c, dict) and "id" in c: seen[c["id"]] += 1
    return seen

def _identify_opp_archetype(op_seen):
    if not op_seen: return "Unknown"
    op_mons = set(op_seen.keys())
    best_name, best_score = "Unknown", 0
    for name, cnt, _ in _TEMPLATES:
        sig = set(cnt.keys())
        overlap = len(sig & op_mons)
        if overlap > best_score:
            best_name, best_score = name, overlap
    return best_name

# ── State Extraction Helper ────────────────────────────────────────────────────
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
    
    opp_all_ids = ([opp_active_id] if opp_active_id else []) + [b.get("id") for b in opp_bench if b.get("id")]
    opp_is_ex = any(is_card_ex(cid) for cid in opp_all_ids)
    opp_has_ability = any(card_has_ability(cid) for cid in opp_all_ids)
    turn = current.get("turn", 1)

    op_seen = _op_visible(current, opp_idx)
    opp_archetype = _identify_opp_archetype(op_seen)

    if "Alakazam" in opp_archetype or "Lucario" in opp_archetype or "Dragapult" in opp_archetype or "Archaludon" in opp_archetype:
        opp_is_ex = True

    if opp_is_ex:
        optimal_active = Crustle
    elif opp_has_ability:
        optimal_active = Ogerpon
    else:
        optimal_active = Kangaskhan if (turn <= 2 and (Kangaskhan in hand or any(b.get("id") == Kangaskhan for b in my_bench))) else Crustle

    opp_hand_raw = opp_player.get("hand")
    opp_hand_count = opp_player.get("handCount") if opp_player.get("handCount") is not None else len(opp_hand_raw if opp_hand_raw else [])
    opp_deck_count = opp_player.get("deckCount", 30)
    
    return {
        "my_idx": my_idx,
        "turn": turn,
        "is_second": (current.get("isFirst", True) == False),
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
        "opp_archetype": opp_archetype,
        "opp_hand_count": opp_hand_count,
        "opp_deck_count": opp_deck_count,
        "optimal_active": optimal_active,
        "my_prizes": len(my_player.get("prize", [])),
        "opp_prizes": len(opp_player.get("prize", [])),
    }

# ==============================================================================
# ARCHITECTURAL REFACTOR: 4 STRICT SEQUENTIAL LAYERS
# ==============================================================================

# ── LAYER 1: Hard Stops & Safety Layer (Disqualification Filter) ──────────────
def is_disqualified(option, info):
    o_type = option.get("type", -1)
    cid = option.get("cardId") or option.get("id") or option.get("cardIdActive")
    
    opp_is_ex = info.get("opp_is_ex", False)
    opp_has_ability = info.get("opp_has_ability", False)
    opp_archetype = info.get("opp_archetype", "Unknown")
    my_active_id = info.get("my_active_id")
    bench_count = len(info.get("my_bench", []))
    turn = info.get("turn", 1)
    opp_prizes = info.get("opp_prizes", 6)

    # Hard Stop 1.1: If opp_is_ex, hard ban deploying, playing, or energizing Kangaskhan or Ogerpon into active
    if opp_is_ex or "Alakazam" in opp_archetype:
        if cid in {Ogerpon, Kangaskhan} and o_type in {6, 11, 14, 15}:
            # If deploying to active or energizing non-immune card vs EX -> DISQUALIFY
            if o_type == 6 and cid == Ogerpon: return True
            if o_type == 6 and cid == Kangaskhan: return True
            if o_type == 11:
                in_play_area = option.get("inPlayArea")
                in_play_idx = option.get("inPlayIndex", 0)
                is_active = (in_play_area in {3, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
                if is_active and my_active_id in {Ogerpon, Kangaskhan}: return True

    # Hard Stop 1.2: If energy count >= 3, lock attachment to absolute negative block (DISQUALIFY)
    if o_type == 11:
        in_play_area = option.get("inPlayArea")
        in_play_idx = option.get("inPlayIndex", 0)
        is_active = (in_play_area in {3, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
        
        target_energy = 0
        if is_active and info.get("my_active"):
            target_energy = info["my_active_energy"]
        elif isinstance(in_play_idx, int) and 0 <= in_play_idx < len(info["my_bench"]):
            b = info["my_bench"][in_play_idx]
            target_energy = len(b.get("energies", []) or [])
            
        if target_energy >= 3:
            return True # DISQUALIFY over-saturated energy attachment!

    # Hard Stop 1.3: If attack target possesses damage immunity that nullifies active attacker, DISQUALIFY attack
    if o_type == 15:
        if opp_is_ex and my_active_id in {Ogerpon, Kangaskhan}:
            return True # DISQUALIFY nullified attack into EX!

    # Hard Stop 1.4: Prohibit playing non-wall basic Pokémon (Kangaskhan) late game or when bench is full
    if o_type == 6 and cid == Kangaskhan:
        if turn >= 3 or opp_prizes <= 4 or opp_is_ex or opp_has_ability or "Alakazam" in opp_archetype:
            return True
        if bench_count >= 2:
            return True

    # Hard Stop 1.5: Dragapult bench hard-cap (max 1 bench)
    if ("Dragapult" in opp_archetype or info.get("opp_active_id") == 121) and o_type == 6 and cid in {Kangaskhan, Ogerpon, Dwebble}:
        if bench_count >= 1:
            return True

    return False

# ── LAYER 2: Core Wall-Matching Engine (Type-Driven Priority) ──────────────────
def score_wall_matching(option, info):
    o_type = option.get("type", -1)
    cid = option.get("cardId") or option.get("id") or option.get("cardIdActive")
    
    opp_is_ex = info.get("opp_is_ex", False)
    opp_has_ability = info.get("opp_has_ability", False)
    opp_archetype = info.get("opp_archetype", "Unknown")
    my_active_id = info.get("my_active_id")
    
    score = 0.0

    # Case A: Opponent is an EX Pokémon -> Maximize preference for Crustle
    if opp_is_ex:
        if cid == Crustle:
            if o_type in {6, 7}: score += 4000.0 # Evolve to Crustle
            elif o_type == 11: score += 3500.0 # Energy to Crustle
        elif cid == Dwebble and o_type == 6:
            score += 3000.0 # Prepare Crustle base

    # Case B: Opponent has an Ability (Non-EX) -> Maximize preference for Ogerpon ex
    elif opp_has_ability:
        if cid == Ogerpon:
            if o_type == 6: score += 4500.0 # Deploy Ogerpon
            elif o_type == 11: score += 4000.0 # Energy to Ogerpon
        elif cid == Crustle:
            score += 2000.0

    # Case C: Opponent is Neither (Non-EX, No Ability) -> Suppress immunity walls, favor disruption
    else:
        if cid == BossOrders and o_type == 6:
            score += 5000.0 # Pivot opponent bench EX/Ability into active!
        elif cid == Xerosic and o_type == 6:
            score += 4800.0 # Hand disruption!
        elif cid == Kangaskhan and info.get("turn", 1) <= 2:
            score += 3500.0 # Kangaskhan draw/attack vs non-EX

    return score

# ── LAYER 3: Resource, Bench, & Energy Distribution Layer ─────────────────────
def score_resource_distribution(option, info):
    o_type = option.get("type", -1)
    cid = option.get("cardId") or option.get("id") or option.get("cardIdActive")
    
    my_active_id = info.get("my_active_id")
    my_active_energy = info.get("my_active_energy", 0)
    bench_count = len(info.get("my_bench", []))
    hand_size = info.get("hand_size", 7)
    my_active_hp = info.get("my_active_hp", 999)
    turn = info.get("turn", 1)
    is_second = info.get("is_second", False)
    
    score = 0.0

    # 3.1: Emergency 0-Bench Survival Protocol
    if bench_count == 0:
        if o_type == 6 and cid in {Dwebble, Crustle}:
            score += 6000.0 # Highest priority: bench backup!
        elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, Arven}:
            score += 5500.0
        elif my_active_hp <= 100 and cid == HerosCape:
            score += 7000.0 # Survival HP boost!

    # 3.2: Turn 1 Going Second Fast Acceleration
    elif turn == 1 and is_second and o_type in {6, 13} and cid in {NestBall, BuddyPuffin, Arven, UltraBall}:
        score += 5800.0

    # 3.3: Route Energy to Bench Walls when Active is Saturated (2+ Energy)
    elif o_type == 11:
        in_play_area = option.get("inPlayArea")
        in_play_idx = option.get("inPlayIndex", 0)
        is_active_target = (in_play_area in {3, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
        
        if my_active_energy >= 2 and is_active_target:
            score += 500.0 # Active almost ready
        elif not is_active_target:
            score += 2500.0 # Route energy to bench wall!
        else:
            score += 2000.0

    # 3.4: Item & Supporter Resource Management
    elif o_type == 6 and cid == HerosCape:
        score += 4200.0
    elif o_type == 6 and cid == Iono and info.get("opp_hand_count", 0) >= 4:
        score += 3800.0
    elif o_type == 6 and hand_size < 4 and cid in {Lillie, Petrel, Arven}:
        score += 3000.0

    return score

# ── LAYER 4: Corrected Delta-Based Lookahead Evaluation ─────────────────────
def calculate_action_delta(option, info):
    o_type = option.get("type", -1)
    cid = option.get("cardId") or option.get("id") or option.get("cardIdActive")
    
    # Differential state score change resulting from this specific action
    delta = 0.0
    
    # Immediate KO / Attack execution delta
    if o_type == 15:
        opp_hp = info.get("opp_active_hp", 999)
        if opp_hp <= 90:
            delta += 3000.0 # Action results in immediate KO!
        else:
            delta += 1500.0 # Action deals damage

    # Evolution state delta (Dwebble -> Crustle increases max HP + immunity)
    elif o_type in {6, 7} and cid == Crustle:
        delta += 2000.0

    # Switching out of danger delta
    elif o_type == 6 and cid == SwitchCard:
        if info.get("opp_is_ex") and info.get("my_active_id") in {Ogerpon, Kangaskhan}:
            delta += 4000.0 # Switch pulls non-immune card out of danger!

    # Ascension attack delta
    elif o_type == 15 and info.get("my_active_id") == Dwebble:
        delta += 2500.0 # Enables immediate free evolution search

    return delta

# ── Main Agent Entry Point ─────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None: return my_deck
    options = select_data.get("option", [])
    if not options: return []
    
    info = extract_board_info(obs_dict)
    hand = info.get("hand", [])
    
    # ── Opening Lead / Setup Context Override ──────────────────────────────────
    context = select_data.get("context", "")
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper() or "PROMOTE" in str(context).upper() or "RETREAT" in str(context).upper():
        opp_is_ex = info.get("opp_is_ex", False)
        opp_archetype = info.get("opp_archetype", "Unknown")
        is_second = info.get("is_second", False)
        holding_crustle = (Crustle in hand)
        
        if opp_is_ex or "Alakazam" in opp_archetype:
            lead_priority = [Crustle, Dwebble] # Hard Ban Kangaskhan/Ogerpon vs EX!
        elif is_second and holding_crustle:
            lead_priority = [Dwebble, Kangaskhan, Crustle, Ogerpon]
        else:
            lead_priority = [Kangaskhan, Crustle, Ogerpon, Dwebble]
            
        for lead_choice in lead_priority:
            for idx, o in enumerate(options):
                cid = o.get("cardId") or o.get("id") or o.get("cardIdActive")
                if cid == lead_choice:
                    return [idx]
        
        for idx, o in enumerate(options):
            cid = o.get("cardId") or o.get("id") or o.get("cardIdActive")
            if opp_is_ex and cid in {Ogerpon, Kangaskhan}: continue
            return [idx]
        return [0]

    # ── 4-LAYER SEQUENTIAL SCORING PIPELINE ────────────────────────────────────
    valid_candidates = []

    for idx, o in enumerate(options):
        # ── LAYER 1: Hard Stops & Safety Layer (Disqualification Filter) ──────
        if is_disqualified(o, info):
            continue # ABSOLUTE DISQUALIFICATION: Filter option completely out!

        # ── LAYER 2: Core Wall-Matching Engine (Type-Driven Priority) ──────────
        s2 = score_wall_matching(o, info)

        # ── LAYER 3: Resource, Bench, & Energy Distribution Layer ─────────────
        s3 = score_resource_distribution(o, info)

        # ── LAYER 4: Corrected Delta-Based Lookahead Evaluation ───────────────
        s4 = calculate_action_delta(o, info)

        # Total score bounded within clean [-10,000.0 to +10,000.0] range
        total_score = max(-10000.0, min(10000.0, s2 + s3 + s4))
        valid_candidates.append((total_score, idx))

    # If all options were disqualified, fall back safely to option 0
    if not valid_candidates:
        return [0]

    # Sort valid candidates strictly by total score on a normalized scale
    valid_candidates.sort(key=lambda x: x[0], reverse=True)
    count = min(select_data.get("maxCount", 1), max(select_data.get("minCount", 1), 1))
    best_indices = [s[1] for s in valid_candidates[:count]]
    return best_indices

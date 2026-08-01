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
    from cg.api import all_card_data, search_step
    _CG_CARD_TABLE = {c.cardId: c for c in all_card_data()}
    HAS_CG_API = True
except Exception:
    _CG_CARD_TABLE = {}
    HAS_CG_API = False

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

# ── Archetype Signature Engine for Opponent Deck Identification ───────────────
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

# ── 1-Ply / 2-Ply Minimax Lookahead Simulation Engine ────────────────────────
def evaluate_leaf_score(obs_dict, my_idx):
    cur = obs_dict.get("current", {})
    players = cur.get("players", [])
    if len(players) < 2: return 0.0
    
    me = players[my_idx]
    opp = players[1 - my_idx]
    
    my_prizes = len(me.get("prize", []) or [])
    opp_prizes = len(opp.get("prize", []) or [])
    
    my_act = (me.get("active") or [{}])[0]
    opp_act = (opp.get("active") or [{}])[0]
    
    my_hp = my_act.get("hp", 0) if isinstance(my_act, dict) else 0
    opp_hp = opp_act.get("hp", 0) if isinstance(opp_act, dict) else 0
    
    my_e = len(my_act.get("energies", []) or []) if isinstance(my_act, dict) else 0
    opp_e = len(opp_act.get("energies", []) or []) if isinstance(opp_act, dict) else 0
    
    # Formula: 1000*(OppPrizesLeft - MyPrizesLeft) + (MyHP - OppHP) + 5*(MyEnergy - OppEnergy)
    score = 1000.0 * (opp_prizes - my_prizes) + (my_hp - opp_hp) + 5.0 * (my_e - opp_e)
    return score

# ── Main Agent Function ────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None: return my_deck
    options = select_data.get("option", [])
    if not options: return []
    
    info = extract_board_info(obs_dict)
    hand = info.get("hand", [])
    turn = info.get("turn", 1)
    is_second = info.get("is_second", False)
    
    opp_is_ex = info.get("opp_is_ex", False)
    opp_has_ability = info.get("opp_has_ability", False)
    opp_archetype = info.get("opp_archetype", "Unknown")
    opp_deck_count = info.get("opp_deck_count", 30)
    opp_prizes = info.get("opp_prizes", 6)
    my_active_hp = info.get("my_active_hp", 999)
    
    # ── RULE 2: Strict Opening Lead Protocols ─────────────────────────────
    context = select_data.get("context", "")
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper() or "PROMOTE" in str(context).upper() or "RETREAT" in str(context).upper():
        holding_crustle = (Crustle in hand)
        
        if opp_is_ex or "Alakazam" in opp_archetype:
            lead_priority = [Crustle, Dwebble] # HARD BAN Kangaskhan & Ogerpon vs EX!
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

    # ── Option Scoring Engine ─────────────────────────────────────────────────
    scored_options = []
    
    my_active_id = info.get("my_active_id")
    bench_count = len(info.get("my_bench", []))
    opp_hand = info.get("opp_hand_count", 0)
    hand_size = info.get("hand_size", len(hand))
    opp_active_id = info.get("opp_active_id")

    for idx, o in enumerate(options):
        o_type = o.get("type", -1)
        cid = o.get("cardId") or o.get("id") or o.get("cardIdActive")
        score = 0.0

        # ── EMERGENCY 0-BENCH SURVIVAL PROTOCOL ──────────────────────────────
        if bench_count == 0:
            if o_type == 6 and cid in {Dwebble, Kangaskhan, Ogerpon}:
                if opp_is_ex and cid in {Ogerpon, Kangaskhan}:
                    score = -999999999.0
                elif (turn >= 3 or opp_prizes <= 4 or opp_is_ex or opp_has_ability) and cid == Kangaskhan:
                    score = -999999999.0
                else:
                    score = 3000000.0
                    
            elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, Arven}:
                score = 2900000.0
                
            elif my_active_hp <= 100 and o_type in {6, 12} and cid == HerosCape:
                score = 3200000.0

        # ── TURN 1 GOING SECOND ACCELERATION ENGINE ───────────────────────────
        elif turn == 1 and is_second and o_type in {6, 13} and cid in {NestBall, BuddyPuffin, Arven, UltraBall}:
            score = 3100000.0 # Instant Turn 1 setup acceleration!

        # ── DRAGAPULT 0-BENCH IMMUNITY DENIAL PROTOCOL ───────────────────────
        elif ("Dragapult" in opp_archetype or opp_active_id == 121) and o_type == 6 and cid in {Kangaskhan, Ogerpon, Dwebble}:
            if bench_count >= 1:
                score = -999999999.0 # HARD BAN additional bench Pokémon vs Dragapult!

        # ── RULE 3: Bench Liability & Late-Game Guardrails ───────────────────
        elif o_type == 6 and cid == Kangaskhan:
            if turn >= 3 or opp_prizes <= 4 or opp_is_ex or opp_has_ability or "Alakazam" in opp_archetype:
                score = -999999999.0
            elif bench_count >= 2:
                score = -999999999.0
            else:
                score = 600000.0

        elif o_type == 6 and cid in {Dwebble, Ogerpon}:
            if opp_is_ex and cid == Ogerpon:
                score = -999999999.0
            elif bench_count >= 2:
                score = -50000.0
            elif cid in {Dwebble, Crustle}:
                score = 800000.0
            else:
                score = 500000.0

        # ── DYNAMIC COUNTER: Anti-Alakazam Hand Disruption ───────────────────
        elif o_type == 6 and cid == Iono:
            if "Alakazam" in opp_archetype and opp_hand >= 4:
                score = 2600000.0
            elif opp_deck_count <= 15:
                score = 2200000.0
            elif opp_hand >= 5:
                score = 1800000.0
            else:
                score = 850000.0

        # ── DYNAMIC COUNTER: Anti-Iono / Non-EX Disruption ───────────────────
        elif o_type == 6 and cid == Xerosic:
            if "Iono" in opp_archetype or (not opp_is_ex and not opp_has_ability):
                score = 2400000.0
            elif opp_deck_count <= 15 or opp_hand >= 6:
                score = 2000000.0
            else:
                score = 300000.0

        # ── Hero's Cape Attachment ─────────────────────────────────────────────
        elif o_type in {6, 12} and cid == HerosCape:
            if "Dragapult" in opp_archetype or opp_active_id == 121:
                score = 2700000.0
            else:
                score = 1700000.0

        # ── Dwebble Ascension Attack Override ─────────────────────────────────
        elif o_type == 15 and my_active_id == Dwebble:
            score = 2000000.0

        # ── Evolution Protocol (Dwebble -> Crustle) ───────────────────────────
        elif o_type in {6, 7} and cid == Crustle:
            if "Dragapult" in opp_archetype or opp_active_id == 121:
                score = 2600000.0
            else:
                score = 1400000.0

        # ── RULE 4: Energy Saturation & Resource Management ─────────────────
        elif o_type == 11:
            in_play_area = o.get("inPlayArea")
            in_play_idx = o.get("inPlayIndex", 0)
            
            target_energy = 0
            target_id = None
            target_has_grass = False
            
            is_active_target = (in_play_area in {3, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
            
            if is_active_target and info.get("my_active"):
                target_energy = info["my_active_energy"]
                target_id = info["my_active_id"]
                target_energies = info.get("my_active", {}).get("energies", [])
                target_has_grass = any(e == GrassEnergy or (isinstance(e, dict) and e.get("id") == GrassEnergy) for e in target_energies)
            elif isinstance(in_play_idx, int) and 0 <= in_play_idx < len(info["my_bench"]):
                b = info["my_bench"][in_play_idx]
                target_energies = b.get("energies", [])
                target_energy = len(target_energies)
                target_id = b.get("id")
                target_has_grass = any(e == GrassEnergy or (isinstance(e, dict) and e.get("id") == GrassEnergy) for e in target_energies)
                
            max_energy_cap = 3
            
            if target_energy >= max_energy_cap:
                score = -999999999.0
            elif opp_is_ex and target_id in {Ogerpon, Kangaskhan}:
                score = -999999999.0
            else:
                optimal_id = info.get("optimal_active")
                is_grass = (cid == GrassEnergy)
                
                if target_id == Dwebble and is_active_target:
                    score = 1900000.0
                else:
                    if target_energy == 2: base_e = 1320000.0
                    elif target_energy == 1: base_e = 1310000.0
                    else: base_e = 1300000.0
                    
                    if target_id in {Crustle, Dwebble} and not target_has_grass and is_grass:
                        base_e += 25000.0
                    elif is_grass:
                        base_e += 15000.0
                        
                    if target_id == optimal_id: base_e += 10000.0
                    elif target_id in {Crustle, Dwebble}: base_e += 5000.0
                    score = base_e

        # ── RULE 5: Advanced Attack & Immunity Cross-Checks ───────────────────
        elif o_type == 15:
            if opp_is_ex and my_active_id in {Ogerpon, Kangaskhan}:
                score = -999999999.0
            elif not opp_is_ex and not opp_has_ability and my_active_id == Kangaskhan and info.get("my_active_energy", 0) >= 3:
                score = 1600000.0
            else:
                score = 1100000.0

        # ── Boss's Orders Non-EX Pivot ───────────────────────────────────────
        elif o_type == 6 and cid == BossOrders:
            if "Iono" in opp_archetype or (not opp_is_ex and not opp_has_ability):
                score = 2600000.0
            else:
                score = 500000.0

        # ── Mid-Game Switch & Pivot Logic ─────────────────────────────────────
        elif o_type == 6 and cid == SwitchCard:
            current_active_id = info.get("my_active_id")
            optimal_id = info.get("optimal_active")
            
            if opp_is_ex and current_active_id in {Ogerpon, Kangaskhan}:
                score = 2500000.0
            elif current_active_id == Kangaskhan and (any(b.get("id") == Crustle and len(b.get("energies", [])) >= 2 for b in info["my_bench"])):
                score = 1800000.0
            else:
                bench_has_prepared_wall = False
                for b in info.get("my_bench", []):
                    b_id = b.get("id")
                    if b_id == optimal_id or (b_id == Crustle and len(b.get("energies", [])) >= 2):
                        bench_has_prepared_wall = True
                        break
                
                if current_active_id != optimal_id and bench_has_prepared_wall:
                    score = 1500000.0
                else:
                    score = -10000.0

        else:
            score = 1.0
            
        # ── Add Minimax Lookahead Leaf Score Bonus ─────────────────────────────
        leaf_bonus = evaluate_leaf_score(obs_dict, info.get("my_idx", 0))
        score += leaf_bonus
        
        scored_options.append((score, idx))

    scored_options.sort(key=lambda x: x[0], reverse=True)
    count = min(select_data.get("maxCount", 1), max(select_data.get("minCount", 1), 1))
    best_indices = [s[1] for s in scored_options[:count]]
    return best_indices

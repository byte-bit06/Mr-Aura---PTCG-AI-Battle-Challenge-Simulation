import os
import sys
import json
import csv

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
                    return [int(line) for line in f if line.strip()]
            except: pass
    except NameError:
        pass
    for p in ["deck.csv", "/kaggle_simulations/agent/deck.csv"]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return [int(line) for line in f if line.strip()]
            except: pass
    return [344]*4 + [345]*4 + [117]*3 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [18]*4 + [14]*3 + [20]*2 + [1]

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

def get_retreat_cost(cid):
    if not cid: return 0
    c = _CG_CARD_TABLE.get(cid)
    if c and hasattr(c, 'retreatCost'): return c.retreatCost
    if cid in _CARD_DB:
        try: return int(_CARD_DB[cid].get("Retreat", 0))
        except: pass
    return 0

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
    opp_is_ex = is_card_ex(opp_active_id)
    opp_has_ability = card_has_ability(opp_active_id)

    # Passive Immunity Optimal Active Rules
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
        "opp_hand_count": opp_hand_count,
        "optimal_active": optimal_active,
        "my_prizes": len(my_player.get("prize", [])),
        "opp_prizes": len(opp_player.get("prize", [])),
    }

# ── Boss's Orders Gate (3 Exact Conditions) ──────────────────────────────────
def check_boss_conditions(info):
    opp_active_hp = info.get("opp_active_hp", 0)
    opp_bench = info.get("opp_bench", [])
    my_active_id = info.get("my_active_id")
    my_energy = info.get("my_active_energy", 0)
    
    my_dmg = 0
    if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
    elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140
    
    active_koable = (my_dmg >= opp_active_hp and opp_active_hp > 0)
    if not active_koable and my_dmg > 0:
        for b in opp_bench:
            if b.get("hp", 999) <= my_dmg:
                return True
                
    opp_active_energy = len(info.get("opp_active", {}).get("energies", [])) if info.get("opp_active") else 0
    if opp_active_energy == 0:
        for b in opp_bench:
            b_energy = len(b.get("energies", []))
            b_tools = len(b.get("tools", []))
            b_stage = b.get("stage", 0)
            if b_energy >= 2 or b_tools >= 1 or b_stage >= 1:
                return True
                
    setting_up_slow = (info.get("turn", 1) <= 4 or my_energy < 2)
    if setting_up_slow:
        for b in opp_bench:
            b_id = b.get("id")
            b_energy = len(b.get("energies", []))
            rc = get_retreat_cost(b_id)
            if rc >= 3 and b_energy == 0:
                return True
                
    return False

# ── Main Agent Function ────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None: return my_deck
    options = select_data.get("option", [])
    if not options: return []
    
    info = extract_board_info(obs_dict)
    hand = info.get("hand", [])
    turn = info.get("turn", 1)
    
    # ── Phase 1: Setup / Lead Selection ──────────────────────────────────────
    context = select_data.get("context", "")
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper():
        optimal_lead = info.get("optimal_active", Crustle)
        lead_priority = [optimal_lead, Dwebble, Ogerpon]
            
        for lead_choice in lead_priority:
            for idx, o in enumerate(options):
                cid = o.get("cardId") or o.get("id")
                if cid == lead_choice:
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

        # ── Rule 4: Emergency Triple-Bench Protection (0 Bench) ───────────────
        if o_type == 6 and cid in {Dwebble, Ogerpon}:
            if bench_count == 0:
                score = 1650000.0 # EMERGENCY BENCH (Prevent instant defeat!)
            elif cid in {Dwebble, Crustle}:
                score = 800000.0
            else:
                score = 500000.0

        # ── Rule 1: Anti-Alakazam Hand Disruption Protocol (Iono Emergency) ───
        elif o_type == 6 and cid == Iono:
            if opp_hand >= 5:
                score = 1800000.0 # Emergency Iono to shuffle Alakazam's hand into deck!
            else:
                score = 850000.0

        # ── Low Hand (<4) Supporter Recovery (Lillie / Petrel) ───────────────
        elif o_type == 6 and hand_size < 4 and cid in {Lillie, Petrel, Arven}:
            if cid == Lillie: score = 1500000.0
            elif cid == Petrel: score = 1450000.0
            elif cid == Arven: score = 1400000.0

        # ── Hero's Cape Attachment ─────────────────────────────────────────────
        elif o_type in {6, 12} and cid == HerosCape:
            score = 1700000.0 # Instant tool priority!

        # ── Rule 2: Active Dwebble Ascension Attack & Energy ──────────────────
        elif o_type == 15 and my_active_id == Dwebble:
            score = 1500000.0 # Execute Ascension attack to pull Crustle from deck!

        # ── Evolution Protocol (Dwebble -> Crustle) ───────────────────────────
        elif o_type in {6, 7} and cid == Crustle:
            # Anti-Dragapult Bench Protection: Evolve benched Dwebbles immediately vs Dragapult!
            if opp_active_id == 121: # Dragapult ex
                score = 1600000.0
            else:
                score = 1400000.0

        # ── Energy Attachment Protocols (ALWAYS attach 1 Energy per turn!) ─────
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
                
            if target_energy >= 3:
                score = -999999.0 # HARD BAN (Never waste 4th+ energy!)
            else:
                optimal_id = info.get("optimal_active")
                is_grass = (cid == GrassEnergy)
                
                if target_id == Dwebble and is_active_target and (345 not in hand):
                    score = 1480000.0 # Active Dwebble Ascension energy priority!
                else:
                    if target_energy == 2: base_e = 1320000.0
                    elif target_energy == 1: base_e = 1310000.0
                    else: base_e = 1300000.0
                    
                    if target_id in {Crustle, Dwebble} and not target_has_grass and is_grass:
                        base_e += 25000.0 # Grass Energy Priority for Crustle!
                    elif is_grass:
                        base_e += 15000.0
                        
                    if target_id == optimal_id: base_e += 10000.0
                    elif target_id in {Crustle, Dwebble, Ogerpon}: base_e += 5000.0
                    score = base_e

        # ── Attack Protocol (Superb Scissors / Demolish) ──────────────────────
        elif o_type == 15:
            score = 1100000.0 # Always attack every turn!

        # ── Deck Search Items (Nest Ball, Ultra Ball, Heavy Ball, Arven) ───────
        elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, EarthenVessel, Arven}:
            score = 850000.0

        # ── Boss's Orders Gate (3 Exact Conditions) ───────────────────────────
        elif o_type == 6 and cid == BossOrders:
            if not check_boss_conditions(info):
                score = -999999.0 # HARD BAN
            else:
                score = 500000.0

        # ── Mid-Game Switch & Pivot Logic ─────────────────────────────────────
        elif o_type == 6 and cid == SwitchCard:
            current_active_id = info.get("my_active_id")
            optimal_id = info.get("optimal_active")
            
            bench_has_prepared_wall = False
            for b in info.get("my_bench", []):
                b_id = b.get("id")
                if b_id == optimal_id or (b_id == Crustle and len(b.get("energies", [])) >= 2) or (b_id == Ogerpon and len(b.get("energies", [])) >= 2):
                    bench_has_prepared_wall = True
                    break
            
            if current_active_id != optimal_id and bench_has_prepared_wall:
                score = 500000.0
            else:
                score = -10000.0 # Stay in position; don't waste Switch!

        # ── Hand Size < 4 Supporter Logic ─────────────────────────────────────
        elif o_type == 6 and hand_size < 4:
            if cid == Petrel: score = 400000.0
            elif cid == Lillie: score = 350000.0

        # ── Healing Items (Jumbo Ice Cream / Community Center) ────────────────
        elif o_type == 6 and cid in {JumboIceCream, CommunityCenter}:
            if info.get("my_active_hp", 999) < info.get("my_active_max_hp", 999):
                score = 350000.0
            else:
                score = -5000.0

        # ── Disruption Supporters & Control ──────────────────────────────────
        elif o_type == 6 and cid in {Xerosic, Morty, TRFactory}:
            score = 200000.0

        else:
            score = 1.0
            
        scored_options.append((score, idx))

    scored_options.sort(key=lambda x: x[0], reverse=True)
    count = min(select_data.get("maxCount", 1), max(select_data.get("minCount", 1), 1))
    best_indices = [s[1] for s in scored_options[:count]]
    return best_indices

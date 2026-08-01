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
    return [344]*4 + [345]*4 + [117]*3 + [756]*2 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [18]*4 + [14]*3 + [20]*2

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
    turn = current.get("turn", 1)

    # ── GUARDRAIL 1: Precision Wall-Matching Logic ─────────────────────────
    if opp_is_ex:
        optimal_active = Crustle # Enemy is ex -> Crustle immunity wall
    elif opp_has_ability:
        optimal_active = Ogerpon # Enemy has Ability -> Cornerstone Mask Ogerpon ex
    else:
        optimal_active = Kangaskhan if (turn <= 3 and (Kangaskhan in hand or any(b.get("id") == Kangaskhan for b in my_bench))) else Crustle

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
        "opp_hand_count": opp_hand_count,
        "opp_deck_count": opp_deck_count,
        "optimal_active": optimal_active,
        "my_prizes": len(my_player.get("prize", [])),
        "opp_prizes": len(opp_player.get("prize", [])),
    }

# ── Main Agent Function ────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None: return my_deck
    options = select_data.get("option", [])
    if not options: return []
    
    info = extract_board_info(obs_dict)
    hand = info.get("hand", [])
    turn = info.get("turn", 1)
    
    opp_is_ex = info.get("opp_is_ex", False)
    opp_has_ability = info.get("opp_has_ability", False)
    opp_deck_count = info.get("opp_deck_count", 30)
    opp_prizes = info.get("opp_prizes", 6)
    my_active_hp = info.get("my_active_hp", 999)
    
    # ── GUARDRAIL 2: Strict Opening Lead Protocols ─────────────────────────
    context = select_data.get("context", "")
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper() or "PROMOTE" in str(context).upper() or "RETREAT" in str(context).upper():
        is_second = info.get("is_second", False)
        holding_crustle = (Crustle in hand)
        
        if is_second and holding_crustle:
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
            if opp_is_ex and cid == Ogerpon: continue # HARD BAN Ogerpon vs EX!
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

        # ── EMERGENCY 0-BENCH SURVIVAL PROTOCOL (BENCH-OUT PREVENTION) ────────
        if bench_count == 0:
            if o_type == 6 and cid in {Dwebble, Kangaskhan, Ogerpon}:
                if opp_is_ex and cid == Ogerpon:
                    score = -999999.0 # HARD BAN Ogerpon vs EX
                elif turn >= 3 and cid == Kangaskhan:
                    score = -999999.0 # HARD BAN late-game Kangaskhan
                else:
                    score = 3000000.0 # ABSOLUTE MAX PRIORITY: Place Bench Backup to avoid instant defeat!
                    
            elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, Arven}:
                score = 2900000.0 # ABSOLUTE MAX PRIORITY: Search deck for Bench Backup!
                
            elif my_active_hp <= 100 and o_type in {6, 12} and cid == HerosCape:
                score = 3200000.0 # ABSOLUTE MAX PRIORITY: Attach Hero's Cape (+50 HP) to survive KO!
                
            elif my_active_hp <= 100 and o_type == 6 and cid in {JumboIceCream, CommunityCenter}:
                score = 3100000.0 # ABSOLUTE MAX PRIORITY: Heal Active to survive KO!

        # ── GUARDRAIL 3: Bench Liability & Late-Game Guardrails ───────────────
        elif o_type == 6 and cid == Kangaskhan:
            if turn >= 3 or opp_prizes <= 4:
                score = -999999.0 # HARD BAN late-game Kangaskhan benching!
            elif bench_count >= 2:
                score = -999999.0 # Prevent extra bench bloat
            else:
                score = 600000.0

        elif o_type == 6 and cid in {Dwebble, Ogerpon}:
            if opp_is_ex and cid == Ogerpon:
                score = -999999.0 # HARD BAN (Ogerpon is a 2-prize target vs EX!)
            elif bench_count >= 2:
                score = -50000.0 # Clean bench guardrail (max 2 bench Pokémon)
            elif cid in {Dwebble, Crustle}:
                score = 800000.0
            else:
                score = 500000.0

        # ── Anti-Alakazam Hand Disruption & Deck-Out Acceleration ─────────────
        elif o_type == 6 and cid == Iono:
            if opp_deck_count <= 15:
                score = 2200000.0 # DECK-OUT LOCK!
            elif opp_hand >= 5:
                score = 1800000.0 # Emergency Iono vs Alakazam!
            else:
                score = 850000.0

        elif o_type == 6 and cid == Xerosic:
            if not opp_is_ex and not opp_has_ability:
                score = 2100000.0 # Disruption vs Non-EX non-ability opponents!
            elif opp_deck_count <= 15 or opp_hand >= 6:
                score = 2000000.0
            else:
                score = 300000.0

        # ── Low Hand (<4) Supporter Recovery ──────────────────────────────────
        elif o_type == 6 and hand_size < 4 and cid in {Lillie, Petrel, Arven}:
            if cid == Lillie: score = 1500000.0
            elif cid == Petrel: score = 1450000.0
            elif cid == Arven: score = 1400000.0

        # ── Hero's Cape Attachment ─────────────────────────────────────────────
        elif o_type in {6, 12} and cid == HerosCape:
            score = 1700000.0

        # ── Dwebble Ascension Attack Override ─────────────────────────────────
        elif o_type == 15 and my_active_id == Dwebble:
            score = 2000000.0 # Execute Ascension IMMEDIATELY!

        # ── Evolution Protocol (Dwebble -> Crustle) ───────────────────────────
        elif o_type in {6, 7} and cid == Crustle:
            if opp_active_id == 121: # Dragapult ex
                score = 1700000.0 # Anti-Dragapult Bench Protection!
            else:
                score = 1400000.0

        # ── GUARDRAIL 4: Energy Saturation & Resource Management ─────────────
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
                
            max_energy_cap = 3 # Hard 3-energy cap!
            if target_id == Kangaskhan: max_energy_cap = 3
            
            if target_energy >= max_energy_cap:
                score = -999999.0 # HARD LOCK TO ZERO (Saturation guardrail)!
            elif opp_is_ex and target_id == Ogerpon:
                score = -999999.0 # HARD BAN (Don't attach energy to Ogerpon vs EX!)
            else:
                optimal_id = info.get("optimal_active")
                is_grass = (cid == GrassEnergy)
                
                if target_id == Dwebble and is_active_target:
                    score = 1900000.0 # Enable Ascension!
                else:
                    if target_energy == 2: base_e = 1320000.0
                    elif target_energy == 1: base_e = 1310000.0
                    else: base_e = 1300000.0
                    
                    if target_id in {Crustle, Dwebble} and not target_has_grass and is_grass:
                        base_e += 25000.0 # Grass Energy Priority for Crustle!
                    elif is_grass:
                        base_e += 15000.0
                        
                    if target_id == optimal_id: base_e += 10000.0
                    elif target_id in {Crustle, Dwebble, Kangaskhan}: base_e += 5000.0
                    score = base_e

        # ── GUARDRAIL 5: Advanced Attack & Immunity Cross-Checks ──────────────
        elif o_type == 15:
            if opp_is_ex and my_active_id == Ogerpon:
                score = -999999.0 # Nullified! Force immediate pivot (SwitchCard) instead of attacking into zero damage!
            elif not opp_is_ex and not opp_has_ability and my_active_id == Kangaskhan and info.get("my_active_energy", 0) >= 3:
                score = 1600000.0 # Attack with Kangaskhan vs Non-EX non-ability opponents!
            else:
                score = 1100000.0 # Standard attack!

        # ── Deck Search Items (Nest Ball, Ultra Ball, Heavy Ball, Arven) ───────
        elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, EarthenVessel, Arven}:
            if opp_deck_count <= 15: score = 400000.0 # Preserve deck size during deck-out phase!
            else: score = 850000.0

        # ── Boss's Orders Gate (Guardrail 1 Disruption vs Non-EX Non-Ability) ──
        elif o_type == 6 and cid == BossOrders:
            if not opp_is_ex and not opp_has_ability:
                score = 2200000.0 # Disruption vs Non-EX Non-Ability opponents!
            elif not check_boss_conditions(info):
                score = -999999.0 # HARD BAN
            else:
                score = 500000.0

        # ── Mid-Game Switch & Pivot Logic ─────────────────────────────────────
        elif o_type == 6 and cid == SwitchCard:
            current_active_id = info.get("my_active_id")
            optimal_id = info.get("optimal_active")
            
            if opp_is_ex and current_active_id == Ogerpon:
                score = 2500000.0 # EMERGENCY SWITCH: Pull Ogerpon OUT of Active vs EX!
            elif current_active_id == Kangaskhan and (any(b.get("id") == Crustle and len(b.get("energies", [])) >= 2 for b in info["my_bench"])):
                score = 1800000.0 # Pivot Kangaskhan to prepared Crustle wall!
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
            
        scored_options.append((score, idx))

    scored_options.sort(key=lambda x: x[0], reverse=True)
    count = min(select_data.get("maxCount", 1), max(select_data.get("minCount", 1), 1))
    best_indices = [s[1] for s in scored_options[:count]]
    return best_indices

import os
import sys
import json
import csv

# ── Card Database & Deck ──────────────────────────────────────────────────────
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
    dir_path = os.path.dirname(__file__)
    local_deck = os.path.join(dir_path, "deck.csv")
    if os.path.exists(local_deck):
        try:
            with open(local_deck) as f:
                return [int(line) for line in f if line.strip()]
        except: pass
    for p in ["deck.csv", "/kaggle_simulations/agent/deck.csv"]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return [int(line) for line in f if line.strip()]
            except: pass
    return [344]*4 + [345]*4 + [117]*3 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [18]*4 + [14]*3 + [20]*2 + [1]

my_deck = load_deck()
_load_card_database()

# Card Constants
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
    opp_is_ex = False
    opp_has_ability = False
    
    if opp_active_id and opp_active_id in _CARD_DB:
        opp_is_ex = str(_CARD_DB[opp_active_id].get("EX", "false")).lower() == "true"
        opp_has_ability = len(_CARD_DB[opp_active_id].get("Abilities", [])) > 0

    # Optimal Active Wall Target based on Opponent Active:
    # Rule 1: If opponent is an EX -> Crustle (Superb Scissors/Wall)
    # Rule 2: If opponent has an Ability (and NOT an EX) -> Ogerpon ex (Cornerstone Immunity)
    # Rule 3: Otherwise -> Crustle
    optimal_active = Crustle
    if opp_has_ability and not opp_is_ex:
        optimal_active = Ogerpon
    elif opp_is_ex:
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

# ── Boss's Orders Condition Evaluator ─────────────────────────────────────────
def check_boss_conditions(info):
    opp_active_hp = info.get("opp_active_hp", 0)
    opp_bench = info.get("opp_bench", [])
    my_active_id = info.get("my_active_id")
    my_energy = info.get("my_active_energy", 0)
    
    my_dmg = 0
    if my_active_id == Crustle and my_energy >= 3: my_dmg = 120
    elif my_active_id == Ogerpon and my_energy >= 3: my_dmg = 140
    
    # Condition A: Bench KO available when Active KO not available
    active_koable = (my_dmg >= opp_active_hp and opp_active_hp > 0)
    if not active_koable and my_dmg > 0:
        for b in opp_bench:
            if b.get("hp", 999) <= my_dmg:
                return True
                
    # Condition B: Stalling the builder
    opp_active_energy = len(info.get("opp_active", {}).get("energies", [])) if info.get("opp_active") else 0
    if opp_active_energy == 0:
        for b in opp_bench:
            if len(b.get("energies", [])) >= 2:
                return True
                
    return False

# ── Main Agent Function ────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select")
    if select_data is None: return my_deck
    options = select_data.get("option", [])
    if not options: return []
    
    info = extract_board_info(obs_dict)
    
    # ── Phase 1: Setup / Mulligan Lead Selection ──────────────────────────────
    context = select_data.get("context", "")
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper():
        optimal_lead = info.get("optimal_active", Crustle)
        
        # Priority: Optimal Lead -> Dwebble -> Ogerpon -> First Available
        for lead_choice in [optimal_lead, Dwebble, Ogerpon]:
            for idx, o in enumerate(options):
                cid = o.get("cardId") or o.get("id")
                if cid == lead_choice:
                    return [idx]
        return [0]

    # ── Option Scoring Engine ─────────────────────────────────────────────────
    scored_options = []
    
    for idx, o in enumerate(options):
        o_type = o.get("type", -1)
        cid = o.get("cardId") or o.get("id") or o.get("cardIdActive")
        score = 0.0

        # ── Boss's Orders Evaluation ──────────────────────────────────────────
        if o_type == 6 and cid == BossOrders:
            if not check_boss_conditions(info):
                score = -999999.0 # HARD BAN
            else:
                score = 500000.0

        # ── Energy Attachment Protocols ───────────────────────────────────────
        elif o_type == 11:
            target_area = o.get("toArea") or o.get("inPlayIndex")
            target_energy = 0
            target_id = None
            
            if target_area in {0, 'active'} and info.get("my_active"):
                target_energy = info["my_active_energy"]
                target_id = info["my_active_id"]
            elif isinstance(target_area, int) and 0 <= target_area < len(info["my_bench"]):
                b = info["my_bench"][target_area]
                target_energy = len(b.get("energies", []))
                target_id = b.get("id")
                
            # Rule: Stop attaching if max expensive attack is powered up (>= 3 energies)
            if target_energy >= 3:
                score = -50000.0
            else:
                optimal_id = info.get("optimal_active")
                is_grass = (cid == GrassEnergy)
                
                # Priority: 2 Energy (1 away from attack) > 1 Energy (2 away) > 0 Energy
                if target_energy == 2:
                    base_e = 110000.0 # Closest to attacking!
                elif target_energy == 1:
                    base_e = 90000.0  # 2 steps away
                else:
                    base_e = 70000.0  # 0 energy
                    
                # Right Energy Priority: Grass Energy gets +15,000 bonus
                if is_grass:
                    base_e += 15000.0
                    
                # Target Priority: Optimal Active Wall gets +10,000 bonus
                if target_id == optimal_id:
                    base_e += 10000.0
                elif target_id in {Crustle, Dwebble, Ogerpon}:
                    base_e += 5000.0
                    
                score = base_e

        # ── Hero's Cape Tool Attachment (Instant Priority!) ─────────────────
        elif o_type in {6, 12} and cid == HerosCape:
            # Equip Hero's Cape to Crustle immediately to bump HP to 240+ and prevent one-shots!
            score = 1400000.0

        # ── Evolution Protocol (Evolve Dwebble -> Crustle ASAP!) ────────────
        elif o_type in {6, 7} and cid == Crustle:
            # Evolving Dwebble into Crustle boosts HP, defense & attacks instantly!
            score = 1350000.0

        # ── Deck Search Items (Nest Ball, Ultra Ball, Heavy Ball, Arven, etc.) ─
        elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, EarthenVessel, Arven, Iono}:
            # High priority to fetch Dwebble, Crustle, Ogerpon & Energies out of deck!
            score = 850000.0

        # ── Hand Size < 4 Supporter Logic ─────────────────────────────────────
        elif o_type == 6 and info.get("hand_size", 5) < 4:
            if cid == Petrel: score = 400000.0
            elif cid == Lillie: score = 350000.0

        # ── Mid-Game Switch & Pivot Logic ─────────────────────────────────────
        elif o_type == 6 and cid == SwitchCard:
            current_active_id = info.get("my_active_id")
            optimal_id = info.get("optimal_active")
            
            # If current active is NOT optimal, and optimal is ready on bench -> SWITCH!
            if current_active_id != optimal_id:
                bench_has_optimal = False
                for b in info.get("my_bench", []):
                    if b.get("id") == optimal_id or (optimal_id == Crustle and b.get("id") == Dwebble):
                        bench_has_optimal = True
                        break
                if bench_has_optimal:
                    score = 500000.0
                else:
                    score = 10000.0
            else:
                score = -10000.0 # Stay in optimal wall position

        # ── Healing Items (Jumbo Ice Cream / Community Center) ────────────────
        elif o_type == 6 and cid in {JumboIceCream, CommunityCenter}:
            if info.get("my_active_hp", 999) < info.get("my_active_max_hp", 999):
                score = 350000.0
            else:
                score = -5000.0

        # ── Disruption Supporters & Control ──────────────────────────────────
        elif o_type == 6 and cid in {Xerosic, Morty, TRFactory}:
            score = 200000.0

        # ── Bench Priority (Deploy Dwebble / Ogerpon) ───────────────────────
        elif o_type == 6 and cid in {Dwebble, Ogerpon}:
            # Emergency Bench Safety Net: Prevent bench-out losses & maintain backup attackers!
            bench_count = len(info.get("my_bench", []))
            if bench_count == 0:
                score = 1300000.0 # EMERGENCY BENCH PROTECTION (Prevent instant loss!)
            elif bench_count == 1:
                score = 500000.0  # High priority backup
            else:
                score = 150000.0

        # ── Attack Protocol (Superb Scissors / Ogerpon) ──────────────────────
        elif o_type == 15:
            score = 700000.0 # Always attack every turn!

        else:
            score = 1.0
            
        scored_options.append((score, idx))

    scored_options.sort(key=lambda x: x[0], reverse=True)
    
    count = min(select_data.get("maxCount", 1), max(select_data.get("minCount", 1), 1))
    best_indices = [s[1] for s in scored_options[:count]]
    return best_indices

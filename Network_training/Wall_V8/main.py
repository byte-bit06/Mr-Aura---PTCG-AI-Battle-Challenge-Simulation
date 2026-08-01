import os
import sys
import json
import csv
import time
import random
from collections import defaultdict, Counter

from cg.api import (AreaType, CardType, EnergyType, Observation, SelectContext,
                    OptionType, Card, Pokemon, all_card_data, to_observation_class)

# ── Search Imports ─────────────────────────────────────────────────────────────
try:
    from cg.api import search_begin, search_step, search_end
    _SEARCH_IMPORT_OK = True
except Exception:
    _SEARCH_IMPORT_OK = False

USE_SEARCH = True
N_DET = 3
K_OPP = 3
MAX_SUBSTEPS = 40
TIME_BUDGET_S = 0.80
SEARCH_MAX_OPTS = 24
DUMMY_BASIC = 646
DUMMY_ENERGY = 7

_search_ok = _SEARCH_IMPORT_OK
_search_reported = False

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
    return [344]*4 + [345]*3 + [756]*2 + [117]*2 + [1227]*4 + [1182]*4 + [1219]*4 + [1194]*2 + [1225]*2 + [1197] + [1187] + [1122]*4 + [1147]*4 + [1121]*3 + [1086]*2 + [1123] + [1159] + [1257] + [1242] + [11]*4 + [18]*4 + [14]*3 + [20]*2 + [1]

my_deck = load_deck()
_load_card_database()

all_card = all_card_data()
_CG_CARD_TABLE = {c.cardId: c for c in all_card}

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
Kangaskhan = 756
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

# ── Archetype Templates for Opponent Belief Modeling ───────────────────────────
_BUILTIN_TEMPLATES = [
    ("Alakazam_ex", Counter([741, 741, 741, 741, 742, 742, 742, 742, 743, 743, 743, 743, 65, 65, 66, 66, 66, 66, 305, 1079, 1079, 1079, 1081, 1081, 1081, 1086, 1086, 1086, 1086, 1097, 1097, 1097, 1129, 1152, 1152, 1152, 1152, 1182, 1182, 1182, 1184, 1197, 1197, 1197, 1225, 1225, 1225, 1225, 1227, 1231, 1231, 1231, 1231, 1247, 5, 5, 19, 19, 19, 19])),
    ("Lucario_ex", Counter([677, 677, 677, 678, 678, 678, 678, 673, 673, 674, 674, 675, 675, 676, 676, 676, 1102, 1102, 1102, 1102, 1123, 1123, 1141, 1141, 1141, 1141, 1142, 1142, 1142, 1142, 1152, 1152, 1152, 1152, 1159, 1182, 1182, 1192, 1192, 1192, 1192, 1227, 1227, 1227, 1227, 1252, 1252, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6])),
    ("Dragapult_ex", Counter([119, 119, 119, 119, 120, 120, 121, 121, 121, 121, 1122, 1122, 1122, 1147, 1147, 1147, 1079, 1079, 1182, 1182, 1219, 1219, 1219, 1227, 1227, 1227, 18, 18, 18, 18, 5, 5, 5, 5])),
    ("Archaludon", Counter([169, 169, 169, 190, 190, 190, 1122, 1122, 1147, 1147, 1219, 1219, 1227, 1227, 1, 1, 1, 1, 1, 1, 1, 1])),
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

_BASIC_ENERGY = {i: i for i in range(1, 9)}
def _pokemon_ids(counter):
    return {cid for cid in counter if _CG_CARD_TABLE.get(cid) and _CG_CARD_TABLE[cid].cardType == CardType.POKEMON}
_TEMPLATE_SIG = [(n, _pokemon_ids(c), c, ids) for (n, c, ids) in _TEMPLATES]

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
    elif my_active_id == Kangaskhan and my_energy >= 3: my_dmg = 100
    
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

# ── Heuristic Option Scoring Engine ──────────────────────────────────────────
def heuristic_scores(obs):
    info = extract_board_info(obs.to_dict() if hasattr(obs, "to_dict") else obs)
    select_data = obs.select if hasattr(obs, "select") else obs.get("select", {})
    options = select_data.option if hasattr(select_data, "option") else select_data.get("option", [])
    
    hand = info.get("hand", [])
    turn = info.get("turn", 1)
    my_active_id = info.get("my_active_id")
    bench_count = len(info.get("my_bench", []))
    opp_hand = info.get("opp_hand_count", 0)
    hand_size = info.get("hand_size", len(hand))
    opp_prizes = info.get("opp_prizes", 6)

    scores = []
    for idx, o in enumerate(options):
        o_type = getattr(o, "type", o.get("type", -1) if isinstance(o, dict) else -1)
        cid = getattr(o, "cardId", None) or getattr(o, "id", None) or (o.get("cardId") if isinstance(o, dict) else None)
        score = 0.0

        if o_type == 6 and cid == Kangaskhan:
            if turn >= 3 or opp_prizes <= 4: score = -999999.0
            else: score = 600000.0

        elif o_type == 6 and cid in {Dwebble, Ogerpon}:
            if bench_count == 0: score = 1650000.0
            elif cid in {Dwebble, Crustle}: score = 800000.0
            else: score = 500000.0

        elif o_type == 6 and cid == Iono:
            if opp_hand >= 5: score = 1600000.0
            else: score = 850000.0

        elif o_type == 6 and hand_size < 4 and cid in {Lillie, Petrel, Arven}:
            if cid == Lillie: score = 1500000.0
            elif cid == Petrel: score = 1450000.0
            elif cid == Arven: score = 1400000.0

        elif o_type in {6, 12} and cid == HerosCape:
            score = 1700000.0

        elif o_type == 15 and my_active_id == Dwebble:
            score = 1500000.0

        elif o_type in {6, 7} and cid == Crustle:
            score = 1400000.0

        elif o_type == 11:
            in_play_area = getattr(o, "inPlayArea", o.get("inPlayArea") if isinstance(o, dict) else None)
            in_play_idx = getattr(o, "inPlayIndex", o.get("inPlayIndex", 0) if isinstance(o, dict) else 0)
            
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
                
            max_energy_cap = 4 if target_id == Kangaskhan else 3
            
            if target_energy >= max_energy_cap:
                score = -999999.0
            else:
                optimal_id = info.get("optimal_active")
                is_grass = (cid == GrassEnergy)
                
                if target_id == Dwebble and is_active_target and (345 not in hand):
                    score = 1480000.0
                elif my_active_id == Kangaskhan and not is_active_target:
                    base_e = 1350000.0
                    if target_id in {Crustle, Dwebble} and not target_has_grass and is_grass:
                        base_e += 25000.0
                    score = base_e
                else:
                    if target_energy == 2: base_e = 1320000.0
                    elif target_energy == 1: base_e = 1310000.0
                    else: base_e = 1300000.0
                    
                    if target_id in {Crustle, Dwebble} and not target_has_grass and is_grass:
                        base_e += 25000.0
                    elif is_grass:
                        base_e += 15000.0
                        
                    if target_id == optimal_id: base_e += 10000.0
                    elif target_id in {Crustle, Dwebble, Ogerpon}: base_e += 5000.0
                    score = base_e

        elif o_type == 15:
            score = 1100000.0

        elif o_type in {6, 13} and cid in {NestBall, UltraBall, HeavyBall, BuddyPuffin, EarthenVessel, Arven}:
            score = 850000.0

        elif o_type == 6 and cid == BossOrders:
            if not check_boss_conditions(info): score = -999999.0
            else: score = 500000.0

        elif o_type == 6 and cid == SwitchCard:
            current_active_id = info.get("my_active_id")
            optimal_id = info.get("optimal_active")
            
            bench_has_prepared_wall = False
            for b in info.get("my_bench", []):
                b_id = b.get("id")
                if b_id == optimal_id or (b_id == Crustle and len(b.get("energies", [])) >= 2) or (b_id == Ogerpon and len(b.get("energies", [])) >= 2):
                    bench_has_prepared_wall = True
                    break
            
            if current_active_id == Kangaskhan and bench_has_prepared_wall:
                score = 1550000.0
            elif current_active_id != optimal_id and bench_has_prepared_wall:
                score = 500000.0
            else:
                score = -10000.0

        elif o_type == 6 and hand_size < 4:
            if cid == Petrel: score = 400000.0
            elif cid == Lillie: score = 350000.0

        elif o_type == 6 and cid in {JumboIceCream, CommunityCenter}:
            if info.get("my_active_hp", 999) < info.get("my_active_max_hp", 999): score = 350000.0
            else: score = -5000.0

        elif o_type == 6 and cid in {Xerosic, Morty, TRFactory}:
            score = 200000.0

        else:
            score = 1.0
            
        scores.append(score)

    return scores

# ── Opponent Belief Modeling & Sampling ────────────────────────────────────────
def _my_visible(state, me_i):
    me = state.players[me_i]
    seen = Counter()
    for c in me.hand or []: seen[c.id] += 1
    for c in me.discard: seen[c.id] += 1
    for c in me.prize:
        if c is not None: seen[c.id] += 1
    for p in me.active + me.bench:
        if p is None: continue
        seen[p.id] += 1
        for c in p.energyCards: seen[c.id] += 1
        for c in p.tools: seen[c.id] += 1
        for c in p.preEvolution: seen[c.id] += 1
    if state.stadium and state.stadium[0].playerIndex == me_i:
        seen[state.stadium[0].id] += 1
    return seen

def _op_visible(state, op_i):
    op = state.players[op_i]
    seen = Counter()
    etype = Counter()
    for c in op.discard: seen[c.id] += 1
    for p in op.active + op.bench:
        if p is None: continue
        seen[p.id] += 1
        for c in p.energyCards: seen[c.id] += 1
        for c in p.tools: seen[c.id] += 1
        for c in p.preEvolution: seen[c.id] += 1
        for e in p.energies: etype[int(e)] += 1
    if state.stadium and state.stadium[0].playerIndex == op_i:
        seen[state.stadium[0].id] += 1
    for c in op.prize:
        if c is not None: seen[c.id] += 1
    return seen, etype

def _match_archetype(op_seen):
    op_mons = {cid for cid in op_seen if _CG_CARD_TABLE.get(cid) and _CG_CARD_TABLE[cid].cardType == CardType.POKEMON}
    if not op_mons or not _TEMPLATE_SIG: return None
    best, best_n = None, 0
    for name, sig, cnt, ids in _TEMPLATE_SIG:
        n = len(sig & op_mons)
        if n > best_n: best, best_n = (cnt, ids), n
    return best if best_n >= 1 else None

def _sample_hidden(state, me_i):
    me = state.players[me_i]
    op_i = 1 - me_i
    op = state.players[op_i]

    seen = _my_visible(state, me_i)
    remain = []
    for cid, n in Counter(my_deck).items():
        remain.extend([cid] * max(0, n - seen.get(cid, 0)))
    n_prize_hidden = sum(1 for c in me.prize if c is None)
    need = me.deckCount + n_prize_hidden
    if len(remain) < need:
        remain += [DUMMY_ENERGY] * (need - len(remain))
    random.shuffle(remain)
    your_deck = remain[:me.deckCount]
    fill = iter(remain[me.deckCount:need])
    your_prize = [c.id if c is not None else next(fill, DUMMY_ENERGY) for c in me.prize]

    op_seen, etype = _op_visible(state, op_i)
    tpl = _match_archetype(op_seen)
    if tpl is not None:
        cnt, _ = tpl
        pool = []
        for cid, n in cnt.items():
            pool.extend([cid] * max(0, n - op_seen.get(cid, 0)))
    else:
        etop = max(etype.items(), key=lambda x: x[1])[0] if etype else 7
        energy_id = _BASIC_ENERGY.get(etop, 7)
        top_card = max(op_seen.items(), key=lambda x: x[1])[0] if op_seen else None
        pool = ([top_card] * 30 if top_card else []) + [energy_id] * 30
        pool += [DUMMY_BASIC] * 8

    n_op_prize_hidden = sum(1 for c in op.prize if c is None)
    op_need = op.deckCount + n_op_prize_hidden + op.handCount
    if len(pool) < op_need:
        pool += [DUMMY_ENERGY] * (op_need - len(pool))
    random.shuffle(pool)
    opponent_deck = pool[:op.deckCount]
    off = op.deckCount
    fill_op = iter(pool[off:off + n_op_prize_hidden])
    opponent_prize = [c.id if c is not None else next(fill_op, DUMMY_ENERGY) for c in op.prize]
    off += n_op_prize_hidden
    opponent_hand = pool[off:off + op.handCount]
    opponent_active = [DUMMY_BASIC] if (op.active and op.active[0] is None) else []

    return dict(your_deck=your_deck, your_prize=your_prize, opponent_deck=opponent_deck, opponent_prize=opponent_prize, opponent_hand=opponent_hand, opponent_active=opponent_active)

# ── Leaf State Evaluation ──────────────────────────────────────────────────────
def _leaf_eval(state, me_i):
    if state is None: return 0.0
    if state.result is not None and state.result >= 0:
        if state.result == me_i: return 1e7
        if state.result == 2: return 0.0
        return -1e7
    me = state.players[me_i]
    op = state.players[1 - me_i]
    my_field = [p for p in (me.active + me.bench) if p]
    op_field = [p for p in (op.active + op.bench) if p]
    my_hp = sum(p.hp for p in my_field)
    op_hp = sum(p.hp for p in op_field)
    my_en = sum(len(p.energies) for p in my_field)
    op_en = sum(len(p.energies) for p in op_field)
    no_active = 0 if (me.active and me.active[0]) else 1
    return (1000.0 * (len(op.prize) - len(me.prize)) + my_hp - op_hp + 5.0 * (my_en - op_en) - 4000.0 * no_active)

def _greedy_pick(obs):
    sel = obs.select
    n = len(sel.option)
    if n == 0: return [], []
    try: sc = heuristic_scores(obs)
    except Exception: sc = list(range(n, 0, -1))
    order = sorted(range(n), key=lambda i: sc[i], reverse=True)
    k = min(sel.maxCount, n)
    k = max(k, min(max(1, sel.minCount), n))
    return order[:k], order

def _greedy_complete_turn(sid, cur, owner, deadline):
    for _ in range(MAX_SUBSTEPS):
        if time.monotonic() > deadline: return sid, cur
        cs = cur.current
        if cs is None or (cs.result is not None and cs.result >= 0): return sid, cur
        if cs.yourIndex != owner or cur.select is None: return sid, cur
        choice, _ = _greedy_pick(cur)
        if not choice: return sid, cur
        try: ss = search_step(sid, choice)
        except Exception: return sid, cur
        sid, cur = ss.searchId, ss.observation
    return sid, cur

def _advance_forced(sid, cur, owner, deadline, limit=8):
    for _ in range(limit):
        if time.monotonic() > deadline: break
        cs = cur.current
        if (cs is None or cur.select is None or cs.yourIndex != owner or cur.select.context == SelectContext.MAIN or (cs.result is not None and cs.result >= 0)): break
        ch, _ = _greedy_pick(cur)
        if not ch: break
        try: ss = search_step(sid, ch)
        except Exception: break
        sid, cur = ss.searchId, ss.observation
    return sid, cur

# ── 2-Ply Minimax Lookahead Search ─────────────────────────────────────────────
def _search_decide(obs, base_order, base_scores):
    global _search_ok, _search_reported
    if not (USE_SEARCH and _search_ok): return None
    st = obs.current
    sel = obs.select
    if st is None or sel is None or sel.context != SelectContext.MAIN: return None
    n = len(sel.option)
    if n < 3 or n > SEARCH_MAX_OPTS or st.turn < 2: return None
    if getattr(obs, "search_begin_input", None) is None:
        _search_ok = False
        return None

    me_i = st.yourIndex
    heur_top = base_order[0]
    cand = [heur_top]
    for i in base_order[1:]:
        if sel.option[i].type in (OptionType.ATTACK, OptionType.END): continue
        if base_scores[i] < 0: continue
        cand.append(i)
        if len(cand) >= 8: break
    if len(cand) < 2: return None

    t0 = time.monotonic()
    deadline = t0 + TIME_BUDGET_S
    acc = {i: 0.0 for i in cand}
    n_eval = {i: 0 for i in cand}
    began = False
    try:
        for det in range(N_DET):
            if time.monotonic() > deadline: break
            hidden = _sample_hidden(st, me_i)
            try:
                ss0 = search_begin(obs, **hidden)
                began = True
            except Exception:
                _search_ok = False
                return None
            root_sid = ss0.searchId

            for idx in cand:
                if time.monotonic() > deadline: break
                try: ss = search_step(root_sid, [idx])
                except Exception: continue
                sid1, cur = ss.searchId, ss.observation
                sid1, cur = _greedy_complete_turn(sid1, cur, me_i, deadline)
                cs = cur.current
                if (cs is None or (cs.result is not None and cs.result >= 0) or cs.yourIndex == me_i or cur.select is None):
                    acc[idx] += _leaf_eval(cs, me_i)
                    n_eval[idx] += 1
                    continue
                sid1, cur = _advance_forced(sid1, cur, 1 - me_i, deadline)
                cs = cur.current
                if (cs is None or cur.select is None or cur.select.context != SelectContext.MAIN or cs.yourIndex == me_i):
                    acc[idx] += _leaf_eval(cs, me_i)
                    n_eval[idx] += 1
                    continue
                _, op_order = _greedy_pick(cur)
                worst = None
                for k in range(min(K_OPP, len(op_order))):
                    if time.monotonic() > deadline: break
                    try: ss2 = search_step(sid1, [op_order[k]])
                    except Exception: continue
                    sid2, cur2 = ss2.searchId, ss2.observation
                    sid2, cur2 = _greedy_complete_turn(sid2, cur2, 1 - me_i, deadline)
                    sid2, cur2 = _advance_forced(sid2, cur2, me_i, deadline, limit=6)
                    v = _leaf_eval(cur2.current, me_i)
                    worst = v if worst is None else min(worst, v)
                if worst is None: worst = _leaf_eval(cs, me_i)
                acc[idx] += worst
                n_eval[idx] += 1

            try: search_end()
            except Exception: pass
            began = False

        n_top = n_eval.get(heur_top, 0)
        if n_top == 0: return None
        evaluated = [i for i in cand if n_eval[i] == n_top]
        avg = {i: acc[i] / n_eval[i] + 1e-6 * base_scores[i] for i in evaluated}
        best = max(evaluated, key=lambda i: avg[i])
        if best == heur_top: return None
        if avg[best] < avg[heur_top] + 500.0: return None
        return best
    except Exception:
        return None
    finally:
        if began:
            try: search_end()
            except Exception: pass

# ── Main Agent Function ────────────────────────────────────────────────────────
def _agent_impl(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None: return my_deck
    
    context = getattr(obs.select, "context", "")
    options = getattr(obs.select, "option", [])
    if not options: return []
    
    # ── Phase 1: Setup / Mulligan Lead Selection ──────────────────────────────
    if "SETUP" in str(context).upper() or "ACTIVE" in str(context).upper():
        info = extract_board_info(obs_dict)
        hand = info.get("hand", [])
        is_second = info.get("is_second", False)
        holding_dwebble_crustle = (Dwebble in hand and Crustle in hand)
        
        if is_second and holding_dwebble_crustle:
            lead_priority = [Dwebble, Kangaskhan, Crustle, Ogerpon]
        else:
            lead_priority = [Kangaskhan, Dwebble, Crustle, Ogerpon]
            
        for lead_choice in lead_priority:
            for idx, o in enumerate(options):
                cid = getattr(o, "cardId", None) or getattr(o, "id", None)
                if cid == lead_choice:
                    return [idx]
        return [0]
        
    base_scores = heuristic_scores(obs)
    n = len(options)
    base_order = sorted(range(n), key=lambda i: base_scores[i], reverse=True)
    
    # ── Try 2-Ply Minimax Lookahead Search Verification ────────────────────────
    pick = _search_decide(obs, base_order, base_scores)
    if pick is not None:
        k = min(getattr(obs.select, "maxCount", 1), n)
        return [pick] + [i for i in base_order if i != pick][:k-1]
        
    k = min(getattr(obs.select, "maxCount", 1), n)
    return base_order[:k]

def agent(obs_dict: dict) -> list[int]:
    try:
        return _agent_impl(obs_dict)
    except Exception:
        try:
            obs = to_observation_class(obs_dict)
            if obs.select is None: return my_deck
            n = len(obs.select.option)
            k = min(max(1, obs.select.minCount), n) if n else 0
            return list(range(k))
        except Exception:
            return [0]

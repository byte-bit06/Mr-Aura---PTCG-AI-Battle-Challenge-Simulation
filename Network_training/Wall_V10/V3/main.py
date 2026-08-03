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
# ── Card Database & Deck Loader ───────────────────────────────────────────────
_CARD_DB = {}
_CARD_INFO_CACHE = {}

def _load_card_database():
    global _CARD_DB, _CARD_INFO_CACHE
    if _CARD_INFO_CACHE: return
    try:
        base_dir = os.path.dirname(__file__)
    except NameError:
        base_dir = "/kaggle_simulations/agent"
    candidates = [
        "EN_Card_Data copy.csv", "data/EN_Card_Data copy.csv", "../data/EN_Card_Data copy.csv", "../../data/EN_Card_Data copy.csv",
        "EN_Card_Data.csv", "data/EN_Card_Data.csv", "../data/EN_Card_Data.csv", "../../data/EN_Card_Data.csv",
        r"c:\Users\Shaur\Coding Project\AWS\data\EN_Card_Data copy.csv"
    ]
    for candidate in candidates:
        for p in [candidate, os.path.join(base_dir, candidate)]:
            if os.path.exists(p):
                try:
                    with open(p, mode='r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            try:
                                cid_raw = row.get("Card ID", "").strip()
                                if not cid_raw: continue
                                cid = int(cid_raw)
                                if cid not in _CARD_INFO_CACHE:
                                    _CARD_INFO_CACHE[cid] = {
                                        "name": row.get("Card Name", "").strip(),
                                        "is_ex": False,
                                        "has_ability": False,
                                        "hp": 0,
                                        "retreat": 0,
                                        "max_damage": 0,
                                        "rows": []
                                    }
                                c_info = _CARD_INFO_CACHE[cid]
                                c_info["rows"].append(row)

                                # Parse EX status from Rule, Stage, and Card Name
                                rule = row.get("Rule", "").lower()
                                stage = row.get("Stage (Pokémon)/Type (Energy and Trainer)", "").lower()
                                cname = row.get("Card Name", "").lower()
                                if "ex" in rule or "ex" in stage or " ex" in cname or "ex " in cname or cname.endswith("ex"):
                                    c_info["is_ex"] = True

                                # Parse Ability status (Move Name starts with [Ability] or Category is Ability)
                                move_name = row.get("Move Name", "")
                                cat = row.get("Category", "").lower()
                                if "[ability]" in move_name.lower() or cat == "ability":
                                    c_info["has_ability"] = True

                                # Parse HP
                                hp_val = row.get("HP", "")
                                if hp_val and hp_val.isdigit():
                                    c_info["hp"] = max(c_info["hp"], int(hp_val))

                                # Parse Move Damage
                                dmg_val = row.get("Damage", "").replace("×", "").replace("+", "").replace("?", "").strip()
                                if dmg_val.isdigit():
                                    c_info["max_damage"] = max(c_info["max_damage"], int(dmg_val))

                                # Parse Retreat Cost
                                ret_val = row.get("Retreat", "").strip()
                                if ret_val.isdigit():
                                    c_info["retreat"] = max(c_info["retreat"], int(ret_val))

                                _CARD_DB[cid] = row
                            except Exception: pass
                    if _CARD_INFO_CACHE: return
                except Exception: pass

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
    from cg.api import all_card_data, search_begin, search_step, search_end, search_release, SelectContext, OptionType, to_observation_class
    _CG_CARD_TABLE = {c.cardId: c for c in all_card_data()}
    _SEARCH_OK = True
except Exception:
    _CG_CARD_TABLE = {}
    _SEARCH_OK = False

def get_opponent_max_threat(op_player, opp_is_ex=False, opp_has_ability=False) -> int:
    """
    Safely calculates the maximum counter-damage threat the opponent can deal next turn
    assuming +1 energy attachment on their active or benched attackers.
    """
    if op_player is None: return 0
    max_dmg = 0
    
    # Check Active and Bench attackers safely
    active_pkmn = op_player.active[0] if (getattr(op_player, "active", None) and len(op_player.active) > 0) else None
    bench_list = list(getattr(op_player, "bench", [])) if getattr(op_player, "bench", None) else []
    all_opp_pkmn = ([active_pkmn] if active_pkmn else []) + bench_list

    for p in all_opp_pkmn:
        if p is None: continue
        p_id = getattr(p, "id", None)
        if not p_id: continue
        
        # Calculate base move damage from card database
        base_dmg = get_card_attack_damage(p_id)
        if base_dmg > max_dmg:
            max_dmg = base_dmg
            
    return max_dmg

def get_prize_count(player_obj) -> int:
    """
    Safely retrieves the number of REMAINING prize cards for a player.
    Supports list format (player.prize), integer format (player.prizeCount), and dict fallback.
    In Pokemon TCG, each player starts with 6 prizes; Prizes Taken = 6 - remaining_prizes.
    """
    if player_obj is None: return 6
    if isinstance(player_obj, dict):
        p_val = player_obj.get("prize")
        if isinstance(p_val, list): return len(p_val)
        elif isinstance(p_val, (int, float)): return int(p_val)
        p_cnt = player_obj.get("prizeCount")
        if p_cnt is not None: return int(p_cnt)
        return 6
    
    p_val = getattr(player_obj, "prize", None)
    if isinstance(p_val, list): return len(p_val)
    elif isinstance(p_val, (int, float)): return int(p_val)
    p_cnt = getattr(player_obj, "prizeCount", None)
    if p_cnt is not None: return int(p_cnt)
    return 6

def evaluate_simulated_state(initial_obs, final_obs) -> float:
    """
    Evaluates a future simulated state (after full turn rollout) using state-based heuristics:
    1. Prizes Taken vs Conceded (Delta & Net count)
    2. Damage Dealt vs Damage Taken (Net HP differential)
    3. Wall Immunity & Active Stability (+5000.0 if immune wall active, -3000.0 if exposed to 1-hit KO)
    4. Board Infrastructure & Resource Health (Bench setup & hand count)
    """
    if final_obs is None or getattr(final_obs, "current", None) is None: return -float('inf')
    st_final = final_obs.current
    if getattr(st_final, "result", None) is not None and st_final.result != -1:
        if st_final.result == st_final.yourIndex:
            return 100000.0  # WIN!
        else:
            return -100000.0 # LOSS!
            
    my_idx = getattr(st_final, "yourIndex", 0)
    op_idx = 1 - my_idx
    players_final = getattr(st_final, "players", [])
    if not players_final or len(players_final) <= max(my_idx, op_idx):
        return 0.0

    me_final = players_final[my_idx]
    op_final = players_final[op_idx]

    # Initial state reference
    st_init = getattr(initial_obs, "current", None) if initial_obs else None
    players_init = getattr(st_init, "players", []) if st_init else []
    me_init = players_init[my_idx] if len(players_init) > my_idx else None
    op_init = players_init[op_idx] if len(players_init) > op_idx else None

    val = 0.0

    # ── 1. PRIZE CARDS HEURISTIC (Prizes Won vs Prizes Given) ──
    me_prizes_rem_init = get_prize_count(me_init) if me_init else 6
    op_prizes_rem_init = get_prize_count(op_init) if op_init else 6

    me_prizes_rem_final = get_prize_count(me_final)
    op_prizes_rem_final = get_prize_count(op_final)

    # Net prizes taken total (6 - remaining)
    me_prizes_taken_total = max(0, 6 - me_prizes_rem_final)
    op_prizes_taken_total = max(0, 6 - op_prizes_rem_final)

    # Prizes won/given during THIS turn sequence
    prizes_won_this_turn = max(0, me_prizes_rem_init - me_prizes_rem_final)
    prizes_given_this_turn = max(0, op_prizes_rem_init - op_prizes_rem_final)

    val += me_prizes_taken_total * 2500.0
    val -= op_prizes_taken_total * 3000.0
    val += prizes_won_this_turn * 4000.0   # Big bonus for taking prize card during turn!
    val -= prizes_given_this_turn * 4500.0 # Heavy penalty if we lose a prize card during turn!

    # ── 2. DAMAGE DEALT VS DAMAGE TAKEN HEURISTIC ──
    my_active_init = me_init.active[0] if (me_init and getattr(me_init, "active", None) and len(me_init.active) > 0) else None
    op_active_init = op_init.active[0] if (op_init and getattr(op_init, "active", None) and len(op_init.active) > 0) else None

    my_active_final = me_final.active[0] if (getattr(me_final, "active", None) and len(me_final.active) > 0) else None
    op_active_final = op_final.active[0] if (getattr(op_final, "active", None) and len(op_final.active) > 0) else None

    hp_me_init = getattr(my_active_init, "hp", 0) if my_active_init else 0
    hp_op_init = getattr(op_active_init, "hp", 0) if op_active_init else 0

    hp_me_final = getattr(my_active_final, "hp", 0) if my_active_final else 0
    hp_op_final = getattr(op_active_final, "hp", 0) if op_active_final else 0

    # Calculate damage dealt to opponent and damage taken by us
    damage_dealt = max(0, hp_op_init - hp_op_final) if (op_active_init and op_active_final and op_active_init.id == op_active_final.id) else (hp_op_init if op_active_init else 0)
    damage_taken = max(0, hp_me_init - hp_me_final) if (my_active_init and my_active_final and my_active_init.id == my_active_final.id) else (hp_me_init if my_active_init else 0)

    val += damage_dealt * 10.0   # Reward dealing damage to opponent
    val -= damage_taken * 12.0   # Penalize taking damage

    # ── 3. WALL IMMUNITY & ACTIVE THREAT STABILITY ──
    opp_is_ex = is_card_ex(getattr(op_active_final, "id", None)) if op_active_final else False
    opp_has_ability = card_has_ability(getattr(op_active_final, "id", None)) if op_active_final else False

    if my_active_final:
        active_hp = getattr(my_active_final, "hp", 0)
        active_id = getattr(my_active_final, "id", None)
        active_energies = len(getattr(my_active_final, "energies", []))
        
        val += active_hp * 2.0
        val += active_energies * 300.0
        
        # Wall Immunity bonus
        is_crustle_immune = (active_id == Crustle and opp_is_ex)
        is_ogerpon_immune = (active_id == Ogerpon and opp_has_ability)
        
        if is_crustle_immune or is_ogerpon_immune:
            val += 5000.0  # TOP WALL IMMUNITY STABILITY BONUS!

        # Threat Assessment & Fainting Risk Penalty
        op_max_damage = get_opponent_max_threat(op_final, opp_is_ex, opp_has_ability)
        if op_max_damage >= active_hp and not is_crustle_immune and not is_ogerpon_immune:
            val -= 3000.0  # Heavy penalty for exposing active to a 1-hit KO!

    # ── 4. RESOURCE & ENGINE HEALTH ──
    hand_count = len(getattr(me_final, "hand", []))
    if hand_count > 3:
        val += 500.0
    elif hand_count <= 2:
        val -= 1000.0  # Top-decking penalty

    # ── 5. BENCH SETUP PROGRESSION ──
    me_bench = list(getattr(me_final, "bench", [])) if getattr(me_final, "bench", None) else []
    dwebble_backup_count = 0
    for p in me_bench:
        if p is None: continue
        p_id = getattr(p, "id", None)
        p_energies = len(getattr(p, "energies", []))
        val += p_energies * 200.0
        
        if p_id == Crustle:
            val += 800.0
            dwebble_backup_count += 1
        elif p_id == Dwebble:
            val += 500.0
            dwebble_backup_count += 1

    if dwebble_backup_count >= 2:
        val += 1000.0  # 2-Dwebble setup readiness bonus!

    return val

def rollout_full_turn(sid, cur_obs, your_index):
    """
    Simulates step-by-step through the remainder of the current turn until OptionType.END is executed.
    """
    steps = 0
    while steps < 25:
        if getattr(cur_obs, "current", None) is None: break
        if cur_obs.current.result is not None and cur_obs.current.result != -1: break
        if cur_obs.current.yourIndex != your_index: break
        if getattr(cur_obs, "select", None) is None: break
        
        obs_dict = cur_obs.to_dict() if hasattr(cur_obs, "to_dict") else {}
        sel = agent(obs_dict)
        if not sel: break
        
        # Check if option chosen is OptionType.END
        if cur_obs.select.context == SelectContext.MAIN and cur_obs.select.option[sel[0]].type == OptionType.END:
            ar = search_step(sid, sel)
            if not (getattr(ar, "error", 0) != 0 or ar.state is None):
                cur_obs = ar.state.observation
            break
            
        ar = search_step(sid, sel)
        if getattr(ar, "error", 0) != 0 or ar.state is None: break
        cur_obs, sid = ar.state.observation, ar.state.searchId
        steps += 1
    return cur_obs

def run_mcts_lookahead_search(obs_dict: dict, heuristic_candidates: list[int]) -> list[int]:
    """
    MCTS Full Turn Evaluation:
    Evaluates every candidate action by running a full turn rollout until turn end,
    scoring each outcome using state heuristics (prizes won/given, damage dealt/taken, wall stability).
    """
    if not _SEARCH_OK or not heuristic_candidates or len(heuristic_candidates) <= 1:
        return heuristic_candidates
        
    try:
        obs = to_observation_class(obs_dict)
        if obs is None or obs.select is None or obs.select.context != SelectContext.MAIN:
            return heuristic_candidates
            
        top_candidates = heuristic_candidates[:5]
        best_val = -float('inf')
        best_action = top_candidates[0]
        
        for cand in top_candidates:
            try:
                sbi = search_begin(obs, your_deck=my_deck)
                if getattr(sbi, "error", 0) != 0 or sbi.state is None: continue
                sid = sbi.state.searchId
                ar = search_step(sid, [cand])
                if getattr(ar, "error", 0) != 0 or ar.state is None: continue
                
                final_obs = rollout_full_turn(ar.state.searchId, ar.state.observation, obs.current.yourIndex)
                score_val = evaluate_simulated_state(obs, final_obs)
                
                if score_val > best_val:
                    best_val = score_val
                    best_action = cand
            except Exception:
                pass
                
        if best_action != top_candidates[0]:
            log_rule_execution(f"  [MCTS FULL-TURN LOOKAHEAD] Candidate {best_action} selected over {top_candidates[0]} with Rollout Score {best_val}!")
            return [best_action] + [c for c in heuristic_candidates if c != best_action]
            
    except Exception as e:
        log_rule_execution(f"  [MCTS LOOKAHEAD EXCEPTION] {e}")
        
    return heuristic_candidates

def is_card_ex(cid):
    if not cid: return False
    if cid in _CARD_INFO_CACHE:
        return _CARD_INFO_CACHE[cid]["is_ex"]
    c = _CG_CARD_TABLE.get(cid)
    if c: return getattr(c, 'ex', False) or getattr(c, 'megaEx', False)
    return False

def card_has_ability(cid):
    if not cid: return False
    if cid in _CARD_INFO_CACHE:
        return _CARD_INFO_CACHE[cid]["has_ability"]
    c = _CG_CARD_TABLE.get(cid)
    if c: return len(getattr(c, 'abilities', [])) > 0 or getattr(c, 'ability', None) is not None
    return False

def get_card_attack_damage(cid):
    if not cid: return 0
    if cid in _CARD_INFO_CACHE:
        return _CARD_INFO_CACHE[cid]["max_damage"]
    return 0

def get_card_retreat_cost(cid):
    if not cid: return 0
    if cid in _CARD_INFO_CACHE:
        return _CARD_INFO_CACHE[cid]["retreat"]
    return 0

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
    if cid in _CARD_DB:
        c_name = _CARD_DB[cid].get("Card Name")
        if c_name: return c_name.strip()
    c = _CG_CARD_TABLE.get(cid)
    if c and getattr(c, 'name', None):
        return getattr(c, 'name').strip()
    return f"Card #{cid}"

def get_pokemon_team_info(p_dict, my_idx=None):
    if not p_dict or not isinstance(p_dict, dict):
        return {"id": None, "name": "None", "playerIndex": None, "is_my_team": False, "energy_count": 0}
    cid = p_dict.get("id")
    c_name = get_card_name(cid)
    p_idx = p_dict.get("playerIndex")
    is_mine = (p_idx == my_idx) if (my_idx is not None and p_idx is not None) else None
    
    e_cnt = 0
    e_cards = p_dict.get("energyCards")
    if isinstance(e_cards, list) and len(e_cards) > 0:
        e_cnt = len(e_cards)
    else:
        e_val = p_dict.get("energies")
        if isinstance(e_val, list):
            e_cnt = len(e_val)
        elif isinstance(e_val, (int, float)):
            e_cnt = int(e_val)

    return {
        "id": cid,
        "name": c_name,
        "playerIndex": p_idx,
        "is_my_team": is_mine,
        "energy_count": e_cnt
    }

def get_energy_count(p_dict, expected_player_index=None):
    if not p_dict or not isinstance(p_dict, dict): return 0
    if expected_player_index is not None:
        p_idx = p_dict.get("playerIndex")
        if p_idx is not None and p_idx != expected_player_index:
            return 0  # Reject card if it belongs to the wrong player/team!
    e_cards = p_dict.get("energyCards")
    if isinstance(e_cards, list) and len(e_cards) > 0:
        return len(e_cards)
    e_val = p_dict.get("energies")
    if isinstance(e_val, list):
        return len(e_val)
    elif isinstance(e_val, (int, float)):
        return int(e_val)
    return 0

def format_pokemon_summary(p_dict, my_idx=None):
    if not p_dict or not isinstance(p_dict, dict): return "None"
    info = get_pokemon_team_info(p_dict, my_idx)
    team_label = "OUR TEAM" if info["is_my_team"] else ("OPPONENT" if info["is_my_team"] is False else f"Player {info['playerIndex']}")
    hp = p_dict.get("hp", 0)
    max_hp = p_dict.get("maxHp", 0)
    t_cards = p_dict.get("tools") or []
    t_names = [get_card_name(t.get("id") if isinstance(t, dict) else t) for t in t_cards]
    t_str = f"Tools: {', '.join(t_names)}" if t_names else "Tools: None"
    return f"[{team_label}] {info['name']} (ID #{info['id']}) [HP: {hp}/{max_hp} | Energy: {info['energy_count']} | {t_str}]"

def get_attack_energy_requirement(cid):
    if cid == Crustle or cid == Dwebble: return 3
    elif cid == Ogerpon: return 3
    elif cid == Kangaskhan: return 3
    return 3

def has_enough_energy_for_highest_attack(p_dict):
    if not p_dict or not isinstance(p_dict, dict): return False
    cid = p_dict.get("id")
    req = get_attack_energy_requirement(cid)
    current_energy = get_energy_count(p_dict)
    return current_energy >= req

def get_card_attack_damage(cid):
    if not cid: return 0
    if cid in _CARD_INFO_CACHE:
        return _CARD_INFO_CACHE[cid]["max_damage"]
    return 0

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

    # Area 2 = Hand (or missing area with hand index)
    if area == 2 or (area is None and idx is not None):
        if isinstance(hand, list) and 0 <= idx < len(hand):
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

    opp_b_str = ", ".join([format_pokemon_summary(b) for b in opp_bench]) if opp_bench else "None"
    log_rule_execution(f"  [FORMATTED BOARD STATE] Opponent Active: {format_pokemon_summary(opp_active)} | Opponent Bench ({len(opp_bench)}): [{opp_b_str}]")
    
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
        "my_active_energy": get_energy_count(my_active),
        "my_bench": my_bench,
        "opp_active": opp_active,
        "opp_active_id": opp_active_id,
        "opp_active_hp": opp_active.get("hp", 0) if opp_active else 0,
        "opp_active_energy": get_energy_count(opp_active),
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

DRAGAPULT_LINE_IDS = {119, 120, 121}

def detect_opponent_archetype(info: dict, obs_dict: dict = None) -> str:
    """
    Dynamically inspects the raw game payload (Active, Bench, Discard)
    to identify the opponent's deck archetype (e.g., 'dragapult_spread', 'default').
    """
    opp_active_id = info.get("opp_active_id") if isinstance(info, dict) else None
    opp_bench = info.get("opp_bench", []) if isinstance(info, dict) else []
    opp_bench_ids = [_get_val(b, "id") for b in opp_bench if isinstance(b, dict) and _get_val(b, "id")]

    opp_discard = []
    if isinstance(obs_dict, dict):
        current = obs_dict.get("current", {}) if isinstance(obs_dict, dict) else {}
        players = current.get("player", []) if isinstance(current, dict) else []
        my_idx = current.get("yourIndex", 0) if isinstance(current, dict) else 0
        opp_idx = 1 if my_idx == 0 else 0
        if isinstance(players, list) and len(players) > opp_idx and isinstance(players[opp_idx], dict):
            opp_p = players[opp_idx]
            opp_discard = [_get_val(c, "id") for c in opp_p.get("discard", []) if isinstance(c, dict) and _get_val(c, "id")]

    all_visible_opp_ids = [opp_active_id] + opp_bench_ids + opp_discard

    # Check for Dragapult Spread Archetype from IDs (#119 Dreepy, #120 Drakloak, #121 Dragapult ex) and names
    for cid in all_visible_opp_ids:
        if not cid: continue
        if cid in DRAGAPULT_LINE_IDS:
            return "dragapult_spread"
        cname = get_card_name(cid).lower()
        if any(kw in cname for kw in ["dragapult", "drakloak", "dreepy"]):
            return "dragapult_spread"

    return "default"

def calculate_lead_priority(active_card, opponent_active=None, opponent_deck_archetype="default"):
    """
    Calculates dynamic active lead priority score based on type-advantage, HP, damage output,
    retreat cost, prize vulnerability, and opponent archetype (e.g., Dragapult spread).
    Returns a score on the normalized 0.0 to 100.0 scale.
    """
    if not active_card or not isinstance(active_card, dict):
        return -float('inf')
    
    cid = _get_val(active_card, "id")
    hp = get_card_hp(cid) or _get_val(active_card, "hp", 0)
    max_hp = get_card_hp(cid) or _get_val(active_card, "maxHp", 200)
    retreat = get_card_retreat_cost(cid)
    max_dmg = get_card_attack_damage(cid)
    is_ex = is_card_ex(cid)
    has_ability = card_has_ability(cid)

    opp_cid = _get_val(opponent_active, "id") if isinstance(opponent_active, dict) else None
    opp_is_ex = is_card_ex(opp_cid) if opp_cid else False
    opp_has_ability = card_has_ability(opp_cid) if opp_cid else False

    score = 50.0  # Base neutral score

    # 1. Immunity-First Wall Mechanics
    if opp_is_ex and cid == Crustle:
        log_rule_execution(f"  [MATCHUP MATRIX] Crustle EX Immunity Matchup -> MAX Rank Score 100.0")
        return 100.0  # Crustle is 100% immune to EX Pokemon!
    if opp_has_ability and cid == Ogerpon:
        log_rule_execution(f"  [MATCHUP MATRIX] Ogerpon ex Ability Immunity Matchup -> MAX Rank Score 100.0")
        return 100.0  # Cornerstone Mask Ogerpon ex is 100% immune to Ability Pokemon!

    # 2. Archetype-Specific Prize Vulnerability (e.g., Dragapult spread damage)
    is_spread_archetype = ("dragapult" in str(opponent_deck_archetype).lower() or 
                           (opp_cid and "dragapult" in get_card_name(opp_cid).lower()))
    
    if is_spread_archetype and is_ex and cid == Kangaskhan:
        # Penalize multi-prize basic leads against spread damage to prevent early 2-prize deficits!
        score -= 50.0
        log_rule_execution(f"  [MATCHUP MATRIX] Kangaskhan ex penalized (-50.0) vs Spread Archetype ({opponent_deck_archetype})")

    # 3. Defensive HP & Prize Efficiency
    if is_ex and opp_is_ex:
        score += (hp / float(max_hp) if max_hp else 0.5) * 20.0
        score += (max_dmg / 200.0) * 15.0
    elif is_ex and not opp_is_ex:
        score -= 15.0

    # 4. Low Retreat Cost Bonus
    score -= retreat * 5.0

    return max(0.0, min(100.0, score))

def rank_active_candidate(pokemon, optimal_active_id, is_early_game=False, opponent_active=None, opponent_deck_archetype="default"):
    if not pokemon: return -float('inf')
    cid = _get_val(pokemon, "id")
    hp = _get_val(pokemon, "hp", 0)
    max_hp = _get_val(pokemon, "maxHp", 200) or 200
    energies = _get_val(pokemon, "energies") or []
    energy_count = len(energies)
    
    # Calculate dynamic matchup lead priority score!
    matchup_lead_score = calculate_lead_priority(pokemon, opponent_active, opponent_deck_archetype)

    if cid == Kangaskhan and is_early_game:
        if "dragapult" in str(opponent_deck_archetype).lower():
            log_rule_execution(f"  [RULE APPLIED] Early Kangaskhan Lead PENALIZED vs Dragapult Spread Archetype!")
            return 30.0
        log_rule_execution(f"  [RULE APPLIED] Early-Game Kangaskhan Active Lead Priority Score 100.0!")
        return 100.0

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
        
    return score + (matchup_lead_score * 0.2)

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

def _log_fallback_state(obs_dict: dict, reason: str = ""):
    """Logs fallback [0] state attributes into live_rule_executions.log for automated GA tuning."""
    try:
        current = obs_dict.get("current", {}) if isinstance(obs_dict, dict) else {}
        my_idx = current.get("yourIndex", 0)
        players = current.get("player", [])
        my_p = players[my_idx] if (isinstance(players, list) and len(players) > my_idx and isinstance(players[my_idx], dict)) else {}
        
        my_active = my_p.get("active", {}) if isinstance(my_p, dict) else {}
        hand = my_p.get("hand", []) if isinstance(my_p, dict) else []
        bench = my_p.get("bench", []) if isinstance(my_p, dict) else []
        
        active_id = my_active.get("id") if isinstance(my_active, dict) else None
        active_hp = my_active.get("hp", 0) if isinstance(my_active, dict) else 0
        hand_count = len(hand) if isinstance(hand, list) else 0
        board_state = f"Active ID={active_id}, HP={active_hp}, BenchCount={len(bench)}, HandCount={hand_count}"
        
        log_rule_execution(f"  [FALLBACK LOGGED] Reason: {reason} | Attributes: board_state='{board_state}', active_hp={active_hp}, hand_count={hand_count}, active_id={active_id}")
    except Exception as e:
        log_rule_execution(f"  [FALLBACK LOGGING EXCEPTION] {e}")

def sanitize_action(chosen_indices: list[int], select_data: dict, obs_dict: dict = None) -> list[int]:
    options = select_data.get("option", []) if isinstance(select_data, dict) else []
    n_opts = len(options)
    if n_opts == 0:
        if obs_dict:
            _log_fallback_state(obs_dict, reason="No options available in select_data")
        return [0]

    max_count = select_data.get("maxCount", 1) if isinstance(select_data, dict) else 1
    min_count = select_data.get("minCount", 1) if isinstance(select_data, dict) else 1

    unique = []
    for idx in chosen_indices:
        if 0 <= idx < n_opts and idx not in unique:
            unique.append(idx)

    if not unique:
        if obs_dict:
            _log_fallback_state(obs_dict, reason="Fallback [0] triggered due to empty valid chosen_indices")
        unique = [0]

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
        opponent_deck_archetype = detect_opponent_archetype(info, obs_dict)

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

        # Expected attack damage (Check if active has enough energy for highest attack!)
        my_active_has_enough_energy = has_enough_energy_for_highest_attack(my_active)
        my_dmg = 0
        if my_active_has_enough_energy and my_active_id:
            my_dmg = get_card_attack_damage(my_active_id)

        # Helper state checks for strict rules
        has_other_supporter_in_hand = any(c in {Lillie, Petrel, Hilda, Colress, Morty, Xerosic} for c in hand)
        supporter_already_played = current.get("supporterPlayed", False) if isinstance(current, dict) else False
        supporter_played = supporter_already_played

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

                # ── IMMUNITY-FIRST ACTIVE PROMOTION LOGIC (0.0 to 100.0 SCALE) ──
                if opp_is_ex:
                    if cid == Crustle:
                        r_score = 100.0  # TOP PRIORITY: Immune Wall Crustle!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Crustle Immunity Priority 100.0 (Opponent is EX!)")
                    elif cid == Ogerpon:
                        r_score = 75.0   # Ogerpon ex is 210 HP wall!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Ogerpon ex Wall Priority 75.0 (High HP Wall!)")
                    elif cid == Dwebble:
                        r_score = 10.0    # Low priority basic
                    elif cid == Kangaskhan:
                        r_score = -50.0   # HARD PENALTY: Do not feed free prize cards to EX opponent!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Kangaskhan ex PENALIZED (-50.0): Prevents feeding free prize cards to EX opponent!")
                    else:
                        r_score = 5.0

                elif opp_has_ability:
                    if cid == Ogerpon:
                        r_score = 100.0  # TOP PRIORITY: Immune Wall Ogerpon ex!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Ogerpon ex Immunity Priority 100.0 (Opponent has Ability!)")
                    elif cid == Crustle:
                        r_score = 80.0   # Crustle 150 HP wall
                    elif cid == Dwebble:
                        r_score = 10.0
                    elif cid == Kangaskhan:
                        r_score = -50.0   # HARD PENALTY: Prevents feeding free prize cards!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Kangaskhan ex PENALIZED (-50.0): Prevents feeding free prize cards!")
                    else:
                        r_score = 5.0

                elif matched_pkmn and has_enough_energy_for_highest_attack(matched_pkmn):
                    r_score = 90.0  # Condition 1: Energy Attacker Swap Priority!
                    log_rule_execution(f"  [IF EXECUTED] Active Promotion -> {get_card_name(cid)} Priority 90.0 (Energy Attacker Ready!)")
                elif is_going_second and has_crustle_in_hand:
                    if cid == Dwebble:
                        r_score = 45.0 # Going 2nd with Crustle in hand -> Evolve Dwebble on turn 1!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Dwebble Priority 45.0 (Going 2nd with Crustle in hand!)")
                    elif cid == Crustle:
                        r_score = 40.0
                    elif cid == Ogerpon:
                        r_score = 35.0
                    elif cid == Kangaskhan:
                        r_score = 30.0
                    else:
                        r_score = 5.0
                else:
                    if cid == Crustle:
                        r_score = 50.0
                    elif cid == Ogerpon:
                        r_score = 40.0
                    elif cid == Kangaskhan:
                        r_score = 30.0 # Default Lead with Kangaskhan ex to use draw ability!
                        log_rule_execution(f"  [IF EXECUTED] Active Promotion -> Kangaskhan ex Lead Priority 30.0 (Draw Ability Starter!)")
                    elif cid == Dwebble:
                        r_score = 15.0
                    else:
                        r_score = 5.0

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

                opp_active_hp = info.get("opp_active_hp", 999)
                opp_active_can_be_kodd = (my_dmg > 0 and my_dmg >= opp_active_hp)

                cond_A = (my_energy >= 3 and my_dmg > 0 and my_dmg >= b_hp and not opp_active_can_be_kodd)
                cond_B = (b_energies >= 2 or (b_energies >= 1 and is_card_ex(cid))) and (opp_active_energy == 0 or not is_card_ex(info.get("opp_active_id")))
                cond_C = (b_retreat >= 3 and b_energies == 0)

                if cond_A:
                    score = 95.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Boss's Target Selected (Condition A KO: {c_name}) -> Score 95.0!")
                elif cond_B:
                    score = 90.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Boss's Target Selected (Condition B Building: {c_name}) -> Score 90.0!")
                elif cond_C:
                    score = 85.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Boss's Target Selected (Condition C Trap: {c_name}) -> Score 85.0!")
                else:
                    score = 50.0 + (10.0 if is_card_ex(cid) else 0.0)
                    log_rule_execution(f"  [IF EXECUTED] Branch 1C: Default Opponent Bench Target Selected ({c_name}) -> Score {score}")

            # ── BRANCH 2: POKÉGEAR 3.0 (EMERGENCY DRAW PRIORITY WHEN HAND <= 2) ──
            elif cid == Pokégear:
                if has_other_supporter_in_hand or supporter_already_played:
                    log_rule_execution(f"  [IF EXECUTED] Branch 2: Pokégear 3.0 HARD BANNED (-inf): Supporter already in hand/played!")
                    score = -float('inf')
                else:
                    # Opponent Technique: Aggressive Emergency Draw when hand is low (<= 2 cards)
                    score = 98.0 if hand_size <= 2 else (86.8 + w_trainer * 0.2)
                    log_rule_execution(f"  [IF EXECUTED] Branch 2: Pokégear 3.0 Allowed -> Score {score}")
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
                    score = 94.0 if dwebble_in_play < 2 else (86.5 + w_trainer * 0.3)
                    log_rule_execution(f"  [IF EXECUTED] Branch 3: Ultra Ball Allowed -> Score {score}")
                    has_useful_pre_attack_action = True

            # ── BRANCH 4: LILLIE SUPPORTER (EMERGENCY HAND REFILL WHEN HAND <= 2) ──
            elif cid == Lillie:
                if supporter_already_played:
                    log_rule_execution(f"  [IF EXECUTED] Branch 4: Lillie Supporter HARD BANNED (-inf): Supporter already played!")
                    score = -float('inf')
                elif has_playable_before_lillie and hand_size > 2:
                    log_rule_execution(f"  [IF EXECUTED] Branch 4: Lillie Supporter HARD BANNED (-inf): Playable cards still in hand!")
                    score = -float('inf')
                else:
                    # Opponent Technique: Emergency Hand Refill Score 98.0 when hand <= 2!
                    score = 98.0 if hand_size <= 2 else (86.0 + w_trainer * 0.5)
                    log_rule_execution(f"  [IF EXECUTED] Branch 4: Lillie Supporter Allowed -> Score {score}")
                    has_useful_pre_attack_action = True

            # ── BRANCH 5: BOSS'S ORDERS RELAXED CONDITIONS (DIRECTIVE 9 FIX) ──
            elif cid == BossOrders:
                if supporter_already_played:
                    log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders HARD BANNED (-inf): Supporter already played this turn!")
                    score = -float('inf')
                else:
                    valid_boss_target = False
                    is_immediate_prize_ko = False
                    is_disruptive_engine = False
                    target_reason = ""
                    opp_active_hp = info.get("opp_active_hp", 999)
                    opp_active_can_be_kodd = (my_dmg > 0 and my_dmg >= opp_active_hp)
                    opp_active_has_ability = card_has_ability(info.get("opp_active_id"))

                    ENGINE_PIECES = {
                        "drakloak", "bidoof", "natu", "rotom", "kirlia", "pidgey", "pidgeotto",
                        "charmander", "dwebble", "drakloak ex", "bibarel", "xatu", "ralts",
                        "comfey", "squirtle", "bulbasaur", "pidgeot"
                    }

                    for b in opp_bench:
                        if not isinstance(b, dict): continue
                        b_id = _get_val(b, "id")
                        b_name = get_card_name(b_id).lower()
                        b_hp = _get_val(b, "hp", 999)
                        b_energies = len(_get_val(b, "energies") or [])
                        b_retreat_cost = get_card_retreat_cost(b_id) or _get_val(b, "retreatCost", 0)
                        b_has_ability = card_has_ability(b_id)
                        
                        if b_retreat_cost == 0 and b_id in {Kangaskhan, Abomasnow, Snorlax, Archaludon}:
                            b_retreat_cost = 3

                        if my_active_id == Ogerpon:
                            if b_has_ability and not opp_active_has_ability:
                                valid_boss_target = True
                                target_reason = f"Ogerpon Immunity Rule (Targeting {get_card_name(b_id)} with Ability)"
                                break
                            continue

                        # Sub-Condition 1: Immediate Prize Condition (Active HAS energy and CAN KO benched target)
                        cond_1_immediate_prize = (my_energy >= 3 and my_dmg > 0 and my_dmg >= b_hp and not opp_active_can_be_kodd)

                        # Sub-Condition 2: Disruptive Engine Target (Opponent engine piece on bench, REGARDLESS of active energy!)
                        is_engine_card = any(engine_kw in b_name for engine_kw in ENGINE_PIECES) or b_has_ability
                        cond_2_disruptive_engine = (is_engine_card and (opp_active_energy == 0 or not is_card_ex(info.get("opp_active_id"))))

                        # Condition C: Heavy trap (retreat >= 3 and 0 energy)
                        cond_3_heavy_trap = (b_retreat_cost >= 3 and b_energies == 0)

                        if cond_1_immediate_prize:
                            valid_boss_target = True
                            is_immediate_prize_ko = True
                            target_reason = f"Sub-Condition 1: Immediate Prize KO on {get_card_name(b_id)}!"
                            break
                        elif cond_2_disruptive_engine:
                            valid_boss_target = True
                            is_disruptive_engine = True
                            target_reason = f"Sub-Condition 2: Disruptive Engine Target ({get_card_name(b_id)})"
                            break
                        elif cond_3_heavy_trap:
                            valid_boss_target = True
                            target_reason = f"Condition C: Heavy Trap on {get_card_name(b_id)} (Retreat {b_retreat_cost}, 0 Energy)"
                            break

                    if not valid_boss_target:
                        log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders HARD BANNED (-inf): No valid target met!")
                        score = -float('inf')
                    else:
                        if is_immediate_prize_ko:
                            score = 95.0  # TOP PRIORITY KO
                            log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders Immediate Prize KO -> Score {score} [{target_reason}]!")
                        elif is_disruptive_engine:
                            score = 87.0  # Disruptive Engine Boss Play
                            log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders Disruptive Engine -> Score {score} [{target_reason}]!")
                        else:
                            score = 45.0 + w_trainer * 0.5
                            log_rule_execution(f"  [IF EXECUTED] Branch 5: Boss's Orders Allowed -> Score {score} [{target_reason}]")
                        has_useful_pre_attack_action = True

            # ── BRANCH 6: BENCH PLAYS (EMERGENCY BENCH PROTECTION & SETUP) ──
            elif (o_type in {1, 7} or "PLAY" in ot_str) and cid in {Dwebble, Ogerpon, Kangaskhan} and bench_count < 5:
                if cid == Ogerpon and not opp_has_ability and ogerpon_in_play >= 2:
                    log_rule_execution(f"  [IF EXECUTED] Branch 6: 3rd Ogerpon Bench Deployment HARD BANNED (-inf): Opponent active has no ability!")
                    score = -float('inf')
                elif cid == Kangaskhan and not is_early_game:
                    log_rule_execution(f"  [IF EXECUTED] Branch 6: Late-Game Kangaskhan Bench Deployment HARD BANNED (-inf)")
                    score = -float('inf')
                elif bench_count == 0 and my_hp <= 40:
                    score = 100.0  # EMERGENCY BENCH-OUT PREVENTION: Absolute Top Priority Score 100.0!
                    log_rule_execution(f"  [IF EXECUTED] Branch 6: EMERGENCY BENCH DEPLOYMENT MATCHED -> Score 100.0 (Prevents Instant Loss)!")
                    has_useful_pre_attack_action = True
                elif cid == Dwebble and dwebble_in_play < 2:
                    subscore = w_pokemon * 0.1
                    score = 94.0 + subscore  # Opponent Technique: 2-Dwebble Bench Flood Priority
                    log_rule_execution(f"  [IF EXECUTED] Branch 6: Early Dwebble Bench Play Priority Matched -> Score {score}!")
                    has_useful_pre_attack_action = True
                elif cid == Ogerpon and optimal_lead == Ogerpon:
                    subscore = w_pokemon * 0.1
                    score = 86.5 + subscore
                    has_useful_pre_attack_action = True
                else:
                    subscore = w_pokemon * 0.1
                    score = 86.0 + subscore
                    has_useful_pre_attack_action = True

            # ── BRANCH 7: EVOLUTION (Evolve Dwebble to Crustle — Pre-Attack Wall Priority) ──
            elif (o_type in {4, 6, 7, 9} or "EVOLVE" in ot_str) and (cid == Crustle):
                subscore = w_evolve * 0.2 + (1.0 if optimal_lead == Crustle else 0.0)
                score = 88.0 + subscore
                log_rule_execution(f"  [IF EXECUTED] Branch 7: Crustle Evolution Matched -> Score {score}!")
                has_useful_pre_attack_action = True

            # ── BRANCH 8: OTHER DRAW SUPPORTERS / ITEMS ──
            elif o_type in {7, 3} and (cid in SUPPORTERS_SET or cid in {BuddyPuffin, UltraBall, Pokégear, HerosCape, CommunityCenter, TRFactory, JumboIceCream}):
                subscore = w_trainer * 0.2 + (1.0 if hand_size <= 3 else 0.0)
                score = 86.0 + subscore
                log_rule_execution(f"  [IF EXECUTED] Branch 8: Draw Supporter / Item Play Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── BRANCH 8B: SWITCH CARD (STRICT USER DIRECTIVE CONDITIONS 1, 2, 3) ──
            elif cid == SwitchCard:
                active_is_crustle_wall = (my_active_id == Crustle and opp_is_ex)
                active_is_ogerpon_wall = (my_active_id == Ogerpon and opp_has_ability)
                active_is_immune_wall = (active_is_crustle_wall or active_is_ogerpon_wall)

                benched_has_attacker = False
                benched_crustle_ready = False
                benched_ogerpon_ready = False

                for b in my_bench:
                    if not isinstance(b, dict): continue
                    b_id = _get_val(b, "id")
                    if has_enough_energy_for_highest_attack(b):
                        benched_has_attacker = True
                    if b_id == Crustle:
                        benched_crustle_ready = True
                    if b_id == Ogerpon:
                        benched_ogerpon_ready = True

                cond_1 = (not my_active_has_enough_energy and benched_has_attacker and not active_is_immune_wall)
                cond_2 = (opp_is_ex and my_active_id != Crustle and benched_crustle_ready)
                cond_3 = (opp_has_ability and not opp_is_ex and my_active_id != Ogerpon and benched_ogerpon_ready)

                if cond_1 or cond_2 or cond_3:
                    reason_str = "Cond 1 (Energy Attacker Swap)" if cond_1 else ("Cond 2 (Crustle EX Pivot)" if cond_2 else "Cond 3 (Ogerpon Ability Pivot)")
                    score = 95.0  # TOP PRIORITY: SwitchCard takes priority over energy attachments and setup plays!
                    log_rule_execution(f"  [IF EXECUTED] Branch 8B: SwitchCard Allowed -> MAX SWITCH SCORE 95.0 [{reason_str}]!")
                    has_useful_pre_attack_action = True
                else:
                    log_rule_execution(f"  [IF EXECUTED] Branch 8B: SwitchCard HARD BANNED (-inf): Strict conditions 1, 2, 3 not met!")
                    score = -float('inf')

            # ── BRANCH 9: OPTIMIZED ENERGY ATTACHMENT PRIORITY (ACTIVE EX/WALL FIRST: 92.0 - 98.0 SCALE) ──
            elif o_type in {8, 4} or "ATTACH" in ot_str:
                in_play_area = o.get("inPlayArea")
                in_play_idx = o.get("inPlayIndex", 0)
                is_active_target = (in_play_area in {3, 4, 'active', 'ACTIVE'} or (in_play_area is None and in_play_idx == 0))
                
                target_cid = my_active_id if is_active_target else None
                target_energy = get_energy_count(my_active) if is_active_target else 0
                
                if not is_active_target and in_play_idx is not None and 0 <= in_play_idx < len(my_bench):
                    b_pkmn = my_bench[in_play_idx]
                    target_cid = _get_val(b_pkmn, "id")
                    target_energy = get_energy_count(b_pkmn)

                max_needed_energy = 3
                target_pkmn = my_active if is_active_target else (my_bench[in_play_idx] if in_play_idx is not None and 0 <= in_play_idx < len(my_bench) else None)

                if has_enough_energy_for_highest_attack(target_pkmn) or target_energy >= max_needed_energy:
                    log_rule_execution(f"  [IF EXECUTED] Branch 9: Energy Cap Exceeded HARD BANNED (-inf): Target {get_card_name(target_cid)} already has {target_energy}/{max_needed_energy} energies!")
                    score = -float('inf')
                else:
                    # User Directive: Power up Kangaskhan ex on Active/Bench for heavy 200 HP knockout swings!
                    if is_active_target:
                        if target_cid in {Crustle, Ogerpon, Dwebble}:
                            tier_base = 96.0
                            urgency = 2.0 if target_energy == 0 else (1.0 if target_energy == 1 else 0.5)
                            score = tier_base + urgency  # Score 98.0 for 0-energy active Crustle/Ogerpon!
                        elif target_cid == Kangaskhan:
                            # 200 HP Heavy Hitter Active Bonus (Score 96.0 when at 2 energies for immediate 200 HP swing!)
                            score = 96.0 if target_energy == 2 else 94.0
                        else:
                            score = 93.0
                    else:
                        if target_cid in {Crustle, Ogerpon, Dwebble}:
                            score = 92.0
                        elif target_cid == Kangaskhan:
                            # Powering up benched 300 HP Heavy Hitter Kangaskhan ex
                            score = 88.0
                        else:
                            score = 85.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 9: Optimized Energy Attachment Matched -> Score {score} for {get_card_name(target_cid)}!")
                    has_useful_pre_attack_action = True

            # ── BRANCH 10: STANDARD ATTACKING (85.0 - 90.0 SCALE: EXECUTES AT END OF TURN) ──
            elif o_type in {13, 5} or "ATTACK" in ot_str:
                tier_base = 85.0  # Executed at end of turn after all setup actions
                recoil_dmg = _get_val(o, "recoilDamage", 0) or _get_val(o, "selfDamage", 0)
                if recoil_dmg > 0 and (recoil_dmg >= my_hp or (my_dmg < 20 and my_dmg < opp_hp)):
                    score = -float('inf')
                else:
                    if bench_count == 0 and my_hp <= 40 and not (my_dmg >= opp_hp):
                        log_rule_execution(f"  [IF EXECUTED] Branch 10: Attack HARD BANNED (-inf): Emergency Bench-Out Prevention!")
                        score = -float('inf')
                    else:
                        prize_norm = (6 - my_prizes) / 6.0
                        subscore = w_attack * 0.5 + w_prize * prize_norm * 0.3
                        if my_dmg >= opp_hp and opp_hp > 0:
                            subscore += 10.0  # Guaranteed Lethal KO Bonus (Total = 95.0+)
                        score = tier_base + subscore
                log_rule_execution(f"  [IF EXECUTED] Branch 10: ATTACK MATCHED -> Score {score}!")

            # ── BRANCH 11: HERO'S CAPE & STADIUMS / HEALING ──
            elif o_type in {7, 10} or cid in {HerosCape, CommunityCenter, JumboIceCream, TRFactory}:
                if cid == HerosCape:
                    score = 25.0 + w_tool * 0.5  # Hero's Cape +100 HP Tool equipped immediately!
                    log_rule_execution(f"  [IF EXECUTED] Branch 11: Hero's Cape +100 HP Tool Equipping Matched -> Score {score}")
                else:
                    subscore = w_tool * 0.5
                    score = 18.0 + subscore
                    log_rule_execution(f"  [IF EXECUTED] Branch 11: Stadium / Healing Item Matched -> Score {score}")
                has_useful_pre_attack_action = True

            # ── BRANCH 12: STRICT NO RETREAT RULE (RETREAT IS HARD BANNED -inf TO PREVENT WASTING ENERGIES!) ──
            elif (
                o_type == 12 or
                "RETREAT" in ot_str or
                "RETREAT" in str(o).upper() or
                "RETREAT" in context_str.upper() or
                select_data.get("type") == 4 or
                raw_context_val in {12, 30}
            ):
                log_rule_execution(f"  [IF EXECUTED] Branch 12: Retreat HARD BANNED (-inf): User Rule — Never retreat to preserve energies!")
                score = -float('inf')

            # ── BRANCH 13: END TURN (PREVENT PREMATURE TURN ENDING WHILE PLAYABLE CARDS REMAIN) ──
            elif o_type in {14} or "END" in ot_str:
                if has_useful_pre_attack_action:
                    score = -float('inf') # User Directive 3: HARD BAN ending turn while playable items/supporters remain!
                    log_rule_execution(f"  [IF EXECUTED] Branch 13: End Turn HARD BANNED (-inf): Playable pre-attack actions still remain in hand!")
                else:
                    score = 0.0
                    log_rule_execution(f"  [IF EXECUTED] Branch 13: End Turn Matched -> Score {score}")

            else:
                score = 10.0
                log_rule_execution(f"  [IF EXECUTED] Branch 14: Neutral Fallback Matched -> Score {score}")

            scored_options.append((score, idx))

        scored_options.sort(key=lambda x: x[0], reverse=True)
        best_score, best_idx = scored_options[0]
        chosen_cid = resolve_card_id(options[best_idx], info, current, select_data)
        
        log_rule_execution(f"  => FINAL EXECUTION SELECTION: Option {best_idx} ({get_card_name(chosen_cid)}) with Highest Score: {best_score}\n")

        desc_indices = [i for _, i in scored_options]
        if _SEARCH_OK and len(desc_indices) > 1:
            desc_indices = run_mcts_lookahead_search(obs_dict, desc_indices)
        return sanitize_action(desc_indices, select_data, obs_dict)
    except Exception as e:
        log_rule_execution(f"  [EXCEPTION] {e}")
        return sanitize_action([0], select_data, obs_dict)

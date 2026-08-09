import os, json, copy
from collections import defaultdict

from cg.api import AreaType, CardType, EnergyType, Observation, SelectContext, OptionType, Card, Pokemon, all_card_data, to_observation_class

"""
Raging Bolt V1: Bellowing Thunder Energy-Discard Aggro Engine
===================================================================
Strategy:
1. Bench 3-4x Teal Mask Ogerpon ex → spam Teal Dance to draw + accelerate {G} Energy
2. Raging Bolt ex active: attach {L} + {F} via Crispin / manual, then Bellowing Thunder
   discards any number of energy from board for 70 damage per energy discarded
3. Non-ex Raging Bolt as a Rule Box bypass vs Iron Thorns / Safeguard
4. Latias ex for Dynamo Spark bench snipe utility
5. Fezandipiti ex for draw recovery after KO
"""

# ---- Tunable priority weights ----
WEIGHTS = {
    # PLAY: Pokémon
    "play_pokemon_base": 20000,
    "play_raging_bolt_ex": 25000,
    "play_ogerpon_early": 35000,
    "play_ogerpon_late": 20000,
    "play_fez": 22000,
    "play_latias": 18000,
    "play_raging_bolt_nonex": 15000,
    "play_bench_penalty": 5000,
    # PLAY: Trainers / Supporters
    "bug_catching_set": 28000,
    "tera_orb": 27000,
    "ultra_ball_ogerpon": 30000,
    "ultra_ball_bolt": 26000,
    "ultra_ball_any": 18000,
    "dusk_ball": 22000,
    "pokegear": 20000,
    "energy_search_missing": 24000,
    "energy_search_grass": 16000,
    "energy_retrieval": 15000,
    "night_stretcher_mon": 18000,
    "night_stretcher_energy": 14000,
    "brocks_scouting": 20000,
    "prime_catcher": 32000,
    "boss_kill": 8000,
    "boss_snipe": 6000,
    "crispin_need_both": 35000,
    "crispin_need_one": 25000,
    "crispin_have_both": 5000,
    # ENERGY ATTACHMENT
    "energy_bolt_lightning": 30000,
    "energy_bolt_fighting": 28000,
    "energy_ogerpon_grass": 20000,
    "energy_manual_any": 10000,
    # ABILITY
    "ability_teal_dance": 40000,
    "ability_fez_flip": 35000,
    "ability_latias_dynamo": 25000,
    # ATTACK
    "attack_bellowing_thunder": 50000,
    "attack_dragon_headbutt": 30000,
    "attack_ogerpon_attack": 5000,
    "attack_default": 1000,
    # DISCARD PRIORITY (for Bellowing Thunder energy selection)
    "discard_grass_ogerpon": 10000,
    "discard_extra_bolt": 8000,
    "discard_base_bolt": 2000,
    # RETREAT
    "retreat_swap_attacker": 15000,
    "retreat_default": 2000,
    # MATCHUP-SPECIFIC
    "boss_drag_drakloak": 45000,
    "hammer_drag_grimm_strip": 35000,
}

# ---- Load runtime weight overrides ----
_dir = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_dir, "rb_w.json"), "rb_w.json", "./rb_w.json",
           "Raging_Bolt_V1/rb_w.json",
           "/kaggle_simulations/agent/rb_w.json"):
    if os.path.exists(_p):
        try:
            with open(_p, "r", encoding="utf-8") as _f:
                WEIGHTS.update(json.load(_f))
            break
        except Exception:
            pass

W = WEIGHTS

my_deck = []

all_card = all_card_data()
card_table = {c.cardId: c for c in all_card}

# ---- Card ID Constants ----
Raging_Bolt_ex = 63
Raging_Bolt_nonex = 171
Teal_Mask_Ogerpon_ex = 96
Teal_Mask_Ogerpon = 95
Fezandipiti_ex = 140
Latias_ex = 184
Iron_Thorns_ex = 37

# Trainers
Crispin = 1198
Boss_Orders = 1182
Bug_Catching_Set = 1094
Pokegear = 1122
Tera_Orb = 1127
Ultra_Ball = 1121
Dusk_Ball = 1102
Prime_Catcher = 1088
Energy_Search = 1119
Energy_Retrieval = 1118
Night_Stretcher = 1097
Brocks_Scouting = 1210

# Energy
Basic_G_Energy = 1
Basic_L_Energy = 4
Basic_F_Energy = 6

# Opponent card IDs
Dreepy, Drakloak, Dragapult_ex = 119, 120, 121
Impidimp_G, Morgrem_G, Grimmsnarl_ex = 646, 647, 648
Froslass = 104
Munkidori = 112

# Sets
OUR_POKEMON = {Raging_Bolt_ex, Raging_Bolt_nonex, Teal_Mask_Ogerpon_ex, Fezandipiti_ex, Latias_ex}
OGERPON_IDS = {Teal_Mask_Ogerpon_ex, Teal_Mask_Ogerpon}
BOLT_IDS = {Raging_Bolt_ex, Raging_Bolt_nonex}
GRASS_ENERGY_IDS = {Basic_G_Energy}
LIGHTNING_ENERGY = Basic_L_Energy
FIGHTING_ENERGY = Basic_F_Energy
ALL_BASIC_ENERGY = {Basic_G_Energy, Basic_L_Energy, Basic_F_Energy}
SEARCH_ITEMS = {Bug_Catching_Set, Tera_Orb, Ultra_Ball, Dusk_Ball, Brocks_Scouting}
SUPPORTER_IDS = {Crispin, Boss_Orders}

pre_turn = 0
ability_used_fezandipiti = False
teal_dance_used_ids = set()


def get_card(obs, area, index, player_index):
    ps = obs.current.players[player_index]
    match area:
        case AreaType.DECK: return obs.select.deck[index]
        case AreaType.HAND: return ps.hand[index]
        case AreaType.DISCARD: return ps.discard[index]
        case AreaType.ACTIVE: return ps.active[index]
        case AreaType.BENCH: return ps.bench[index]
        case AreaType.PRIZE: return ps.prize[index]
        case AreaType.STADIUM: return obs.current.stadium[index]
        case AreaType.LOOKING: return obs.current.looking[index]
        case _: return None


def prize_count(pokemon):
    data = card_table.get(pokemon.id)
    if not data:
        return 1
    count = 3 if data.megaEx else 2 if data.ex else 1
    for card in pokemon.energyCards:
        if card.id == 12:
            count -= 1
    return max(0, count)


def count_energy_on_board(my_state):
    """Count total energy cards across all our Pokémon."""
    total = 0
    for p in my_state.active:
        if p is not None:
            total += len(p.energyCards)
    for p in my_state.bench:
        if p is not None:
            total += len(p.energyCards)
    return total


def count_grass_energy_on_board(my_state):
    total = 0
    for p in my_state.active:
        if p is not None:
            total += sum(1 for e in p.energyCards if e.id in GRASS_ENERGY_IDS)
    for p in my_state.bench:
        if p is not None:
            total += sum(1 for e in p.energyCards if e.id in GRASS_ENERGY_IDS)
    return total


def bolt_has_attack_energy(pokemon):
    """Check if a Raging Bolt ex has {L} and {F} attached (minimum to attack)."""
    has_l = any(e.id == LIGHTNING_ENERGY for e in pokemon.energyCards)
    has_f = any(e.id == FIGHTING_ENERGY for e in pokemon.energyCards)
    return has_l and has_f


def heuristic_scores(obs):
    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    global pre_turn, ability_used_fezandipiti, teal_dance_used_ids
    if pre_turn != state.turn:
        pre_turn = state.turn
        ability_used_fezandipiti = False
        teal_dance_used_ids = set()

    field_counts = defaultdict(int)
    hand_counts = defaultdict(int)
    discard_counts = defaultdict(int)

    my_field = []
    for card in my_state.active:
        if card is not None:
            field_counts[card.id] += 1
            my_field.append((0, card))
    for idx, card in enumerate(my_state.bench):
        if card is not None:
            field_counts[card.id] += 1
            my_field.append((idx + 1, card))
    for card in my_state.hand:
        hand_counts[card.id] += 1
    for card in my_state.discard:
        discard_counts[card.id] += 1

    ogerpon_on_field = field_counts[Teal_Mask_Ogerpon_ex]
    bolt_on_field = field_counts[Raging_Bolt_ex] + field_counts[Raging_Bolt_nonex]

    op_all_pokemon = [p for p in (op_state.active + op_state.bench) if p is not None]
    op_has_dragapult_line = any(p.id in (Dreepy, Drakloak, Dragapult_ex) for p in op_all_pokemon)
    op_has_grimmsnarl = any(p.id in (Impidimp_G, Morgrem_G, Grimmsnarl_ex, Munkidori, Froslass) for p in op_all_pokemon)
    op_has_iron_thorns = any(p.id == Iron_Thorns_ex for p in op_all_pokemon)
    op_has_ex = any((cd := card_table.get(p.id)) and (cd.ex or cd.megaEx) for p in op_all_pokemon)

    bench_count = len([b for b in my_state.bench if b])
    bench_max = my_state.benchMax
    bench_free = bench_max - bench_count

    active_pokemon = my_state.active[0] if my_state.active else None
    active_id = active_pokemon.id if active_pokemon else -1
    active_is_bolt_ex = active_id == Raging_Bolt_ex

    op_active = op_state.active[0] if op_state.active else None
    op_active_hp = op_active.hp if op_active else 9999

    hand_size = len(my_state.hand) if my_state.hand else my_state.handCount
    total_board_energy = count_energy_on_board(my_state)

    # Check if active bolt has {L} and {F}
    bolt_ready = False
    if active_is_bolt_ex and active_pokemon:
        bolt_ready = bolt_has_attack_energy(active_pokemon)

    hand_has_lightning = hand_counts[Basic_L_Energy] > 0
    hand_has_fighting = hand_counts[Basic_F_Energy] > 0
    hand_has_grass = hand_counts[Basic_G_Energy] > 0

    # Calculate potential Bellowing Thunder damage
    potential_discards = total_board_energy
    if bolt_ready:
        potential_discards = max(0, total_board_energy - 2)  # keep L+F minimum
    bellowing_damage = potential_discards * 70

    # Target selection
    target_idx = -1
    target_pokemon = None
    target_can_kill = False
    target_prize_gain = 0
    target_use_boss = False

    if state.turn >= 2 and op_active is not None:
        all_op = [(0, op_active)] + [(bi + 1, bp) for bi, bp in enumerate(op_state.bench) if bp]
        candidates = []
        for oi, pkmn in all_op:
            pz = prize_count(pkmn)
            e_req = max(1, -(-pkmn.hp // 70))  # ceiling division
            can_kill = bellowing_damage >= pkmn.hp
            tv = pz / e_req if e_req > 0 else 0

            # Threat multiplier for things that can KO our bolt
            if pkmn.hp > 0 and can_kill:
                tv *= 1.5

            need_boss = (oi != 0)
            has_boss = hand_counts[Boss_Orders] > 0 and not state.supporterPlayed
            has_prime = hand_counts[Prime_Catcher] > 0

            if need_boss and not has_boss and not has_prime:
                continue

            candidates.append((tv, can_kill, pz, oi, pkmn, need_boss))

        if candidates:
            candidates.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
            best = candidates[0]
            target_idx = best[3]
            target_pokemon = best[4]
            target_can_kill = best[1]
            target_prize_gain = best[2]
            target_use_boss = best[5]

    scores = []
    options = select.options if select.options else []

    for option in options:
        s = 0
        card = None
        if option.area is not None and option.area != AreaType.NONE:
            card = get_card(obs, option.area, option.index, my_index)
        cid = card.id if card else 0
        otype = option.type if option.type is not None else OptionType.NONE

        # ============================================================
        # PLAY POKEMON
        # ============================================================
        if otype == OptionType.PLAY:
            if card and card_table.get(cid, None) and card_table[cid].cardType == CardType.POKEMON:
                if bench_free <= 0:
                    s -= W["play_bench_penalty"]
                elif cid == Teal_Mask_Ogerpon_ex:
                    if ogerpon_on_field < 3:
                        s += W["play_ogerpon_early"] if state.turn <= 3 else W["play_ogerpon_late"]
                    else:
                        s += W["play_ogerpon_late"] // 2
                elif cid == Raging_Bolt_ex:
                    if bolt_on_field < 2:
                        s += W["play_raging_bolt_ex"]
                    else:
                        s += W["play_raging_bolt_ex"] // 3
                elif cid == Fezandipiti_ex:
                    s += W["play_fez"]
                elif cid == Latias_ex:
                    s += W["play_latias"]
                elif cid == Raging_Bolt_nonex:
                    if op_has_iron_thorns:
                        s += W["play_raging_bolt_nonex"] * 3
                    else:
                        s += W["play_raging_bolt_nonex"]
                else:
                    s += W["play_pokemon_base"]
            # PLAY TRAINER
            elif card:
                if cid == Bug_Catching_Set:
                    if ogerpon_on_field < 3 or bolt_on_field < 1:
                        s += W["bug_catching_set"]
                    else:
                        s += W["bug_catching_set"] // 3
                elif cid == Tera_Orb:
                    if ogerpon_on_field < 3 or bolt_on_field < 1:
                        s += W["tera_orb"]
                    else:
                        s += W["tera_orb"] // 3
                elif cid == Ultra_Ball:
                    if ogerpon_on_field < 3:
                        s += W["ultra_ball_ogerpon"]
                    elif bolt_on_field < 1:
                        s += W["ultra_ball_bolt"]
                    else:
                        s += W["ultra_ball_any"]
                elif cid == Dusk_Ball:
                    s += W["dusk_ball"]
                elif cid == Pokegear:
                    if not state.supporterPlayed:
                        s += W["pokegear"]
                    else:
                        s += W["pokegear"] // 4
                elif cid == Energy_Search:
                    if not hand_has_lightning or not hand_has_fighting:
                        s += W["energy_search_missing"]
                    else:
                        s += W["energy_search_grass"]
                elif cid == Energy_Retrieval:
                    s += W["energy_retrieval"]
                elif cid == Night_Stretcher:
                    key_in_discard = any(discard_counts[x] > 0 for x in [Raging_Bolt_ex, Teal_Mask_Ogerpon_ex, Latias_ex])
                    if key_in_discard:
                        s += W["night_stretcher_mon"]
                    else:
                        s += W["night_stretcher_energy"]
                elif cid == Brocks_Scouting:
                    s += W["brocks_scouting"]
                elif cid == Prime_Catcher:
                    if target_use_boss and target_can_kill:
                        s += W["prime_catcher"]
                    else:
                        s += W["prime_catcher"] // 2
                elif cid == Boss_Orders:
                    if not state.supporterPlayed:
                        if target_use_boss and target_can_kill:
                            s += W["boss_kill"]
                        else:
                            s += W["boss_snipe"]
                elif cid == Crispin:
                    if not state.supporterPlayed:
                        if active_is_bolt_ex and not bolt_ready:
                            active_has_l = any(e.id == LIGHTNING_ENERGY for e in active_pokemon.energyCards) if active_pokemon else False
                            active_has_f = any(e.id == FIGHTING_ENERGY for e in active_pokemon.energyCards) if active_pokemon else False
                            if not active_has_l and not active_has_f:
                                s += W["crispin_need_both"]
                            else:
                                s += W["crispin_need_one"]
                        else:
                            s += W["crispin_have_both"]

        # ============================================================
        # ATTACH (Energy / Tool)
        # ============================================================
        elif otype == OptionType.ATTACH:
            if card and cid in ALL_BASIC_ENERGY:
                target_area = option.targetArea if option.targetArea is not None else AreaType.NONE
                target_p = None
                if target_area == AreaType.ACTIVE and my_state.active:
                    target_p = my_state.active[0]
                elif target_area == AreaType.BENCH and option.targetIndex is not None:
                    if option.targetIndex < len(my_state.bench) and my_state.bench[option.targetIndex]:
                        target_p = my_state.bench[option.targetIndex]

                if target_p:
                    tid = target_p.id
                    if tid == Raging_Bolt_ex:
                        if cid == Basic_L_Energy and not any(e.id == LIGHTNING_ENERGY for e in target_p.energyCards):
                            s += W["energy_bolt_lightning"]
                        elif cid == Basic_F_Energy and not any(e.id == FIGHTING_ENERGY for e in target_p.energyCards):
                            s += W["energy_bolt_fighting"]
                        else:
                            s += W["energy_manual_any"]
                    elif tid in OGERPON_IDS:
                        if cid == Basic_G_Energy:
                            s += W["energy_ogerpon_grass"]
                        else:
                            s += W["energy_manual_any"] // 2
                    else:
                        s += W["energy_manual_any"]

        # ============================================================
        # ABILITY
        # ============================================================
        elif otype == OptionType.ABILITY:
            if card:
                cid_ability = card.id
                if cid_ability in OGERPON_IDS:
                    # Teal Dance: attach {G} from hand to this Ogerpon, draw 1
                    if hand_has_grass:
                        s += W["ability_teal_dance"]
                    else:
                        s += W["ability_teal_dance"] // 10  # can't use without grass
                elif cid_ability == Fezandipiti_ex:
                    if not ability_used_fezandipiti:
                        s += W["ability_fez_flip"]
                elif cid_ability == Latias_ex:
                    s += W["ability_latias_dynamo"]

        # ============================================================
        # ATTACK
        # ============================================================
        elif otype == OptionType.ATTACK:
            if active_is_bolt_ex and bolt_ready:
                # Bellowing Thunder
                if target_can_kill:
                    s += W["attack_bellowing_thunder"] + target_prize_gain * 5000
                else:
                    s += W["attack_bellowing_thunder"]
            elif active_id == Raging_Bolt_nonex:
                s += W["attack_dragon_headbutt"]
            elif active_id in OGERPON_IDS:
                s += W["attack_ogerpon_attack"]
            else:
                s += W["attack_default"]

        # ============================================================
        # RETREAT
        # ============================================================
        elif otype == OptionType.RETREAT:
            if active_id in OGERPON_IDS and field_counts[Raging_Bolt_ex] > 0:
                s += W["retreat_swap_attacker"]
            elif active_id not in BOLT_IDS:
                s += W["retreat_swap_attacker"] // 2
            else:
                s += W["retreat_default"]

        # ============================================================
        # SELECT (search targets, discard choices, etc.)
        # ============================================================
        elif otype == OptionType.SELECT:
            if card:
                # Search target prioritization
                if context == SelectContext.SELECT_POKEMON or context == SelectContext.SELECT_FROM_DECK:
                    if cid == Teal_Mask_Ogerpon_ex and ogerpon_on_field < 3:
                        s += 30000
                    elif cid == Raging_Bolt_ex and bolt_on_field < 1:
                        s += 25000
                    elif cid == Latias_ex and field_counts[Latias_ex] == 0:
                        s += 15000
                    elif cid == Fezandipiti_ex and field_counts[Fezandipiti_ex] == 0:
                        s += 18000
                    elif cid in ALL_BASIC_ENERGY:
                        if cid == Basic_L_Energy and not hand_has_lightning:
                            s += 22000
                        elif cid == Basic_F_Energy and not hand_has_fighting:
                            s += 20000
                        elif cid == Basic_G_Energy:
                            s += 15000
                        else:
                            s += 5000
                    elif cid in SUPPORTER_IDS:
                        if cid == Crispin and not state.supporterPlayed:
                            s += 20000
                        else:
                            s += 8000
                    else:
                        s += 1000

                # Discard selection for Bellowing Thunder
                elif context == SelectContext.SELECT_ENERGY or context == SelectContext.DISCARD_ENERGY:
                    if card.id in GRASS_ENERGY_IDS:
                        s += W["discard_grass_ogerpon"]
                    elif card.id in (LIGHTNING_ENERGY, FIGHTING_ENERGY):
                        # Only discard L/F if we have extras
                        extra_l = sum(1 for e in active_pokemon.energyCards if e.id == LIGHTNING_ENERGY) - 1 if active_pokemon else 0
                        extra_f = sum(1 for e in active_pokemon.energyCards if e.id == FIGHTING_ENERGY) - 1 if active_pokemon else 0
                        if (card.id == LIGHTNING_ENERGY and extra_l > 0) or (card.id == FIGHTING_ENERGY and extra_f > 0):
                            s += W["discard_extra_bolt"]
                        else:
                            s += W["discard_base_bolt"]
                    else:
                        s += W["discard_extra_bolt"]

                # Boss/Prime Catcher target selection
                elif context == SelectContext.SELECT_OPPONENT_POKEMON or context == SelectContext.SWITCH_OPPONENT:
                    if target_pokemon and card and card.id == target_pokemon.id:
                        s += 50000
                    else:
                        pz = prize_count(card) if card and hasattr(card, 'id') else 1
                        s += pz * 5000

        # ============================================================
        # PASS / DONE / END TURN
        # ============================================================
        elif otype == OptionType.PASS or otype == OptionType.DONE:
            s += 0  # Neutral

        scores.append(s)

    return scores


def agent(obs, config):
    global my_deck
    if isinstance(obs, dict):
        obs = to_observation_class(obs)

    state = obs.current
    select = obs.select
    my_index = state.yourIndex

    if not my_deck:
        my_deck = [c.id for c in state.players[my_index].deck]

    if select is None or select.options is None or len(select.options) == 0:
        return 0

    scores = heuristic_scores(obs)
    best_score = max(scores)
    best_indices = [i for i, s in enumerate(scores) if s == best_score]

    import random
    return random.choice(best_indices)

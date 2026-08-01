"""
main.py — Pokémon TCG heuristic agent
======================================
Works in two modes:
  • Local (kaggle_environments self-play): receives raw obs dicts, no cg.api needed.
  • Kaggle submission: if cg.api is available (Kaggle runtime), uses typed helpers.

All scoring constants are loaded from optimized_weights.json (if present).
"""

import os
import sys
import json
from collections import defaultdict

# ── Try to import cg.api (available on Kaggle, not locally) ──────────────────
_HAS_CG_API = False
try:
    from cg.api import (
        AreaType, CardType, EnergyType, Observation,
        SelectContext, OptionType, Card, Pokemon,
        all_card_data, to_observation_class,
    )
    _HAS_CG_API = True
except ModuleNotFoundError:
    pass

if not _HAS_CG_API:
    # Try the cabt-bundled path
    try:
        import kaggle_environments
        _cg_dir = os.path.join(
            os.path.dirname(kaggle_environments.__file__), "envs", "cabt"
        )
        if _cg_dir not in sys.path:
            sys.path.insert(0, _cg_dir)
        from cg.api import (
            AreaType, CardType, EnergyType, Observation,
            SelectContext, OptionType, Card, Pokemon,
            all_card_data, to_observation_class,
        )
        _HAS_CG_API = True
    except (ModuleNotFoundError, ImportError):
        pass


# ── Weights ───────────────────────────────────────────────────────────────────
_WEIGHT_DEFAULTS = {
    "W_PRIZE_MULT":             1000,
    "W_ENERGY_SCORE":            150,
    "W_TOOL_SCORE":              100,
    "W_STAGE2_SCORE":            250,
    "W_STAGE1_SCORE":            130,
    "W_ACTIVE_BONUS":            220,
    "W_TARGET_ACTIVE_BONUS":     300,
    "W_ENERGY_ACTIVE_BIAS":       10,
    "W_ENERGY_BASE":            8000,
    "W_ENERGY_NEED_BONUS":       100,
    "W_ENERGY_SURPLUS_PENALTY":   50,
    "W_EVOLVE_BASE":            9000,
    "W_TRAINER_BASE":          10000,
    "W_POKEMON_BASE":          20000,
    "W_RETREAT_SCORE":          2000,
    "W_ATTACK_SCORE":           1000,
}


def _load_weights():
    for candidate in ["optimized_weights.json",
                      "/kaggle_simulations/agent/optimized_weights.json"]:
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    data = json.load(f)
                merged = dict(_WEIGHT_DEFAULTS)
                merged.update({k: v for k, v in data.items() if k in _WEIGHT_DEFAULTS})
                return merged
            except Exception:
                pass
    return dict(_WEIGHT_DEFAULTS)


W = _load_weights()


# ── Deck ──────────────────────────────────────────────────────────────────────
def load_deck():
    _deck_path = "data/deck.csv"
    if os.path.exists("/kaggle_simulations/agent/deck.csv"):
        _deck_path = "/kaggle_simulations/agent/deck.csv"
    elif os.path.exists("deck.csv"):
        _deck_path = "deck.csv"
    with open(_deck_path) as _f:
        return [int(line) for line in _f if line.strip()]

my_deck = load_deck()


# ── Card IDs ──────────────────────────────────────────────────────────────────
# Original printings
Makuhita             = 673
Hariyama             = 674
Lunatone             = 675
Solrock              = 676
Riolu                = 677
Mega_Lucario_ex      = 678

# MEG-set alternate printings (same Pokémon, different art/set)
Makuhita_MEG         = 72    # Makuhita MEG 72
Hariyama_MEG         = 73    # Hariyama MEG 73 (future-proof)
Riolu_MEG            = 76    # Riolu MEG 76
Mega_Lucario_ex_MEG  = 77    # Mega Lucario ex MEG 77

# New Pokémon
Meowth_ex_POR        = 121   # Meowth ex POR 121

# Trainer cards
Dusk_Ball            = 1102
Switch               = 1123
Premium_Power_Pro    = 1141
Fighting_Gong        = 1142
Poke_Pad             = 1152
Hero_Cape            = 1159
Boss_Orders          = 1182
Carmine              = 1192
Lillie_Determination = 1227
Gravity_Mountain     = 1252
Basic_Fighting_Energy = 6

# Convenience sets — group MEG variants with originals for all logic
_MAKUHITA_ALL       = (Makuhita, Makuhita_MEG)
_HARIYAMA_ALL       = (Hariyama, Hariyama_MEG)
_RIOLU_ALL          = (Riolu, Riolu_MEG)
_MEGA_LUCARIO_ALL   = (Mega_Lucario_ex, Mega_Lucario_ex_MEG)


# ── Typed-API path (cg.api available — Kaggle runtime) ───────────────────────
if _HAS_CG_API:
    all_card   = all_card_data()
    card_table = {c.cardId: c for c in all_card}

    class _AttackPlan:
        attacker    = -1
        target      = -1
        attack_index = -1
        remain_hp   = -1
        energy      = False

    _plan         = _AttackPlan()
    _pre_turn     = 0
    _ability_used = False

    def _prize_count(pokemon) -> int:
        data  = card_table[pokemon.id]
        count = 3 if data.megaEx else 2 if data.ex else 1
        for card in pokemon.energyCards:
            if card.id == 12:
                count -= 1
        for card in pokemon.tools:
            if card.id == 1172 and "Lillie" in data.name:
                count -= 1
        return max(0, count)

    def _pokemon_score(pokemon) -> int:
        data  = card_table[pokemon.id]
        score = _prize_count(pokemon) * int(W["W_PRIZE_MULT"])
        score += len(pokemon.energies) * int(W["W_ENERGY_SCORE"])
        score += len(pokemon.tools)    * int(W["W_TOOL_SCORE"])
        if data.stage2:   score += int(W["W_STAGE2_SCORE"])
        elif data.stage1: score += int(W["W_STAGE1_SCORE"])
        pid = pokemon.id
        if pid in (173, 174, 190, 1071): score -= 200
        if pid == 112 and len(pokemon.energies) >= 1: score += 300
        score += pokemon.hp
        return score

    def _get_card(obs, area, index, player_index):
        ps = obs.current.players[player_index]
        match area:
            case AreaType.DECK:    return obs.select.deck[index]
            case AreaType.HAND:    return ps.hand[index]
            case AreaType.DISCARD: return ps.discard[index]
            case AreaType.ACTIVE:  return ps.active[index]
            case AreaType.BENCH:   return ps.bench[index]
            case AreaType.PRIZE:   return ps.prize[index]
            case AreaType.STADIUM: return obs.current.stadium[index]
            case AreaType.LOOKING: return obs.current.looking[index]
            case _:                return None

    def _agent_typed(obs_dict: dict) -> list[int]:
        """Full typed agent using cg.api (Kaggle runtime)."""
        obs = to_observation_class(obs_dict)
        if obs.select is None:
            return my_deck

        global _plan, _pre_turn, _ability_used
        state    = obs.current
        select   = obs.select
        context  = select.context
        my_index = state.yourIndex
        my_state = state.players[my_index]
        op_state = state.players[1 - my_index]
        my_prize = len(my_state.prize)

        if _pre_turn != state.turn:
            _pre_turn     = state.turn
            _plan         = _AttackPlan()
            _ability_used = False

        field_counts   = defaultdict(int)
        hand_counts    = defaultdict(int)
        discard_counts = defaultdict(int)
        attacker1 = attacker2 = False

        for card in my_state.active + my_state.bench:
            if card is None: continue
            field_counts[card.id] += 1
            if card.id in (Makuhita, Hariyama):
                if len(card.energies) >= 3: attacker2 = True
            elif card.id in (Riolu, Mega_Lucario_ex):
                if len(card.energies) >= 2: attacker1 = True

        for card in my_state.hand:    hand_counts[card.id]    += 1
        for card in my_state.discard: discard_counts[card.id] += 1

        stadium_id = 0
        for card in state.stadium: stadium_id = card.id

        can_attack = False
        if context == SelectContext.MAIN:
            can_switch = can_op_switch = can_use_mega_brave = False
            for o in select.option:
                if o.type == OptionType.PLAY:
                    card = _get_card(obs, AreaType.HAND, o.index, my_index)
                    if card.id == Switch: can_switch = True
                    elif card.id == Boss_Orders: can_op_switch = True
                elif o.type == OptionType.EVOLVE:
                    card = _get_card(obs, AreaType.HAND, o.index, my_index)
                    if card.id == Hariyama: can_op_switch = True
                elif o.type == OptionType.RETREAT:
                    can_switch = True
                elif o.type == OptionType.ATTACK:
                    can_attack = True
                    if o.attackId == 983: can_use_mega_brave = True

            my_cards = [my_state.active[0]] + list(my_state.bench)
            op_cards = [op_state.active[0]] + list(op_state.bench)

            if state.turn >= 2:
                best_score = -1
                for i, my_pokemon in enumerate(my_cards):
                    if i != 0 and not can_switch: break
                    for a in range(2):
                        energy_required = base_damage = base_score = 0
                        if my_pokemon.id == Mega_Lucario_ex:
                            if a == 0:
                                energy_required, base_damage = 1, 130
                                base_score += 60 * min(3, discard_counts[Basic_Fighting_Energy])
                            else:
                                energy_required, base_damage = 2, 270
                            if my_prize in (2, 3): base_score -= 500
                        elif a == 1: break
                        elif my_pokemon.id == Hariyama:
                            energy_required, base_damage = 3, 210
                        elif my_pokemon.id == Makuhita:
                            for o in select.option:
                                if o.type == OptionType.EVOLVE:
                                    idx2 = o.inPlayIndex + (1 if o.inPlayArea == AreaType.BENCH else 0)
                                    if idx2 == i: break
                            else: break
                            base_score -= 100; energy_required, base_damage = 3, 210
                        elif my_pokemon.id == Solrock:
                            if field_counts[Lunatone] >= 1:
                                energy_required, base_damage = 1, 70
                        if base_damage <= 0: continue
                        energy_count = len(my_pokemon.energies)
                        if a == 1 and i == 0 and energy_count >= 2 and not can_use_mega_brave: break
                        more_energy = False
                        if energy_count < energy_required:
                            if hand_counts[Basic_Fighting_Energy] >= 1 and not state.energyAttached:
                                energy_count += 1
                                if energy_count < energy_required: continue
                                else: more_energy = True
                            else: continue
                        for j, op_pokemon in enumerate(op_cards):
                            if j != 0 and not can_op_switch: break
                            damage = base_damage
                            data = card_table[op_pokemon.id]
                            if data.weakness == EnergyType.FIGHTING: damage *= 2
                            elif data.resistance == EnergyType.FIGHTING: damage -= 30
                            score = _pokemon_score(op_pokemon); prize = 0
                            if op_pokemon.hp <= damage: prize = _prize_count(op_pokemon)
                            else: score *= damage / op_pokemon.hp
                            score += base_score
                            if len(op_state.prize) <= prize: score = 50000
                            if i == 0: score += int(W["W_ACTIVE_BONUS"])
                            if j == 0: score += int(W["W_TARGET_ACTIVE_BONUS"])
                            score += energy_count
                            if best_score < score:
                                best_score = score
                                _plan.attacker = i; _plan.target = j
                                _plan.attack_index = a
                                _plan.remain_hp = op_pokemon.hp - damage
                                _plan.energy = more_energy

        def energy_score_typed(pokemon, active: bool) -> int:
            ec = len(pokemon.energies)
            s = int(W["W_ENERGY_BASE"]) + (int(W["W_ENERGY_ACTIVE_BIAS"]) if active else 0)
            if pokemon.id in (Makuhita, Hariyama):
                if pokemon.id == Hariyama: s += 1
                if ec < 3: s += int(W["W_ENERGY_NEED_BONUS"])
                if attacker2: s -= int(W["W_ENERGY_SURPLUS_PENALTY"])
            elif pokemon.id == Lunatone: s -= 100
            elif pokemon.id == Solrock:
                if ec < 1: s += 20
                else: s -= 100
            elif pokemon.id in (Riolu, Mega_Lucario_ex):
                if pokemon.id == Mega_Lucario_ex: s += 1
                if ec < 2: s += int(W["W_ENERGY_NEED_BONUS"])
                if attacker1: s -= int(W["W_ENERGY_SURPLUS_PENALTY"])
            return s

        scores = []
        for o in select.option:
            score = 0
            if o.type == OptionType.NUMBER: score = o.number
            elif o.type == OptionType.YES: score = 1
            elif o.type == OptionType.CARD:
                card = _get_card(obs, o.area, o.index, o.playerIndex)
                if card is not None:
                    ec = len(card.energies) if hasattr(card, 'energies') else 0
                    if context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
                        if o.playerIndex == my_index:
                            score += ec * 2
                            if o.index == _plan.attacker - 1: score += 100
                            if card.id == Mega_Lucario_ex: score += 8 if my_prize in (2,3) else 20
                            elif card.id == Hariyama and ec >= 2: score += 15
                            elif card.id == Makuhita and ec >= 2: score += 10
                            elif card.id == Solrock: score += 5
                            elif card.id == Riolu: score += 4
                        else:
                            if o.index == _plan.target - 1: score += 100
                    elif context == SelectContext.SETUP_ACTIVE_POKEMON:
                        if card.id == Solrock: score = 2 if state.firstPlayer == my_index else 4
                        elif card.id == Riolu: score = 3
                        elif card.id == Makuhita: score = 1
                    elif context == SelectContext.TO_HAND:
                        score = 200 - hand_counts[card.id] * 100
                        if card.id == Makuhita: score += 10 if field_counts[card.id] < 1 else -10
                        elif card.id == Hariyama: score += 20 if field_counts[Makuhita] >= 1 else -20
                        elif card.id == Lunatone: score += -250 if field_counts[card.id] >= 1 else 60
                        elif card.id == Solrock: score += -250 if field_counts[card.id] >= 1 else 50
                        elif card.id == Riolu:
                            t = field_counts[card.id] + field_counts[Mega_Lucario_ex]
                            score += -150 if t >= 2 else (-3 if t >= 1 else 40)
                        elif card.id == Mega_Lucario_ex: score += 40 if field_counts[Riolu] >= 1 else -15
                        elif card.id == Basic_Fighting_Energy: score += 30 if not _ability_used or not state.energyAttached else -1
                    elif context == SelectContext.ATTACH_FROM:
                        score = energy_score_typed(card, o.area == AreaType.ACTIVE)
            elif o.type == OptionType.PLAY:
                card = _get_card(obs, AreaType.HAND, o.index, my_index)
                data = card_table[card.id]
                if data.cardType == CardType.POKEMON:
                    score = int(W["W_POKEMON_BASE"])
                    if card.id in (Lunatone, Solrock): score = -1 if field_counts[card.id] >= 1 else score
                    elif card.id == Riolu:
                        if field_counts[card.id] + field_counts[Mega_Lucario_ex] >= 2: score = -1
                else:
                    score = int(W["W_TRAINER_BASE"])
                    if card.id == Switch: score = 6000 if _plan.attacker > 0 else -1
                    elif card.id == Premium_Power_Pro:
                        if state.supporterPlayed and _plan.remain_hp <= 0: score = -1
                        elif not can_attack:
                            score = 3050 if (not state.supporterPlayed and hand_counts[Carmine] > 0 and hand_counts[Lillie_Determination] == 0) else -1
                        else: score = 5000
                    elif card.id == Boss_Orders: score = 3200 if _plan.target >= 1 else -1
                    elif card.id == Carmine: score = 3000
                    elif card.id == Lillie_Determination: score = 3100
                    elif card.id == Gravity_Mountain: score = -1 if stadium_id == 0 else score
            elif o.type == OptionType.ATTACH:
                card = _get_card(obs, AreaType.HAND, o.index, my_index)
                pokemon = _get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
                if card.id == Hero_Cape:
                    score = 7000 + (100 if pokemon.id == Riolu else 200 if pokemon.id == Mega_Lucario_ex else 0)
                else:
                    score = energy_score_typed(pokemon, o.inPlayArea == AreaType.ACTIVE)
                    if o.inPlayArea == AreaType.ACTIVE:
                        if _plan.attacker == 0 and _plan.energy: score += 200
                    else:
                        if _plan.attacker == 1 + o.inPlayIndex and _plan.energy: score += 200
            elif o.type == OptionType.EVOLVE:
                pokemon = _get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
                score = int(W["W_EVOLVE_BASE"]) + len(pokemon.energies)
                if pokemon.id == Makuhita and _plan.target == 0: score = -1
            elif o.type == OptionType.ABILITY:
                card = _get_card(obs, o.area, o.index, my_index)
                score = 1 if card.id == 1267 else 30000
            elif o.type == OptionType.RETREAT:
                score = int(W["W_RETREAT_SCORE"]) if _plan.attacker >= 1 else -1
            elif o.type == OptionType.ATTACK:
                score = int(W["W_ATTACK_SCORE"])
                if _plan.attack_index == 1:
                    if o.attackId == 983: score += 100
                else:
                    if o.attackId != 983: score += 100
            scores.append(score)

        desc_indices = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]
        if context == SelectContext.MAIN:
            top_o = select.option[desc_indices[0]]
            if top_o.type == OptionType.ABILITY:
                card = _get_card(obs, top_o.area, top_o.index, my_index)
                if card.id == Lunatone: _ability_used = True
        return desc_indices[:select.maxCount]


# ── Dict-only path (local kaggle_environments, no cg.api) ────────────────────
# When running locally via env.run([agent, agent]), the cabt interpreter
# passes raw Python dicts. We parse them directly.

# String constants that match the raw cabt JSON keys
_CTX_MAIN           = "MAIN"
_CTX_SWITCH         = "SWITCH"
_CTX_TO_ACTIVE      = "TO_ACTIVE"
_CTX_SETUP_ACTIVE   = "SETUP_ACTIVE_POKEMON"
_CTX_TO_HAND        = "TO_HAND"
_CTX_ATTACH_FROM    = "ATTACH_FROM"

_OPT_NUMBER  = "NUMBER"
_OPT_YES     = "YES"
_OPT_CARD    = "CARD"
_OPT_PLAY    = "PLAY"
_OPT_ATTACH  = "ATTACH"
_OPT_EVOLVE  = "EVOLVE"
_OPT_ABILITY = "ABILITY"
_OPT_RETREAT = "RETREAT"
_OPT_ATTACK  = "ATTACK"

_AREA_ACTIVE  = "ACTIVE"
_AREA_BENCH   = "BENCH"
_AREA_HAND    = "HAND"
_AREA_DISCARD = "DISCARD"
_AREA_DECK    = "DECK"
_AREA_PRIZE   = "PRIZE"
_AREA_STADIUM = "STADIUM"
_AREA_LOOKING = "LOOKING"

_TYPE_POKEMON  = "POKEMON"
_ENERGY_FIGHTING = "FIGHTING"

# Card metadata cache (built on first use)
_card_meta_cache: dict = {}

def _get_card_meta(cid: int) -> dict:
    """Return raw card-metadata dict for a card ID via cg.game."""
    if cid in _card_meta_cache:
        return _card_meta_cache[cid]
    # We don't have a local card DB lookup — we build a minimal stub
    # from what the obs dict gives us (name, hp, etc.) rather than
    # calling all_card_data().  For weaknesses/resistance we rely on
    # the obs data attached to Pokémon in the current/opponent state.
    meta = {}
    _card_meta_cache[cid] = meta
    return meta


def _dict_get_card(obs_dict: dict, area: str, index: int, player_index: int):
    """Extract a card sub-dict from the raw observation."""
    current = obs_dict.get("current", {}) or {}
    select  = obs_dict.get("select",  {}) or {}
    players = current.get("players", [])

    if area == _AREA_DECK:
        return (select.get("deck") or [])[index] if select else None

    if player_index >= len(players):
        return None
    ps = players[player_index]

    if area == _AREA_HAND:
        lst = ps.get("hand", [])
    elif area == _AREA_DISCARD:
        lst = ps.get("discard", [])
    elif area == _AREA_ACTIVE:
        lst = ps.get("active", [])
    elif area == _AREA_BENCH:
        lst = ps.get("bench", [])
    elif area == _AREA_PRIZE:
        lst = ps.get("prize", [])
    elif area == _AREA_STADIUM:
        lst = current.get("stadium", [])
    elif area == _AREA_LOOKING:
        lst = current.get("looking", [])
    else:
        return None

    return lst[index] if 0 <= index < len(lst) else None


def _pkmn_prize_count_dict(pkmn: dict) -> int:
    cid   = pkmn.get("id", 0)
    is_ex = pkmn.get("ex", False)
    is_mega_ex = pkmn.get("megaEx", False)
    count = 3 if is_mega_ex else 2 if is_ex else 1
    for card in pkmn.get("energyCards", []):
        if card.get("id") == 12:   # Legacy Energy
            count -= 1
    for card in pkmn.get("tools", []):
        if card.get("id") == 1172 and "Lillie" in (pkmn.get("name") or ""):
            count -= 1
    return max(0, count)


def _pkmn_score_dict(pkmn: dict) -> int:
    score = _pkmn_prize_count_dict(pkmn) * int(W["W_PRIZE_MULT"])
    score += len(pkmn.get("energies", [])) * int(W["W_ENERGY_SCORE"])
    score += len(pkmn.get("tools",    [])) * int(W["W_TOOL_SCORE"])
    if pkmn.get("stage2"): score += int(W["W_STAGE2_SCORE"])
    elif pkmn.get("stage1"): score += int(W["W_STAGE1_SCORE"])
    pid = pkmn.get("id", 0)
    if pid in (173, 174, 190, 1071, Meowth_ex_POR): score -= 200
    if pid == 112 and pkmn.get("energies"): score += 300
    score += pkmn.get("hp", 0)
    return score


# Per-invocation turn state (dict path)
_dict_plan:         dict  = {}
_dict_pre_turn:     int   = 0
_dict_ability_used: bool  = False


def _reset_dict_plan():
    global _dict_plan, _dict_ability_used
    _dict_plan         = {"attacker": -1, "target": -1, "attack_index": -1,
                          "remain_hp": -1, "energy": False}
    _dict_ability_used = False


_reset_dict_plan()


def _agent_dict(obs_dict: dict) -> list[int]:
    """Pure-dict agent for local cabt self-play (no cg.api required)."""
    global _dict_pre_turn, _dict_plan, _dict_ability_used

    select_data = obs_dict.get("select")
    if select_data is None:
        return my_deck   # Deck submission on first call

    current  = obs_dict.get("current", {}) or {}
    players  = current.get("players", [])
    my_index = current.get("yourIndex", 0)
    op_index = 1 - my_index

    if my_index >= len(players) or op_index >= len(players):
        options = select_data.get("option", [])
        return list(range(select_data.get("maxCount", 1)))

    my_state = players[my_index]
    op_state = players[op_index]
    my_prize = len(my_state.get("prize", []))

    turn = current.get("turn", 0)
    if _dict_pre_turn != turn:
        _dict_pre_turn = turn
        _reset_dict_plan()

    field_counts   = defaultdict(int)
    hand_counts    = defaultdict(int)
    discard_counts = defaultdict(int)
    attacker1 = attacker2 = False

    for pkmn in (my_state.get("active") or []) + (my_state.get("bench") or []):
        if pkmn is None: continue
        pid = pkmn.get("id", 0)
        field_counts[pid] += 1
        if pid in _MAKUHITA_ALL + _HARIYAMA_ALL:
            if len(pkmn.get("energies", [])) >= 3: attacker2 = True
        elif pid in _RIOLU_ALL + _MEGA_LUCARIO_ALL:
            if len(pkmn.get("energies", [])) >= 2: attacker1 = True

    # Normalize MEG variants into original IDs so all downstream logic
    # only needs to check one constant per Pokémon species.
    field_counts[Makuhita]       += field_counts[Makuhita_MEG]
    field_counts[Hariyama]       += field_counts[Hariyama_MEG]
    field_counts[Riolu]          += field_counts[Riolu_MEG]
    field_counts[Mega_Lucario_ex]+= field_counts[Mega_Lucario_ex_MEG]

    for card in (my_state.get("hand") or []):
        hand_counts[card.get("id", 0)] += 1
    # Normalize MEG hand counts
    hand_counts[Makuhita]        += hand_counts[Makuhita_MEG]
    hand_counts[Hariyama]        += hand_counts[Hariyama_MEG]
    hand_counts[Riolu]           += hand_counts[Riolu_MEG]
    hand_counts[Mega_Lucario_ex] += hand_counts[Mega_Lucario_ex_MEG]

    for card in (my_state.get("discard") or []):
        discard_counts[card.get("id", 0)] += 1
    # Normalize MEG discard counts
    discard_counts[Makuhita]        += discard_counts[Makuhita_MEG]
    discard_counts[Riolu]           += discard_counts[Riolu_MEG]
    discard_counts[Mega_Lucario_ex] += discard_counts[Mega_Lucario_ex_MEG]

    stadium_id = 0
    for card in (current.get("stadium") or []):
        stadium_id = card.get("id", 0)

    context  = select_data.get("context", "")
    options  = select_data.get("option",  [])
    max_count = select_data.get("maxCount", 1)

    energy_attached   = current.get("energyAttached",  False)
    supporter_played  = current.get("supporterPlayed", False)
    first_player      = current.get("firstPlayer",     -1)

    my_active_list = my_state.get("active") or []
    my_bench_list  = my_state.get("bench")  or []
    op_active_list = op_state.get("active") or []
    op_bench_list  = op_state.get("bench")  or []

    my_active = my_active_list[0] if my_active_list else None
    op_active = op_active_list[0] if op_active_list else None

    can_attack       = False
    can_switch       = False
    can_op_switch    = False
    can_use_mega_brave = False

    if context == _CTX_MAIN:
        for o in options:
            ot = o.get("type", "")
            if ot == _OPT_PLAY:
                card = _dict_get_card(obs_dict, _AREA_HAND, o.get("index", 0), my_index)
                if card:
                    cid = card.get("id", 0)
                    if cid == Switch:     can_switch    = True
                    elif cid == Boss_Orders: can_op_switch = True
            elif ot == _OPT_EVOLVE:
                card = _dict_get_card(obs_dict, _AREA_HAND, o.get("index", 0), my_index)
                if card and card.get("id") in _HARIYAMA_ALL: can_op_switch = True
            elif ot == _OPT_RETREAT:
                can_switch = True
            elif ot == _OPT_ATTACK:
                can_attack = True
                if o.get("attackId") == 983: can_use_mega_brave = True

        my_cards = ([my_active] if my_active else []) + list(my_bench_list)
        op_cards = ([op_active] if op_active else []) + list(op_bench_list)

        if turn >= 2:
            best_score = -1
            for i, my_pkmn in enumerate(my_cards):
                if my_pkmn is None: continue
                if i != 0 and not can_switch: break
                for a in range(2):
                    energy_required = base_damage = base_score = 0
                    pid = my_pkmn.get("id", 0)
                    if pid in _MEGA_LUCARIO_ALL:
                        if a == 0:
                            energy_required, base_damage = 1, 130
                            base_score += 60 * min(3, discard_counts[Basic_Fighting_Energy])
                        else:
                            energy_required, base_damage = 2, 270
                        if my_prize in (2, 3): base_score -= 500
                    elif a == 1: break
                    elif pid in _HARIYAMA_ALL:
                        energy_required, base_damage = 3, 210
                    elif pid in _MAKUHITA_ALL:
                        # Check if Makuhita can evolve (skip if not)
                        for o in options:
                            if o.get("type") == _OPT_EVOLVE:
                                idx2 = o.get("inPlayIndex", 0)
                                if o.get("inPlayArea") == _AREA_BENCH: idx2 += 1
                                if idx2 == i: break
                        else: break
                        base_score -= 100; energy_required, base_damage = 3, 210
                    elif pid == Solrock:
                        if field_counts[Lunatone] >= 1:
                            energy_required, base_damage = 1, 70
                    if base_damage <= 0: continue

                    energy_count = len(my_pkmn.get("energies", []))
                    if a == 1 and i == 0 and energy_count >= 2 and not can_use_mega_brave: break

                    more_energy = False
                    if energy_count < energy_required:
                        if hand_counts[Basic_Fighting_Energy] >= 1 and not energy_attached:
                            energy_count += 1
                            if energy_count < energy_required: continue
                            more_energy = True
                        else: continue

                    for j, op_pkmn in enumerate(op_cards):
                        if op_pkmn is None: continue
                        if j != 0 and not can_op_switch: break
                        damage = base_damage
                        weakness   = op_pkmn.get("weakness",   "")
                        resistance = op_pkmn.get("resistance", "")
                        if weakness   == _ENERGY_FIGHTING: damage *= 2
                        elif resistance == _ENERGY_FIGHTING: damage -= 30
                        score = _pkmn_score_dict(op_pkmn); prize = 0
                        hp = op_pkmn.get("hp", 0)
                        if hp <= damage: prize = _pkmn_prize_count_dict(op_pkmn)
                        else: score *= damage / max(hp, 1)
                        score += base_score
                        if len(op_state.get("prize", [])) <= prize: score = 50000
                        if i == 0: score += int(W["W_ACTIVE_BONUS"])
                        if j == 0: score += int(W["W_TARGET_ACTIVE_BONUS"])
                        score += energy_count
                        if best_score < score:
                            best_score = score
                            _dict_plan["attacker"]     = i
                            _dict_plan["target"]       = j
                            _dict_plan["attack_index"] = a
                            _dict_plan["remain_hp"]    = hp - damage
                            _dict_plan["energy"]       = more_energy

    # Energy-scoring helper (dict)
    def energy_score_dict(pkmn: dict, active: bool) -> int:
        ec = len(pkmn.get("energies", []))
        s  = int(W["W_ENERGY_BASE"]) + (int(W["W_ENERGY_ACTIVE_BIAS"]) if active else 0)
        pid = pkmn.get("id", 0)
        if pid in _MAKUHITA_ALL + _HARIYAMA_ALL:
            if pid in _HARIYAMA_ALL: s += 1
            if ec < 3: s += int(W["W_ENERGY_NEED_BONUS"])
            if attacker2: s -= int(W["W_ENERGY_SURPLUS_PENALTY"])
        elif pid == Lunatone: s -= 100
        elif pid == Solrock:
            if ec < 1: s += 20
            else: s -= 100
        elif pid in _RIOLU_ALL + _MEGA_LUCARIO_ALL:
            if pid in _MEGA_LUCARIO_ALL: s += 1
            if ec < 2: s += int(W["W_ENERGY_NEED_BONUS"])
            if attacker1: s -= int(W["W_ENERGY_SURPLUS_PENALTY"])
        elif pid == Meowth_ex_POR:
            # Meowth ex: keep it energised but lower priority than main attackers
            if ec < 1: s += 10
            else: s -= 50
        return s

    scores = []
    for o in options:
        ot    = o.get("type", "")
        score = 0

        if ot == _OPT_NUMBER:
            score = o.get("number", 0)

        elif ot == _OPT_YES:
            score = 1

        elif ot == _OPT_CARD:
            area       = o.get("area", "")
            idx        = o.get("index", 0)
            pidx       = o.get("playerIndex", my_index)
            card       = _dict_get_card(obs_dict, area, idx, pidx)
            if card is not None:
                cid = card.get("id", 0)
                ec  = len(card.get("energies", []))

                if context in (_CTX_SWITCH, _CTX_TO_ACTIVE):
                    if pidx == my_index:
                        score += ec * 2
                        if idx == _dict_plan["attacker"] - 1: score += 100
                        if cid in _MEGA_LUCARIO_ALL:
                            score += 8 if my_prize in (2, 3) else 20
                        elif cid in _HARIYAMA_ALL and ec >= 2: score += 15
                        elif cid in _MAKUHITA_ALL  and ec >= 2: score += 10
                        elif cid == Solrock: score += 5
                        elif cid in _RIOLU_ALL:   score += 4
                        elif cid == Meowth_ex_POR: score += 2
                    else:
                        if idx == _dict_plan["target"] - 1: score += 100

                elif context == _CTX_SETUP_ACTIVE:
                    if cid == Solrock:             score = 2 if first_player == my_index else 4
                    elif cid in _RIOLU_ALL:        score = 3
                    elif cid in _MAKUHITA_ALL:     score = 1
                    elif cid == Meowth_ex_POR:     score = 1

                elif context == _CTX_TO_HAND:
                    score = 200 - hand_counts[cid] * 100
                    if cid in _MAKUHITA_ALL:
                        score += 10 if field_counts[Makuhita] < 1 else -10
                    elif cid in _HARIYAMA_ALL:
                        score += 20 if field_counts[Makuhita] >= 1 else -20
                    elif cid == Lunatone:
                        score += -250 if field_counts[cid] >= 1 else 60
                    elif cid == Solrock:
                        score += -250 if field_counts[cid] >= 1 else 50
                    elif cid in _RIOLU_ALL:
                        t = field_counts[Riolu] + field_counts[Mega_Lucario_ex]
                        score += -150 if t >= 2 else (-3 if t >= 1 else 40)
                    elif cid in _MEGA_LUCARIO_ALL:
                        score += 40 if field_counts[Riolu] >= 1 else -15
                    elif cid == Meowth_ex_POR:
                        score += 20 if field_counts[cid] < 1 else -30
                    elif cid == Basic_Fighting_Energy:
                        score += 30 if not _dict_ability_used or not energy_attached else -1

                elif context == _CTX_ATTACH_FROM:
                    score = energy_score_dict(card, area == _AREA_ACTIVE)

        elif ot == _OPT_PLAY:
            hand_idx = o.get("index", 0)
            card = _dict_get_card(obs_dict, _AREA_HAND, hand_idx, my_index)
            if card is not None:
                cid      = card.get("id", 0)
                is_pkmn  = card.get("cardType", "") == _TYPE_POKEMON or card.get("hp") is not None
                if is_pkmn:
                    score = int(W["W_POKEMON_BASE"])
                    if cid in (Lunatone, Solrock):
                        score = -1 if field_counts[cid] >= 1 else score
                    elif cid in _RIOLU_ALL:
                        if field_counts[Riolu] + field_counts[Mega_Lucario_ex] >= 2: score = -1
                    elif cid == Meowth_ex_POR:
                        score = -1 if field_counts[cid] >= 1 else score
                else:
                    score = int(W["W_TRAINER_BASE"])
                    if cid == Switch:
                        score = 6000 if _dict_plan["attacker"] > 0 else -1
                    elif cid == Premium_Power_Pro:
                        if supporter_played and _dict_plan["remain_hp"] <= 0: score = -1
                        elif not can_attack:
                            score = 3050 if (not supporter_played
                                             and hand_counts[Carmine] > 0
                                             and hand_counts[Lillie_Determination] == 0) else -1
                        else: score = 5000
                    elif cid == Boss_Orders:
                        score = 3200 if _dict_plan["target"] >= 1 else -1
                    elif cid == Carmine:           score = 3000
                    elif cid == Lillie_Determination: score = 3100
                    elif cid == Gravity_Mountain:
                        score = -1 if stadium_id == 0 else score

        elif ot == _OPT_ATTACH:
            hand_idx   = o.get("index", 0)
            in_area    = o.get("inPlayArea", _AREA_ACTIVE)
            in_idx     = o.get("inPlayIndex", 0)
            card       = _dict_get_card(obs_dict, _AREA_HAND, hand_idx, my_index)
            pokemon    = _dict_get_card(obs_dict, in_area, in_idx, my_index)
            if card and pokemon:
                cid = card.get("id", 0)
                if cid == Hero_Cape:
                    pid = pokemon.get("id", 0)
                    score = 7000 + (100 if pid in _RIOLU_ALL else
                                    200 if pid in _MEGA_LUCARIO_ALL else 0)
                else:
                    score = energy_score_dict(pokemon, in_area == _AREA_ACTIVE)
                    if in_area == _AREA_ACTIVE:
                        if _dict_plan["attacker"] == 0 and _dict_plan["energy"]: score += 200
                    else:
                        if _dict_plan["attacker"] == 1 + in_idx and _dict_plan["energy"]: score += 200

        elif ot == _OPT_EVOLVE:
            in_area = o.get("inPlayArea", _AREA_ACTIVE)
            in_idx  = o.get("inPlayIndex", 0)
            pokemon = _dict_get_card(obs_dict, in_area, in_idx, my_index)
            if pokemon:
                score = int(W["W_EVOLVE_BASE"]) + len(pokemon.get("energies", []))
                if pokemon.get("id") in _MAKUHITA_ALL and _dict_plan["target"] == 0: score = -1

        elif ot == _OPT_ABILITY:
            area = o.get("area", _AREA_ACTIVE)
            idx  = o.get("index", 0)
            card = _dict_get_card(obs_dict, area, idx, my_index)
            score = 1 if (card and card.get("id") == 1267) else 30000

        elif ot == _OPT_RETREAT:
            score = int(W["W_RETREAT_SCORE"]) if _dict_plan["attacker"] >= 1 else -1

        elif ot == _OPT_ATTACK:
            score = int(W["W_ATTACK_SCORE"])
            if _dict_plan["attack_index"] == 1:
                if o.get("attackId") == 983: score += 100
            else:
                if o.get("attackId") != 983: score += 100

        scores.append(score)

    desc_indices = [i for i, _ in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)]

    if context == _CTX_MAIN and desc_indices:
        top_o = options[desc_indices[0]]
        if top_o.get("type") == _OPT_ABILITY:
            area = top_o.get("area", _AREA_ACTIVE)
            idx  = top_o.get("index", 0)
            card = _dict_get_card(obs_dict, area, idx, my_index)
            if card and card.get("id") == Lunatone:
                _dict_ability_used = True

    return desc_indices[:max_count]


# ── Public entry point ────────────────────────────────────────────────────────
def agent(obs_dict: dict) -> list[int]:
    """
    Unified agent entry point.
    Uses the typed cg.api path on Kaggle; falls back to raw-dict path locally.
    """
    if _HAS_CG_API:
        return _agent_typed(obs_dict)
    return _agent_dict(obs_dict)

"""
Wall_V13 — Dragapult ex Phantom Dive Engine
=============================================
A competitive Dragapult ex deck agent that combines:
  - Optimal damage counter spread (Phantom Dive: 200 active + 60 counters on bench)
  - Intelligent evolution priority (Rare Candy fast-track to Dragapult ex)
  - Boss's Orders bench-snipe calculus for multi-prize turns
  - Crushing Hammer energy denial
  - Fezandipiti ex comeback mechanic
  - Team Rocket Watchtower stadium control
  - Full Kaggle __file__ safety for submission
"""

import os
import sys
from collections import defaultdict

# ── Kaggle-safe deck loader ──────────────────────────────────────────────────
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
    # Hardcoded fallback
    return ([119]*4 + [120]*4 + [121]*3 + [140]*1 + [184]*1 + [235]*2 +
            [1071]*1 + [1079]*2 + [1080]*1 + [1086]*4 + [1097]*2 +
            [1120]*4 + [1121]*4 + [1152]*3 + [1156]*1 + [1182]*3 +
            [1198]*4 + [1210]*2 + [1227]*4 + [1256]*2 + [2]*4 + [5]*4)

my_deck = load_deck()

# ── Card API import (safe for both local and Kaggle) ─────────────────────────
try:
    from cg.api import (AreaType, CardType, Log, LogType, Observation,
                         SelectContext, OptionType, Card, Pokemon, State,
                         all_card_data, to_observation_class)
    all_card = all_card_data()
    card_table = {c.cardId: c for c in all_card}
except Exception:
    card_table = {}

# ── Card ID Constants ────────────────────────────────────────────────────────
Dreepy              = 119   # ×4  Basic Psychic 60HP
Drakloak            = 120   # ×4  Stage 1 Psychic 90HP
Dragapult_ex        = 121   # ×3  Stage 2 Psychic 320HP - Phantom Dive: 200 + 60 counters
Fezandipiti_ex      = 140   # ×1  Basic Psychic - Comeback ability
Latias_ex           = 184   # ×1  Basic Psychic - Wall/stall
Budew               = 235   # ×2  Basic Psychic - Evolution search ability
Meowth_ex           = 1071  # ×1  Basic - Extra supporter turn
Rare_Candy          = 1079  # ×2  Skip Stage 1 evolution
Unfair_Stamp        = 1080  # ×1  Disruption after KO
Buddy_Buddy_Poffin  = 1086  # ×4  Search 2 basics with ≤70HP
Night_Stretcher     = 1097  # ×2  Recover Pokemon/Energy from discard
Crushing_Hammer     = 1120  # ×4  Remove opponent energy (coin flip)
Ultra_Ball          = 1121  # ×4  Search any Pokemon (discard 2)
Poke_Pad            = 1152  # ×3  Search Pokemon from deck
Lucky_Helmet        = 1156  # ×1  Draw 2 when damaged
Boss_Orders         = 1182  # ×3  Drag opponent bench to active
Crispin             = 1198  # ×4  Energy acceleration from deck
Brock_Scouting      = 1210  # ×2  Setup/bench search supporter
Lillie_Determination= 1227  # ×4  Draw supporter
Team_Rocket_Tower   = 1256  # ×2  Stadium: blocks opponent abilities on bench
Basic_Fire_Energy   = 2     # ×4
Basic_Psychic_Energy= 5     # ×4

PHANTOM_DIVE_ID     = 154   # Dragapult ex's main attack ID
PHANTOM_DIVE_DMG    = 200   # Base damage to active
PHANTOM_DIVE_SPREAD = 60    # Total damage counters to bench (in HP units)

UNNECESSARY = -10_000_000

# ── Immunity / Damage Reduction Tables ───────────────────────────────────────
# Pokemon that block Phantom Dive's direct damage via abilities/typing
_NO_DMG_ACTIVE = {158, 207, 330, 345}  # Crustle wall, etc.

# Pokemon that block damage counters placed by Phantom Dive
def _no_damage_counter(pokemon):
    """Check if a Pokemon is immune to damage counter placement."""
    if pokemon.id in {28, 199, 203, 207, 362, 1136}:
        return True
    for card in pokemon.energyCards:
        if card.id in {11, 20}:  # Grass/Dark energy with counter-immunity
            return True
    return False

# ── Scoring Helpers ──────────────────────────────────────────────────────────
def prize_count(pokemon, is_attack_damage=True):
    """Return prize cards taken when KO'ing this pokemon."""
    data = card_table.get(pokemon.id)
    if not data: return 1
    count = 3 if data.megaEx else 2 if data.ex else 1
    if is_attack_damage:
        # Lucky Energy reduces prizes
        for card in pokemon.energyCards:
            if card.id == 12: count -= 1
        for card in pokemon.tools:
            if card.id == 1172 and "Lillie" in data.name: count -= 1
    return max(0, count)


def pokemon_score(pokemon, is_attack_damage=True):
    """Score the value of KO'ing a pokemon (higher = more valuable target)."""
    data = card_table.get(pokemon.id)
    if not data: return 500
    score = prize_count(pokemon, is_attack_damage) * 1000
    score += len(pokemon.energies) * 150
    score += len(pokemon.tools) * 100
    if data.stage2:    score += 250
    elif data.stage1:  score += 130
    # Penalize low-value targets
    if pokemon.id in {173, 174, 190, 1071}: score -= 200
    # Bonus for threatening pokemon with energy
    if pokemon.id == 112 and len(pokemon.energies) >= 1: score += 300
    score += pokemon.hp
    return score


# ── Deck Tracking System ────────────────────────────────────────────────────
class DeckTracker:
    """Tracks what cards remain in deck vs prize vs visible zones."""

    def __init__(self):
        self.card_counts = defaultdict(int)
        self.serial_set = set()
        self.prize_cards = []

    def _add_card(self, card, my_index):
        if card is None: return
        if isinstance(card, Pokemon) or card.playerIndex == my_index:
            if card.serial not in self.serial_set:
                self.card_counts[card.id] -= 1
                self.serial_set.add(card.serial)
        if isinstance(card, Pokemon):
            for c in card.energyCards:  self._add_card(c, my_index)
            for c in card.tools:       self._add_card(c, my_index)
            for c in card.preEvolution: self._add_card(c, my_index)

    def set_counts(self, obs, my_index, select_effect=None):
        self.card_counts.clear()
        self.serial_set.clear()
        for cid in my_deck: self.card_counts[cid] += 1
        state = obs.current
        ps = state.players[my_index]
        for card in ps.hand:    self._add_card(card, my_index)
        for card in ps.discard: self._add_card(card, my_index)
        for card in ps.bench:   self._add_card(card, my_index)
        for card in ps.active:  self._add_card(card, my_index)
        for card in state.stadium: self._add_card(card, my_index)
        if state.looking is not None:
            for card in state.looking: self._add_card(card, my_index)
        if select_effect is not None:
            self._add_card(select_effect, my_index)

    def compute_prizes(self, obs, my_index):
        self.set_counts(obs, my_index)
        if obs.select.deck is not None:
            for card in obs.select.deck:
                self.card_counts[card.id] -= 1
        self.prize_cards.clear()
        for cid in self.card_counts:
            for _ in range(self.card_counts[cid]):
                self.prize_cards.append(cid)

    def get_deck_counts(self, obs, my_index, select_effect=None):
        self.set_counts(obs, my_index, select_effect)
        for cid in self.prize_cards:
            self.card_counts[cid] -= 1
        return self.card_counts

tracker = DeckTracker()


# ── Attack Planning Engine ───────────────────────────────────────────────────
class AttackPlan:
    """Represents an optimal attack target + damage counter spread."""
    __slots__ = ['target_idx', 'counter_targets', 'score']
    def __init__(self):
        self.target_idx = -1
        self.counter_targets = []
        self.score = 0


def _compute_counter_combinations(cards, total_counters=60):
    """
    Find all subsets of bench pokemon that can be KO'd by `total_counters`
    HP worth of damage counters. Uses backtracking.
    """
    combos = []
    stack = [0]
    remain = total_counters
    while stack:
        idx = stack[-1]
        if idx >= len(cards):
            stack.pop()
            if stack: remain += cards[stack[-1]].hp
            if stack: stack[-1] += 1
            continue
        hp = cards[idx].hp
        if _no_damage_counter(cards[idx]):
            stack[-1] += 1
            continue
        if remain >= hp:
            combos.append(stack.copy())
            if idx < len(cards) - 1:
                remain -= hp
                stack.append(idx + 1)
                continue
        if idx == len(cards) - 1:
            stack.pop()
            if stack: remain += cards[stack[-1]].hp
        if stack: stack[-1] += 1
    combos.append([])  # Empty combo is always an option
    return combos


def compute_attack_plan(obs, my_prizes_remaining):
    """
    Compute the best attack target (active or bench via Boss's Orders)
    and the best damage counter spread for Phantom Dive.
    Returns (plan_for_best_target, plan_for_active_only).
    """
    state = obs.current
    my_index = state.yourIndex
    op_state = state.players[1 - my_index]

    best_plan = AttackPlan()
    active_plan = AttackPlan()

    targets = list(op_state.active) + list(op_state.bench)
    if not targets: return best_plan, active_plan

    # Pre-compute counter combos for bench targets
    counter_combos = _compute_counter_combinations(targets)

    for i, pokemon in enumerate(targets):
        if pokemon is None: continue

        # Damage to active target
        active_dmg = 0 if pokemon.id in _NO_DMG_ACTIVE else PHANTOM_DIVE_DMG
        base_prizes = 0
        base_score = pokemon_score(pokemon, True)

        if pokemon.hp <= active_dmg:
            base_prizes = prize_count(pokemon, True)
        else:
            if pokemon.hp > 0:
                base_score = base_score * active_dmg / pokemon.hp

        # Win check
        if my_prizes_remaining <= base_prizes:
            plan = AttackPlan()
            plan.target_idx = i
            plan.counter_targets = []
            plan.score = 50000
            if i == 0:
                return plan, plan
            else:
                active_plan_copy = AttackPlan()
                active_plan_copy.target_idx = 0
                active_plan_copy.counter_targets = []
                active_plan_copy.score = pokemon_score(targets[0], True)
                return plan, active_plan_copy

        # Find best counter spread for this target
        best_combo = []
        max_score = base_score
        for combo in counter_combos:
            if i in combo: continue  # Don't counter the active target
            combo_prizes = base_prizes
            combo_score = base_score
            for cidx in combo:
                combo_prizes += prize_count(targets[cidx], False)
                combo_score += pokemon_score(targets[cidx], False)
            if my_prizes_remaining <= combo_prizes:
                combo_score = 50000
            else:
                # Prize efficiency bonus
                if combo_prizes >= 2:
                    if my_prizes_remaining <= 4:
                        combo_score -= 1200  # Don't overshoot
                    elif combo_prizes == 1:
                        combo_score -= 300
                    else:
                        combo_score += 1200
            if combo_score > max_score:
                max_score = combo_score
                best_combo = combo

        if max_score > best_plan.score:
            best_plan.target_idx = i
            best_plan.counter_targets = best_combo
            best_plan.score = max_score

        if i == 0:
            active_plan.target_idx = best_plan.target_idx
            active_plan.counter_targets = best_plan.counter_targets
            active_plan.score = best_plan.score

    return best_plan, active_plan


# ── Card Accessor ────────────────────────────────────────────────────────────
def get_card(obs, area, index, player_index):
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
        case _: return None


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN AGENT
# ══════════════════════════════════════════════════════════════════════════════

# Persistent state across turns
_pre_turn_log = []
_current_turn_log = []
_use_support = 0

def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global _pre_turn_log, _current_turn_log, _use_support

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    # ── Turn log tracking ────────────────────────────────────────────────
    if state.turn == 0:
        tracker.prize_cards.clear()
        _pre_turn_log.clear()
        _current_turn_log.clear()
    else:
        for log in obs.logs:
            _current_turn_log.append(log)
            if log.type == LogType.TURN_END:
                _pre_turn_log = _current_turn_log
                _current_turn_log = []

    # ── Detect opponent's last-turn events ───────────────────────────────
    pre_ko = False    # Did we lose a Pokemon last turn?
    no_item = False   # Did opponent use item-lock attack?
    for log in _pre_turn_log:
        if log.type == LogType.ATTACK:
            if log.attackId == 323: no_item = True  # Noivern item lock
        elif log.type == LogType.MOVE_CARD:
            if (log.playerIndex == my_index
                and log.fromArea in {AreaType.BENCH, AreaType.ACTIVE}
                and log.toArea == AreaType.DISCARD):
                pre_ko = True

    # ── Prize card tracking ──────────────────────────────────────────────
    if select.deck is not None:
        tracker.compute_prizes(obs, my_index)

    deck_counts = tracker.get_deck_counts(obs, my_index, select.effect)
    prize_diff = len(my_state.prize) - len(op_state.prize)

    # ── Field state analysis ─────────────────────────────────────────────
    field_counts = defaultdict(int)
    hand_counts = defaultdict(int)
    discard_counts = defaultdict(int)

    active_id = 0
    bench_attacker = False       # Benched Dragapult ex with 2+ energy
    can_evolve_dreepy = False    # Any Dreepy eligible for evolution?
    evolve_dreepy_count = 0
    can_evolve_drakloak = False  # Any Drakloak eligible for Dragapult ex?

    for card in my_state.active:
        if card is None: continue
        active_id = card.id
        field_counts[card.id] += 1
        if not card.appearThisTurn:
            if card.id == Dreepy:
                can_evolve_dreepy = True
                evolve_dreepy_count += 1
            elif card.id == Drakloak:
                can_evolve_drakloak = True

    for card in my_state.bench:
        if card is None: continue
        field_counts[card.id] += 1
        if not card.appearThisTurn:
            if card.id == Dreepy:
                can_evolve_dreepy = True
                evolve_dreepy_count += 1
            elif card.id == Drakloak:
                can_evolve_drakloak = True
        if card.id == Dragapult_ex and len(card.energies) >= 2:
            bench_attacker = True

    main_pokemon_count = field_counts[Dreepy] + field_counts[Drakloak] + field_counts[Dragapult_ex]

    # Don't need more Dragapult ex if we have enough to take remaining prizes
    no_more_dex = (field_counts[Dragapult_ex] * 2 >= len(op_state.prize))

    # ── Detect active attack capability ──────────────────────────────────
    can_switch = False
    can_attack = False
    can_main_attack = False  # Can use Phantom Dive specifically?

    for o in select.option:
        if o.type == OptionType.RETREAT:  can_switch = True
        elif o.type == OptionType.ATTACK:
            can_attack = True
            if o.attackId == PHANTOM_DIVE_ID: can_main_attack = True

    # ── Compute attack plans ─────────────────────────────────────────────
    plan_a = AttackPlan()  # Best overall (may require Boss's Orders)
    plan_b = AttackPlan()  # Best for current active target only

    if context == SelectContext.MAIN:
        if can_main_attack or (bench_attacker and can_switch):
            plan_a, plan_b = compute_attack_plan(obs, len(my_state.prize))

    # ── Stadium tracking ─────────────────────────────────────────────────
    stadium_id = 0
    for card in state.stadium: stadium_id = card.id

    # ── Discard tracking ─────────────────────────────────────────────────
    for card in my_state.discard: discard_counts[card.id] += 1

    # ── Supporter counting ───────────────────────────────────────────────
    support_count = 0

    # ══════════════════════════════════════════════════════════════════════
    #  SCORING FUNCTIONS
    # ══════════════════════════════════════════════════════════════════════

    def attach_score(attach_id, pokemon, active):
        """Score attaching a card (energy/tool) to a pokemon."""
        energy_count = len(pokemon.energies)
        ct = card_table.get(attach_id)
        if ct and ct.cardType == CardType.TOOL:
            return 60000 + (1000 if active else 0)
        # Never attach energy to Budew
        if pokemon.id == Budew: return -1
        # Special handling for non-attackers in active
        if pokemon.id in {Meowth_ex, Fezandipiti_ex, Latias_ex}:
            if active and not can_switch and not my_state.asleep and not my_state.paralyzed:
                return 22000 if (bench_attacker or field_counts[Budew] >= 1) else 18000
            return -1
        # Don't attach if active can already Phantom Dive
        if active and can_main_attack: return -1
        score = 20000
        if energy_count >= 2:
            # Already loaded — only attach if stuck in active
            if active and not can_switch and not my_state.asleep and not my_state.paralyzed:
                return score + 200
            return -1
        elif energy_count == 1:
            # Need different type energy (Fire+Psychic)
            if attach_id == pokemon.energyCards[0].id: return -1
            if pokemon.id == Dragapult_ex:   score += 250
            elif pokemon.id == Dreepy:       score -= 150
            else:                            score -= 200
            if active: score += 200
        else:
            # Zero energy — prioritize based on position
            if active:
                if bench_attacker: score += 400
            else:
                if pokemon.id == Dragapult_ex:   score += 150
                elif pokemon.id == Dreepy:       score += 100
                else:                            score += 50
                if bench_attacker: score -= 200
        # Don't invest in pre-evolutions if we don't need more Dragapult
        if no_more_dex and pokemon.id in {Dreepy, Drakloak}: score -= 500
        return score

    def hand_score(cid, ignore_count=False):
        """Score the value of having/needing a card in hand."""
        score = 0
        if cid == Dreepy:
            score = 1000 if main_pokemon_count >= 3 else 18000
        elif cid == Drakloak:
            score = 20000 if can_evolve_dreepy else 3000
        elif cid == Dragapult_ex:
            if no_more_dex:
                score = UNNECESSARY
            elif can_evolve_dreepy and hand_counts.get(Rare_Candy, 0) >= 1 and not no_item:
                score = 40000
            elif can_evolve_drakloak:
                fc = field_counts[Dragapult_ex]
                score = 30000 if fc == 0 else (10000 if fc == 1 else 50)
            else:
                score = 50 if field_counts[Dragapult_ex] >= 2 else 2000
        elif cid == Fezandipiti_ex:
            if pre_ko:            score = 50000
            elif prize_diff <= -2: score = 5
            elif len(op_state.prize) == 1: score = UNNECESSARY
        elif cid == Latias_ex:
            if active_id in {Fezandipiti_ex, Meowth_ex, Dreepy}:
                if field_counts[Drakloak] + field_counts[Dragapult_ex] == 0:
                    score = 28000
                else: score = 15000
            else: score = 10
        elif cid == Budew:
            if field_counts[Budew] + field_counts[Drakloak] + field_counts[Dragapult_ex] >= 1:
                score = UNNECESSARY
            elif state.turn >= 2:
                score = 30000
        elif cid == Meowth_ex:
            if support_count > hand_counts.get(Boss_Orders, 0) or stadium_id == Team_Rocket_Tower:
                score = 5
            elif state.supporterPlayed: score = 40
            else: score = 35000
        elif cid == Rare_Candy:
            if no_more_dex: score = UNNECESSARY
            elif can_evolve_dreepy and hand_counts.get(Dragapult_ex, 0) >= 1:
                score = 40000
        elif cid == Unfair_Stamp:
            if pre_ko:                     score = 80000
            elif len(op_state.prize) == 1: score = UNNECESSARY
            else:                          score = 80
        elif cid == Buddy_Buddy_Poffin:
            cnt = deck_counts.get(Dreepy, 0)
            if cnt == 0: score = UNNECESSARY
            else:
                if state.turn <= 2 and field_counts[Budew] == 0 and deck_counts.get(Budew, 0) >= 1:
                    cnt += 1
                if cnt >= 2: score = 35000
        elif cid == Night_Stretcher:
            for did in discard_counts:
                if discard_counts[did] >= 1:
                    ct = card_table.get(did)
                    if ct and ct.cardType in {CardType.POKEMON, CardType.BASIC_ENERGY}:
                        score = max(score, hand_score(did, ignore_count))
        elif cid == Crushing_Hammer:
            score = 20
        elif cid == Ultra_Ball:
            score = 70 if (main_pokemon_count <= 2 or field_counts[Dreepy] >= 1) else 5
        elif cid == Poke_Pad:
            score = max(hand_score(Dreepy, ignore_count), hand_score(Drakloak, ignore_count))
        elif cid == Lucky_Helmet:
            score = 15
        elif cid == Boss_Orders:
            score = 60000 if plan_a.target_idx > 0 else 1000
        elif cid == Crispin:
            if not ignore_count or support_count == 0:
                if deck_counts.get(Basic_Fire_Energy, 0) == 0 or deck_counts.get(Basic_Psychic_Energy, 0) == 0:
                    score = 10
                elif not can_main_attack and not bench_attacker and field_counts[Dragapult_ex] >= 1:
                    score = 55000
                else:
                    score = 25000
        elif cid == Brock_Scouting:
            if not ignore_count or support_count == 0:
                if state.turn == 2 and field_counts[Budew] + field_counts[Latias_ex] == 0:
                    score = 50000
                else: score = 30000
        elif cid == Lillie_Determination:
            if not ignore_count or support_count == 0:
                score = 45000
        elif cid == Team_Rocket_Tower:
            if stadium_id != 0 and stadium_id != Team_Rocket_Tower:
                score = 4000
        elif cid in {Basic_Fire_Energy, Basic_Psychic_Energy}:
            if can_main_attack and (len(op_state.prize) <= 2
                or (bench_attacker and len(op_state.prize) <= 4)):
                score = UNNECESSARY
            else:
                max_sc = -10000
                for pokemon in my_state.active:
                    if pokemon is None: continue
                    max_sc = max(max_sc, attach_score(cid, pokemon, True))
                for pokemon in my_state.bench:
                    max_sc = max(max_sc, attach_score(cid, pokemon, False))
                score = max_sc - 5000
                if can_main_attack or bench_attacker:
                    score = score / 10

        if not ignore_count and hand_counts.get(cid, 0) > 0:
            if cid == Drakloak and hand_counts[cid] < evolve_dreepy_count:
                score -= 10
            elif cid == Dreepy:
                score -= 100
            else:
                score -= 100000
        return score

    # ── Pre-compute supporter priority for this turn ─────────────────────
    if context == SelectContext.MAIN:
        _use_support = 0
        if not state.supporterPlayed:
            best_sup_score = 0
            for o in select.option:
                if o.type == OptionType.PLAY:
                    card = get_card(obs, AreaType.HAND, o.index, state.yourIndex)
                    ct = card_table.get(card.id)
                    if ct and ct.cardType == CardType.SUPPORTER:
                        sc = hand_score(card.id, True)
                        if sc > best_sup_score:
                            best_sup_score = sc
                            _use_support = card.id

    # ── Compute hand scores for discard/search decisions ─────────────────
    hand_scores_list = []
    negative_hand_count = 0
    for card in my_state.hand:
        sc = hand_score(card.id, False)
        hand_scores_list.append(sc)
        if sc < 0: negative_hand_count += 1
        hand_counts[card.id] = hand_counts.get(card.id, 0) + 1
        ct = card_table.get(card.id)
        if ct and ct.cardType == CardType.SUPPORTER and card.id != Boss_Orders:
            support_count += 1

    no_draw = (my_state.deckCount <= 8)
    do_switch = (not can_main_attack and
                 (bench_attacker or
                  (active_id != Budew and field_counts[Budew] >= 1 and state.turn >= 2)))
    effect_card_id = 0 if select.effect is None else select.effect.id
    context_card_id = 0 if select.contextCard is None else select.contextCard.id

    # ══════════════════════════════════════════════════════════════════════
    #  OPTION SCORING
    # ══════════════════════════════════════════════════════════════════════
    scores = []
    for o in select.option:
        score = 0

        # ── NUMBER ───────────────────────────────────────────────────────
        if o.type == OptionType.NUMBER:
            score = o.number

        # ── YES/NO ───────────────────────────────────────────────────────
        elif o.type == OptionType.YES:
            score = -1 if context == SelectContext.IS_FIRST else 1

        # ── CARD selection ───────────────────────────────────────────────
        elif o.type == OptionType.CARD:
            card = get_card(obs, o.area, o.index, o.playerIndex)
            if card is not None:
                energy_count = len(card.energies) if isinstance(card, Pokemon) else 0
                hp = card.hp if isinstance(card, Pokemon) else 0

                # --- Switch / Setup Active ---
                if context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE,
                               SelectContext.SETUP_ACTIVE_POKEMON}:
                    if o.playerIndex == my_index:
                        if card.id == Dreepy:         score += 10000
                        elif card.id == Drakloak:
                            score += 20000 if energy_count >= 1 else -10000
                        elif card.id == Dragapult_ex:  score += 50000
                        elif card.id == Budew:
                            if context != SelectContext.SWITCH: score += 100000
                            elif not bench_attacker:            score += 30000
                        elif card.id == Fezandipiti_ex: score -= 1000
                        elif card.id == Meowth_ex:      score -= 2000
                    else:
                        # Opponent pokemon — target best plan
                        if plan_a.target_idx == o.index + 1:
                            score += 100000
                    score += energy_count * 1000 + hp

                # --- Setup Bench ---
                elif context == SelectContext.SETUP_BENCH_POKEMON:
                    if my_index == state.firstPlayer or card.id != Dreepy:
                        score = -1

                # --- Search to Bench / Hand ---
                elif context in {SelectContext.TO_BENCH, SelectContext.TO_HAND}:
                    score = hand_score(card.id, False)
                    hand_counts[card.id] = hand_counts.get(card.id, 0) + 1
                    if effect_card_id == Crispin:
                        score = 100000 - hand_score(card.id, True)

                # --- Discard selection ---
                elif context == SelectContext.DISCARD:
                    hand_counts[card.id] = hand_counts.get(card.id, 0) - 1
                    ct = card_table.get(card.id)
                    if ct and ct.cardType == CardType.SUPPORTER:
                        support_count -= 1
                    score = -hand_score(card.id, False)

                # --- Damage counter placement ---
                elif context in {SelectContext.DAMAGE_COUNTER, SelectContext.DAMAGE_COUNTER_ANY}:
                    if hp > 0:
                        score = 100000 - 10 * hp + pokemon_score(card, False)
                        if context == SelectContext.DAMAGE_COUNTER:
                            # Phantom Dive active damage counter placement
                            if 210 <= hp <= 230:
                                score += 20000 + hp * 20
                                if o.area == AreaType.ACTIVE: score += 10000
                            elif 40 <= hp <= 90:
                                score += 10000 + hp * 20
                            elif hp <= 30:
                                score += -10000 + hp * 20
                            # High priority on troublesome Pokemon
                            if card.id in {133, 351}: score += 30000
                        else:
                            # DAMAGE_COUNTER_ANY — follow the plan
                            idx = o.index + 1
                            if idx in plan_b.counter_targets:
                                score += 100000
                            else:
                                remain_dmg = select.remainDamageCounter * 10
                                if 210 <= hp <= 200 + remain_dmg:   score += 30000
                                elif 20 <= hp <= 60 + remain_dmg:   score += 10000
                                elif hp == 10:                      score -= 100000
                            if _no_damage_counter(card): score = -1

                # --- Attach target selection ---
                elif context == SelectContext.ATTACH_FROM:
                    score = attach_score(context_card_id, card, o.area == AreaType.ACTIVE)
                    if card.id == Dragapult_ex: score += 200

        # ── ENERGY_CARD / ENERGY (opponent energy removal) ───────────────
        elif o.type in {OptionType.ENERGY_CARD, OptionType.ENERGY}:
            if o.playerIndex != state.yourIndex:
                score = 20 if o.area == AreaType.BENCH else 10
                card = get_card(obs, o.area, o.index, o.playerIndex)
                ct = card_table.get(card.id)
                if ct and ct.cardType == CardType.SPECIAL_ENERGY: score += 1

        # ── PLAY (main phase card plays) ─────────────────────────────────
        elif o.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, o.index, my_index)
            card_score = hand_scores_list[o.index]

            if card.id == Dreepy:
                score = 51000
            elif card.id == Fezandipiti_ex:
                score = 53000 if card_score > 0 else -1
            elif card.id == Latias_ex:
                score = 51000 if active_id not in {Drakloak, Dragapult_ex} else -1
            elif card.id == Budew:
                score = 52000 if (field_counts[Budew] == 0 and field_counts[Dragapult_ex] == 0) else -1
            elif card.id == Meowth_ex:
                if state.supporterPlayed or stadium_id == Team_Rocket_Tower:
                    score = -1
                elif support_count == 0:
                    score = 50000
                elif support_count == hand_counts.get(Boss_Orders, 0) and plan_a.target_idx > 0:
                    score = 50000
                else: score = -1
            elif card.id == Rare_Candy:
                score = -1 if no_more_dex else 75000
            elif card.id == Unfair_Stamp:
                score = 15000
            elif card.id == Night_Stretcher:
                score = 42000 if card_score >= 18000 else -1
            elif card.id == Crushing_Hammer:
                score = 40000
            elif card.id == Boss_Orders:
                score = 35000 if card.id == _use_support else -1
            elif card.id == Lillie_Determination:
                score = 14000 if card.id == _use_support else -1
            elif card.id == Team_Rocket_Tower:
                score = 80000 if (stadium_id > 0 or state.turn == 1) else -1
            elif no_draw:
                score = -1
            elif card.id == Buddy_Buddy_Poffin:
                score = 46000 if deck_counts.get(Dreepy, 0) > 0 else -1
            elif card.id == Ultra_Ball:
                score = 44000 if negative_hand_count >= 2 else -1
            elif card.id == Poke_Pad:
                score = 45000 if deck_counts.get(Dreepy, 0) + deck_counts.get(Drakloak, 0) > 0 else -1
            elif card.id in {Crispin, Brock_Scouting}:
                score = 35000 if card.id == _use_support else -1

        # ── ATTACH (energy/tool attachment) ──────────────────────────────
        elif o.type == OptionType.ATTACH:
            card = get_card(obs, o.area, o.index, my_index)
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score = attach_score(card.id, pokemon, o.inPlayArea == AreaType.ACTIVE)

        # ── EVOLVE ───────────────────────────────────────────────────────
        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score += len(pokemon.energies)
            if pokemon.id == Dreepy:
                score += 30000  # Evolve Dreepy -> Drakloak
            elif field_counts[Dragapult_ex] >= 2 or (field_counts[Dragapult_ex] == 1 and len(op_state.prize) <= 2):
                score = -1  # Don't need more Dragapult ex
            else:
                score += 70000  # Evolve Drakloak -> Dragapult ex (highest priority)

        # ── ABILITY ──────────────────────────────────────────────────────
        elif o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if no_draw:
                score = -1
            elif card.id == 1267:
                score = 1
            else:
                score = 40000

        # ── RETREAT ──────────────────────────────────────────────────────
        elif o.type == OptionType.RETREAT:
            score = 10000 if do_switch else -1

        # ── ATTACK ───────────────────────────────────────────────────────
        elif o.type == OptionType.ATTACK:
            score = o.attackId

        scores.append(score)

    # ── Build output (select highest-scoring options) ────────────────────
    output = []
    if scores:
        sorted_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        for i in range(min(select.maxCount, len(sorted_scores))):
            if (sorted_scores[i][1] >= 0
                or select.minCount > i
                or context not in {SelectContext.TO_BENCH, SelectContext.SETUP_BENCH_POKEMON}):
                output.append(sorted_scores[i][0])

    return output

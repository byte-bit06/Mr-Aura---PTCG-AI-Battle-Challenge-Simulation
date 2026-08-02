"""
Wall_V13 — Dragapult ex Phantom Dive Engine (Strategic Upgrade)
================================================================
A competitive Dragapult ex deck agent featuring:
  - Phantom Dive: 200 active + 60 damage counters on bench
  - Duskull → Dusclops → Dusknoir kamikaze line (Cursed Blast: 5/13 counters)
  - Munkidori Adrena-Brain: move 3 damage counters (requires Dark energy)
  - Item-first supporter sequencing
  - Dynamic defensive retreat & Drakloak preservation
  - Precision damage counter placement calculus
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
    # Hardcoded fallback (60 cards)
    return ([119]*4 + [120]*4 + [121]*3 + [131]*2 + [132]*1 + [133]*1 +
            [112]*1 + [140]*1 + [184]*1 + [235]*2 + [1071]*1 + [1079]*2 +
            [1080]*1 + [1086]*4 + [1097]*2 + [1121]*4 + [1152]*3 +
            [1182]*3 + [1198]*4 + [1210]*2 + [1227]*4 + [1256]*2 +
            [2]*4 + [5]*2 + [7]*2)

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

# ══════════════════════════════════════════════════════════════════════════════
#  CARD ID CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# --- Main Attacker Line ---
Dreepy              = 119   # ×4  Basic Psychic 60HP
Drakloak            = 120   # ×4  Stage 1 Psychic 90HP
Dragapult_ex        = 121   # ×3  Stage 2 Psychic 320HP — Phantom Dive

# --- Kamikaze Spread Line ---
Duskull             = 131   # ×2  Basic Psychic 60HP (Poffin searchable ≤70HP)
Dusclops            = 132   # ×1  Stage 1 — Cursed Blast: place 5 counters, self-KO
Dusknoir            = 133   # ×1  Stage 2 — Cursed Blast: place 13 counters, self-KO

# --- Utility Pokemon ---
Munkidori           = 112   # ×1  Basic Psychic 110HP — Adrena-Brain: move 3 counters
Fezandipiti_ex      = 140   # ×1  Basic Psychic — Comeback ability
Latias_ex           = 184   # ×1  Basic Psychic — Wall/stall
Budew               = 235   # ×2  Basic Psychic — Evolution search ability
Meowth_ex           = 1071  # ×1  Basic — Extra supporter turn

# --- Trainers ---
Rare_Candy          = 1079  # ×2  Skip Stage 1 evolution
Unfair_Stamp        = 1080  # ×1  Disruption after KO
Buddy_Buddy_Poffin  = 1086  # ×4  Search 2 basics with ≤70HP
Night_Stretcher     = 1097  # ×2  Recover Pokemon/Energy from discard
Ultra_Ball          = 1121  # ×4  Search any Pokemon (discard 2)
Poke_Pad            = 1152  # ×3  Search Pokemon from deck

# --- Supporters ---
Boss_Orders         = 1182  # ×3  Drag opponent bench to active
Crispin             = 1198  # ×4  Energy acceleration from deck
Brock_Scouting      = 1210  # ×2  Setup/bench search supporter
Lillie_Determination= 1227  # ×4  Draw supporter

# --- Stadium ---
Team_Rocket_Tower   = 1256  # ×2  Stadium: blocks opponent abilities on bench

# --- Energy ---
Basic_Fire_Energy   = 2     # ×4
Basic_Psychic_Energy= 5     # ×2
Basic_Dark_Energy   = 7     # ×2  Required for Munkidori Adrena-Brain

# --- Attack / Ability Constants ---
PHANTOM_DIVE_ID     = 154   # Dragapult ex's main attack ID
PHANTOM_DIVE_DMG    = 200   # Base damage to active
PHANTOM_DIVE_SPREAD = 60    # Total damage counters to bench (in HP units)
CURSED_BLAST_5      = 50    # Dusclops: 5 damage counters = 50 HP
CURSED_BLAST_13     = 130   # Dusknoir: 13 damage counters = 130 HP

UNNECESSARY = -10_000_000

# ── Immunity / Damage Reduction Tables ───────────────────────────────────────
_NO_DMG_ACTIVE = {158, 207, 330, 345}  # Crustle wall, etc.

def _no_damage_counter(pokemon):
    """Check if a Pokemon is immune to damage counter placement."""
    if pokemon.id in {28, 199, 203, 207, 362, 1136}:
        return True
    for card in pokemon.energyCards:
        if card.id in {11, 20}:
            return True
    return False


# ── Scoring Helpers ──────────────────────────────────────────────────────────
def prize_count(pokemon, is_attack_damage=True):
    """Return prize cards taken when KO'ing this pokemon."""
    data = card_table.get(pokemon.id)
    if not data: return 1
    count = 3 if data.megaEx else 2 if data.ex else 1
    if is_attack_damage:
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
    if pokemon.id in {173, 174, 190, 1071}: score -= 200
    if pokemon.id == 112 and len(pokemon.energies) >= 1: score += 300
    score += pokemon.hp
    return score


# ── Deck Tracking System ────────────────────────────────────────────────────
class DeckTracker:
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
    __slots__ = ['target_idx', 'counter_targets', 'score']
    def __init__(self):
        self.target_idx = -1
        self.counter_targets = []
        self.score = 0


def _compute_counter_combinations(cards, total_counters=60):
    """
    Find all subsets of opponent pokemon that can be KO'd by total_counters
    HP worth of damage counters. Uses backtracking.
    Improved: skips immune targets and prioritizes exact-KO efficiency.
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
    combos.append([])
    return combos


def compute_attack_plan(obs, my_prizes_remaining, field_counts_local=None):
    """
    Compute the best attack target + damage counter spread for Phantom Dive.
    Enhanced with:
      - Pre-evolution snipe priority (basics about to evolve)
      - Exact-KO threshold precision
      - Multi-prize turn optimization
    """
    state = obs.current
    my_index = state.yourIndex
    op_state = state.players[1 - my_index]

    best_plan = AttackPlan()
    active_plan = AttackPlan()

    targets = list(op_state.active) + list(op_state.bench)
    if not targets: return best_plan, active_plan

    counter_combos = _compute_counter_combinations(targets)

    for i, pokemon in enumerate(targets):
        if pokemon is None: continue

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

        # Find best counter spread
        best_combo = []
        max_score = base_score
        for combo in counter_combos:
            if i in combo: continue
            combo_prizes = base_prizes
            combo_score = base_score
            for cidx in combo:
                t = targets[cidx]
                if t is None: continue
                combo_prizes += prize_count(t, False)
                t_score = pokemon_score(t, False)
                # Pre-evolution snipe bonus: basics that could evolve
                data = card_table.get(t.id)
                if data and data.basic and t.hp <= 70:
                    t_score += 500  # Bonus for sniping basics before they evolve
                combo_score += t_score
            if my_prizes_remaining <= combo_prizes:
                combo_score = 50000
            else:
                if combo_prizes >= 2:
                    if my_prizes_remaining <= 4:
                        combo_score -= 1200
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
#  OPPONENT DAMAGE ESTIMATION
# ══════════════════════════════════════════════════════════════════════════════
def _estimate_opp_max_damage(op_state):
    """Estimate the maximum damage the opponent's active can deal."""
    max_dmg = 0
    for pokemon in op_state.active:
        if pokemon is None: continue
        data = card_table.get(pokemon.id)
        if not data: 
            max_dmg = max(max_dmg, 100)  # Conservative default
            continue
        for atk_id in data.attacks:
            atk_data = card_table.get(atk_id) if isinstance(atk_id, int) else atk_id
            dmg = getattr(atk_data, 'damage', 0) if atk_data else 0
            if isinstance(dmg, int):
                max_dmg = max(max_dmg, dmg)
    # Fallback: if we couldn't determine, assume moderate damage
    return max_dmg if max_dmg > 0 else 120


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN AGENT
# ══════════════════════════════════════════════════════════════════════════════

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
    pre_ko = False
    no_item = False
    for log in _pre_turn_log:
        if log.type == LogType.ATTACK:
            if log.attackId == 323: no_item = True
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
    active_hp = 0                # [NEW] Track active HP for defensive calc
    bench_attacker = False
    can_evolve_dreepy = False
    evolve_dreepy_count = 0
    can_evolve_drakloak = False
    can_evolve_duskull = False   # [NEW] Dusk line evolution tracking
    can_evolve_dusclops = False  # [NEW]
    munkidori_has_dark = False   # [NEW] Track Munkidori energy state

    for card in my_state.active:
        if card is None: continue
        active_id = card.id
        active_hp = card.hp      # [NEW]
        field_counts[card.id] += 1
        if not card.appearThisTurn:
            if card.id == Dreepy:
                can_evolve_dreepy = True
                evolve_dreepy_count += 1
            elif card.id == Drakloak:
                can_evolve_drakloak = True
            elif card.id == Duskull:
                can_evolve_duskull = True
            elif card.id == Dusclops:
                can_evolve_dusclops = True

    for card in my_state.bench:
        if card is None: continue
        field_counts[card.id] += 1
        if not card.appearThisTurn:
            if card.id == Dreepy:
                can_evolve_dreepy = True
                evolve_dreepy_count += 1
            elif card.id == Drakloak:
                can_evolve_drakloak = True
            elif card.id == Duskull:
                can_evolve_duskull = True
            elif card.id == Dusclops:
                can_evolve_dusclops = True
        if card.id == Dragapult_ex and len(card.energies) >= 2:
            bench_attacker = True
        # [NEW] Track if Munkidori has Dark energy attached
        if card.id == Munkidori:
            for e in card.energyCards:
                if e.id == Basic_Dark_Energy:
                    munkidori_has_dark = True

    main_pokemon_count = (field_counts[Dreepy] + field_counts[Drakloak] +
                          field_counts[Dragapult_ex])
    dusk_pokemon_count = (field_counts[Duskull] + field_counts[Dusclops] +
                          field_counts[Dusknoir])  # [NEW]
    no_more_dex = (field_counts[Dragapult_ex] * 2 >= len(op_state.prize))

    # ── Detect active attack capability ──────────────────────────────────
    can_switch = False
    can_attack = False
    can_main_attack = False

    for o in select.option:
        if o.type == OptionType.RETREAT:  can_switch = True
        elif o.type == OptionType.ATTACK:
            can_attack = True
            if o.attackId == PHANTOM_DIVE_ID: can_main_attack = True

    # ── Compute attack plans ─────────────────────────────────────────────
    plan_a = AttackPlan()
    plan_b = AttackPlan()

    if context == SelectContext.MAIN:
        if can_main_attack or (bench_attacker and can_switch):
            plan_a, plan_b = compute_attack_plan(obs, len(my_state.prize), field_counts)

    # ── Stadium tracking ─────────────────────────────────────────────────
    stadium_id = 0
    for card in state.stadium: stadium_id = card.id

    # ── Discard tracking ─────────────────────────────────────────────────
    for card in my_state.discard: discard_counts[card.id] += 1

    # ── Supporter counting ───────────────────────────────────────────────
    support_count = 0

    # ── [NEW] Opponent damage estimation for defensive retreat ────────────
    opp_max_damage = _estimate_opp_max_damage(op_state)

    # ── [NEW] Count opponent bench energy (for dynamic Crushing Hammer eval)
    opp_total_energy = 0
    for pokemon in op_state.active:
        if pokemon: opp_total_energy += len(pokemon.energies)
    for pokemon in op_state.bench:
        if pokemon: opp_total_energy += len(pokemon.energies)

    # ══════════════════════════════════════════════════════════════════════
    #  SCORING FUNCTIONS
    # ══════════════════════════════════════════════════════════════════════

    def attach_score(attach_id, pokemon, active):
        """Score attaching a card (energy/tool) to a pokemon."""
        energy_count = len(pokemon.energies)
        ct = card_table.get(attach_id)
        if ct and ct.cardType == CardType.TOOL:
            return 60000 + (1000 if active else 0)

        # [NEW] Never attach energy to Dusk line (they self-KO via ability)
        if pokemon.id in {Duskull, Dusclops, Dusknoir}:
            return -1

        # Never attach energy to Budew
        if pokemon.id == Budew: return -1

        # [NEW] Munkidori: only attach Dark energy to enable Adrena-Brain
        if pokemon.id == Munkidori:
            if attach_id == Basic_Dark_Energy and energy_count == 0:
                return 22000  # High priority to enable ability
            return -1  # Don't attach other energy types

        # Non-attackers in active: attach to enable retreat cost
        if pokemon.id in {Meowth_ex, Fezandipiti_ex, Latias_ex}:
            if active and not can_switch and not my_state.asleep and not my_state.paralyzed:
                return 22000 if (bench_attacker or field_counts[Budew] >= 1) else 18000
            return -1

        # Don't attach if active can already Phantom Dive
        if active and can_main_attack: return -1

        score = 20000
        if energy_count >= 2:
            if active and not can_switch and not my_state.asleep and not my_state.paralyzed:
                return score + 200
            return -1
        elif energy_count == 1:
            # Need different type (Fire+Psychic for Dragapult)
            if attach_id == pokemon.energyCards[0].id: return -1
            if pokemon.id == Dragapult_ex:   score += 250
            elif pokemon.id == Dreepy:       score -= 150
            else:                            score -= 200
            if active: score += 200
        else:
            if active:
                if bench_attacker: score += 400
            else:
                if pokemon.id == Dragapult_ex:   score += 150
                elif pokemon.id == Dreepy:       score += 100
                else:                            score += 50
                if bench_attacker: score -= 200
        if no_more_dex and pokemon.id in {Dreepy, Drakloak}: score -= 500
        return score

    def hand_score(cid, ignore_count=False):
        """Score the value of having/needing a card in hand."""
        score = 0

        # --- Main Attacker Line ---
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

        # --- [NEW] Dusk Kamikaze Line ---
        elif cid == Duskull:
            if dusk_pokemon_count >= 2:
                score = 800  # Already have enough Dusk pieces
            elif main_pokemon_count < 2:
                score = 5000  # Prioritize main line first
            else:
                score = 15000  # Good time to set up Dusk line
        elif cid == Dusclops:
            score = 22000 if can_evolve_duskull else 2000
        elif cid == Dusknoir:
            if can_evolve_dusclops:
                score = 35000  # High priority: enables 130 dmg kamikaze
            elif can_evolve_duskull and hand_counts.get(Rare_Candy, 0) >= 1:
                score = 38000  # Rare Candy fast-track
            else:
                score = 1500

        # --- [NEW] Munkidori ---
        elif cid == Munkidori:
            # Score based on whether there are damaged opponent bench targets
            opp_damaged = sum(1 for p in op_state.bench if p and p.hp < 100)
            if opp_damaged > 0 and field_counts[Munkidori] == 0:
                score = 25000
            elif field_counts[Munkidori] == 0:
                score = 12000  # Decent bench utility even without targets
            else:
                score = UNNECESSARY  # Already have one in play

        # --- Other Pokemon ---
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

        # --- Trainers ---
        elif cid == Rare_Candy:
            if no_more_dex and field_counts[Dusknoir] >= 1:
                score = UNNECESSARY
            elif can_evolve_dreepy and hand_counts.get(Dragapult_ex, 0) >= 1:
                score = 40000
            elif can_evolve_duskull and hand_counts.get(Dusknoir, 0) >= 1:
                score = 38000  # [NEW] Rare Candy also works for Dusk line
        elif cid == Unfair_Stamp:
            if pre_ko:                     score = 80000
            elif len(op_state.prize) == 1: score = UNNECESSARY
            else:                          score = 80
        elif cid == Buddy_Buddy_Poffin:
            cnt = deck_counts.get(Dreepy, 0) + deck_counts.get(Duskull, 0)  # [NEW] Also searches Duskull
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
        elif cid == Ultra_Ball:
            if main_pokemon_count <= 2 or field_counts[Dreepy] >= 1:
                score = 70
            else:
                score = 5
        elif cid == Poke_Pad:
            score = max(hand_score(Dreepy, ignore_count),
                       hand_score(Drakloak, ignore_count),
                       hand_score(Duskull, ignore_count))  # [NEW] Also considers Duskull

        # --- Supporters ---
        elif cid == Boss_Orders:
            score = 60000 if plan_a.target_idx > 0 else 1000
        elif cid == Crispin:
            if not ignore_count or support_count == 0:
                # [NEW] Also check Dark energy availability
                fire_avail = deck_counts.get(Basic_Fire_Energy, 0)
                psychic_avail = deck_counts.get(Basic_Psychic_Energy, 0)
                dark_avail = deck_counts.get(Basic_Dark_Energy, 0)
                if fire_avail == 0 and psychic_avail == 0 and dark_avail == 0:
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

        # --- Stadium ---
        elif cid == Team_Rocket_Tower:
            if stadium_id != 0 and stadium_id != Team_Rocket_Tower:
                score = 4000

        # --- Energy ---
        elif cid in {Basic_Fire_Energy, Basic_Psychic_Energy, Basic_Dark_Energy}:
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

        # Duplicate-in-hand penalty
        if not ignore_count and hand_counts.get(cid, 0) > 0:
            if cid == Drakloak and hand_counts[cid] < evolve_dreepy_count:
                score -= 10
            elif cid == Dreepy:
                score -= 100
            elif cid == Duskull:
                score -= 100  # [NEW] Similar to Dreepy
            else:
                score -= 100000
        return score

    # ══════════════════════════════════════════════════════════════════════
    #  PRE-COMPUTE PHASE
    # ══════════════════════════════════════════════════════════════════════

    # ── Pre-compute supporter priority ───────────────────────────────────
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

    # ── Compute hand scores ──────────────────────────────────────────────
    hand_scores_list = []
    negative_hand_count = 0
    # [NEW] Track if there are playable items in hand for sequencing
    has_playable_items = False
    for card in my_state.hand:
        sc = hand_score(card.id, False)
        hand_scores_list.append(sc)
        if sc < 0: negative_hand_count += 1
        hand_counts[card.id] = hand_counts.get(card.id, 0) + 1
        ct = card_table.get(card.id)
        if ct and ct.cardType == CardType.SUPPORTER and card.id != Boss_Orders:
            support_count += 1
        # [NEW] Check if we have useful items to play
        if ct and ct.cardType == CardType.ITEM and sc > 0:
            has_playable_items = True

    no_draw = (my_state.deckCount <= 8)

    # [NEW] Dynamic defensive retreat logic
    active_in_danger = (active_hp > 0 and active_hp <= opp_max_damage and
                        active_id not in {Dragapult_ex, Dusknoir, Dusclops})
    do_switch = (not can_main_attack and
                 (bench_attacker or
                  (active_id != Budew and field_counts[Budew] >= 1 and state.turn >= 2) or
                  active_in_danger))  # [NEW] Retreat if in danger

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
                        # [NEW] Dusk line: low switch priority
                        elif card.id == Duskull:         score += 5000
                        elif card.id == Dusclops:        score += 8000
                        elif card.id == Dusknoir:        score -= 500  # Don't put kamikaze in active
                        elif card.id == Munkidori:       score += 7000
                    else:
                        if plan_a.target_idx == o.index + 1:
                            score += 100000
                    score += energy_count * 1000 + hp

                # --- Setup Bench ---
                elif context == SelectContext.SETUP_BENCH_POKEMON:
                    if my_index == state.firstPlayer or card.id not in {Dreepy, Duskull}:
                        score = -1
                    elif card.id == Duskull:
                        score = 5000  # [NEW] Duskull is also good bench setup

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

                # --- Damage counter placement (PRECISION CALCULUS) ---
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
                            # [NEW] Exact-KO bonus: target with HP exactly in counter range
                            if hp <= 10:
                                score += 25000  # One counter finishes it
                            if card.id in {133, 351}: score += 30000
                        else:
                            # DAMAGE_COUNTER_ANY — follow the plan
                            idx = o.index + 1
                            if idx in plan_b.counter_targets:
                                score += 100000
                            else:
                                remain_dmg = select.remainDamageCounter * 10
                                # [NEW] Exact-KO threshold precision
                                if hp <= remain_dmg:
                                    # Can KO this target with remaining counters
                                    score += 40000 + pokemon_score(card, False)
                                elif 210 <= hp <= 200 + remain_dmg:
                                    score += 30000
                                elif 20 <= hp <= 60 + remain_dmg:
                                    score += 10000
                                elif hp == 10:
                                    score -= 100000
                                # [NEW] Pre-evolution snipe: basics about to evolve
                                data = card_table.get(card.id)
                                if data and data.basic and hp <= remain_dmg:
                                    score += 5000  # Finish off before it evolves
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

            # --- Pokemon plays ---
            if card.id == Dreepy:
                score = 51000
            elif card.id == Duskull:
                score = 48000  # [NEW] Slightly below Dreepy priority
            elif card.id == Munkidori:
                score = 47000 if field_counts[Munkidori] == 0 else -1  # [NEW]
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

            # --- Item plays (high priority, before supporters) ---
            elif card.id == Rare_Candy:
                score = -1 if (no_more_dex and field_counts[Dusknoir] >= 1) else 75000
            elif card.id == Unfair_Stamp:
                score = 15000
            elif card.id == Night_Stretcher:
                score = 42000 if card_score >= 18000 else -1
            elif card.id == Team_Rocket_Tower:
                score = 80000 if (stadium_id > 0 or state.turn == 1) else -1
            elif no_draw:
                score = -1
            elif card.id == Buddy_Buddy_Poffin:
                poffin_targets = deck_counts.get(Dreepy, 0) + deck_counts.get(Duskull, 0)  # [NEW]
                score = 46000 if poffin_targets > 0 else -1
            elif card.id == Ultra_Ball:
                score = 44000 if negative_hand_count >= 2 else -1
            elif card.id == Poke_Pad:
                poke_targets = (deck_counts.get(Dreepy, 0) + deck_counts.get(Drakloak, 0) +
                               deck_counts.get(Duskull, 0) + deck_counts.get(Dusclops, 0))  # [NEW]
                score = 45000 if poke_targets > 0 else -1

            # --- Supporter plays ---
            elif card.id == Boss_Orders:
                if card.id == _use_support:
                    score = 35000
                    # [NEW §3] Item-first sequencing: penalize if items remain
                    if has_playable_items: score -= 20000
                else:
                    score = -1
            elif card.id == Lillie_Determination:
                if card.id == _use_support:
                    score = 14000
                    # [NEW §3] Item-first sequencing penalty
                    if has_playable_items: score -= 20000
                else:
                    score = -1
            elif card.id in {Crispin, Brock_Scouting}:
                if card.id == _use_support:
                    score = 35000
                    # [NEW §3] Item-first sequencing penalty
                    if has_playable_items: score -= 20000
                else:
                    score = -1

        # ── ATTACH (energy/tool attachment) ──────────────────────────────
        elif o.type == OptionType.ATTACH:
            card = get_card(obs, o.area, o.index, my_index)
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score = attach_score(card.id, pokemon, o.inPlayArea == AreaType.ACTIVE)

        # ── EVOLVE ───────────────────────────────────────────────────────
        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score += len(pokemon.energies)

            # --- Main Attacker Evolution ---
            if pokemon.id == Dreepy:
                score += 30000  # Dreepy -> Drakloak
            elif pokemon.id == Drakloak:
                if field_counts[Dragapult_ex] >= 2 or (field_counts[Dragapult_ex] == 1 and len(op_state.prize) <= 2):
                    score = -1
                else:
                    # [NEW §4] Drakloak preservation: penalize evolving the last Drakloak
                    if field_counts[Drakloak] <= 1 and field_counts[Dragapult_ex] >= 1:
                        score += 55000  # Still evolve, but reduced priority
                    else:
                        score += 70000  # Full priority if we have spares

            # --- [NEW] Dusk Line Evolution ---
            elif pokemon.id == Duskull:
                score += 35000  # Duskull -> Dusclops
            elif pokemon.id == Dusclops:
                score += 65000  # Dusclops -> Dusknoir (high priority)

        # ── ABILITY ──────────────────────────────────────────────────────
        elif o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if no_draw:
                score = -1
            elif card.id == 1267:
                score = 1
            # [NEW] Dusclops Cursed Blast: 5 damage counters, self-KO
            elif card.id == Dusclops:
                # Evaluate if 50 damage to any opponent pokemon creates a KO
                best_blast = 0
                for opp_p in list(op_state.active) + list(op_state.bench):
                    if opp_p is None or _no_damage_counter(opp_p): continue
                    if opp_p.hp <= CURSED_BLAST_5:
                        ko_value = pokemon_score(opp_p, False) + prize_count(opp_p, False) * 5000
                        best_blast = max(best_blast, ko_value)
                    else:
                        # Softening a target for Phantom Dive follow-up
                        best_blast = max(best_blast, 2000)
                if best_blast > 0:
                    score = 85000 + best_blast  # Very high priority if KO possible
                else:
                    score = -1  # No good targets

            # [NEW] Dusknoir Cursed Blast: 13 damage counters, self-KO
            elif card.id == Dusknoir:
                best_blast = 0
                for opp_p in list(op_state.active) + list(op_state.bench):
                    if opp_p is None or _no_damage_counter(opp_p): continue
                    if opp_p.hp <= CURSED_BLAST_13:
                        ko_value = pokemon_score(opp_p, False) + prize_count(opp_p, False) * 8000
                        best_blast = max(best_blast, ko_value)
                    else:
                        # Soften for Phantom Dive
                        best_blast = max(best_blast, 5000)
                if best_blast > 0:
                    score = 90000 + best_blast  # Highest ability priority
                else:
                    score = 5000  # Even without KO, 130 damage is huge

            # [NEW] Munkidori Adrena-Brain: move 3 damage counters
            elif card.id == Munkidori:
                if munkidori_has_dark:
                    # Check if moving 3 counters (30 dmg) creates a KO
                    best_move = 0
                    for opp_p in list(op_state.active) + list(op_state.bench):
                        if opp_p is None or _no_damage_counter(opp_p): continue
                        if opp_p.hp <= 30:
                            ko_value = pokemon_score(opp_p, False) + prize_count(opp_p, False) * 3000
                            best_move = max(best_move, ko_value)
                        elif opp_p.hp <= 60:
                            best_move = max(best_move, 1500)  # Softening
                    score = 45000 + best_move if best_move > 0 else 20000
                else:
                    score = -1  # No Dark energy, can't use

            else:
                score = 40000

        # ── RETREAT ──────────────────────────────────────────────────────
        elif o.type == OptionType.RETREAT:
            if do_switch:
                # [NEW §4] Boost retreat score when active is in lethal danger
                if active_in_danger and bench_attacker:
                    score = 25000  # High priority defensive retreat
                else:
                    score = 10000
            else:
                score = -1

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

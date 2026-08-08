"""
dragapult_heuristics.py — position evaluation for the Dragapult ex / Dusknoir deck.

Provides the read-only `View` over a turn's `State`, the `Heuristics` service
that builds views and scores positions, and the static tables (`HAND_VALUE`,
`LIABILITY_2_PRIZE`, `SEARCH_ITEMS`) that `main.py` and `dragapult_decisions`
consult. Card/attack IDs below were pulled from the live card data (cg.api
all_card_data / all_attack), not guessed.
"""

import json
import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Card ID namespace (verified against cg.api.all_card_data / all_attack)
# ---------------------------------------------------------------------------

class ID:
    DREEPY = 119
    DRAKLOAK = 120
    DRAGAPULT_EX = 121
    DUSKULL = 131
    DUSCLOPS = 132
    DUSKNOIR = 133
    MUNKIDORI = 112
    BUDEW = 235
    MEOWTH_EX = 1071
    LATIAS_EX = 184
    FEZANDIPITI_EX = 140
    BLOODMOON_URSALUNA_EX = 44

    BUDDY_BUDDY_POFFIN = 1086
    LILLIES_DETERMINATION = 1227
    POKEGEAR_3 = 1122
    POKE_PAD = 1152
    RARE_CANDY = 1079
    BOSSES_ORDERS = 1182
    NIGHT_STRETCHER = 1097
    ULTRA_BALL = 1121
    ENERGY_SEARCH = 1119
    CRUSHING_HAMMER = 1120
    HILDA = 1225

    BASIC_FIRE_ENERGY = 2
    BASIC_PSYCHIC_ENERGY = 5
    SPECIAL_DARKNESS_ENERGY = 7      # single copy; feeds Munkidori's Adrena-Brain
    NEO_UPPER_ENERGY = 10


# Attack IDs (cg.api.Option.attackId), not card IDs.
PHANTOM_DIVE_ATTACK = 154     # Dragapult ex — 200 dmg + 6 bench counters, costs Fire+Psychic
JET_HEADBUTT_ATTACK = 153     # Dragapult ex — 70 dmg, costs 1 colorless
ITCHY_POLLEN_ATTACK = 323     # Budew — 10 dmg, FREE (no energy cost), item-locks opponent
BLOOD_MOON_ATTACK = 41        # Bloodmoon Ursaluna ex — 240 dmg, 5 colorless (reduced by prizes taken)

PHANTOM_DIVE_SPREAD = 60      # HP worth of bench damage counters Phantom Dive grants

# 2-prize (ex) Basic Pokemon in this deck. Never lead with these; never
# overbench them (rule 4 / rule 9).
LIABILITY_2_PRIZE = {
    ID.BLOODMOON_URSALUNA_EX,
    ID.FEZANDIPITI_EX,
    ID.LATIAS_EX,
    ID.MEOWTH_EX,
}

# Item cards that dig for the Dreepy line / basics. Always worth playing early.
SEARCH_ITEMS = {
    ID.BUDDY_BUDDY_POFFIN,
    ID.POKE_PAD,
    ID.ULTRA_BALL,
}

# ---------------------------------------------------------------------------
# Tunable weights — every scoring constant this deck's policy uses lives here,
# named, so a genetic/bayesian optimizer (see train_genetic_dragapult.py) can
# mutate them the same way the other decks in this repo already do (root
# main.py's `W` dict is the precedent this mirrors). Nothing about *what*
# cid maps to *which* named weight is tunable — only the numeric values are.
# ---------------------------------------------------------------------------

_WEIGHT_DEFAULTS = {
    # HAND_VALUE: static "how much do we want to be holding this card" prior,
    # 0..1. Used as the discard-priority fallback (1 - value = discard-first
    # score) when dragapult_decisions.discard_priority has no sharper answer.
    "hand_value_dreepy": 0.55,
    "hand_value_drakloak": 0.70,
    "hand_value_dragapult_ex": 0.85,
    "hand_value_duskull": 0.35,
    "hand_value_dusclops": 0.55,
    "hand_value_dusknoir": 0.80,
    "hand_value_munkidori": 0.45,
    "hand_value_budew": 0.60,
    "hand_value_meowth_ex": 0.35,
    "hand_value_latias_ex": 0.55,
    "hand_value_fezandipiti_ex": 0.45,
    "hand_value_bloodmoon_ursaluna_ex": 0.30,
    "hand_value_buddy_buddy_poffin": 0.55,
    "hand_value_lillies_determination": 0.90,
    "hand_value_pokegear_3": 0.45,
    "hand_value_poke_pad": 0.50,
    "hand_value_rare_candy": 0.65,
    "hand_value_bosses_orders": 0.60,
    "hand_value_night_stretcher": 0.50,
    "hand_value_ultra_ball": 0.55,
    "hand_value_energy_search": 0.25,
    "hand_value_crushing_hammer": 0.20,
    "hand_value_hilda": 0.40,
    "hand_value_basic_fire_energy": 0.45,
    "hand_value_basic_psychic_energy": 0.45,
    "hand_value_special_darkness_energy": 0.35,
    "hand_value_neo_upper_energy": 0.30,

    # Heuristics.evaluate(): how hard a logged violation docks the search's
    # leaf score (bug-4 fix — this is what keeps search aligned with policy).
    "violation_penalty": 0.15,

    # rank_targets / _make_target threat + efficiency formula coefficients.
    "threat_prize_mult": 0.15,
    "threat_energy_cap": 0.4,
    "threat_energy_mult": 0.08,
    "threat_active_bonus": 0.2,
    "threat_hp_cap": 0.25,
    "threat_hp_div": 1000.0,
    "efficiency_hp_div": 300.0,

    # should_cursed_blast (rule 5 prize math).
    "cursedblast_win": 1.0,
    "cursedblast_buy_two": 0.9,
    "cursedblast_hold": 0.25,
    "cursedblast_no_target": 0.15,

    # should_bench (rules 4 / 8 / 9 / D).
    "bench_last_slot_deny": 0.1,
    "bench_liability_existing_deny": 0.05,
    "bench_liability_latias_rescue": 0.95,
    "bench_liability_default": 0.5,
    "bench_duskull_early": 0.7,
    "bench_duskull_late_deny": 0.1,
    "bench_dreepy": 0.95,
    "bench_munkidori": 0.55,
    "bench_budew_dup_deny": 0.1,
    "bench_budew": 0.8,
    "bench_default": 0.5,

    # energy_attach_target ranking.
    "attach_budew": 0.0,
    "attach_utility_active_empty": 0.5,
    "attach_utility_bench": 0.05,
    "attach_dragapult_loaded": 0.1,
    "attach_dragapult_one_energy": 0.95,
    "attach_dragapult_active_empty": 0.8,
    "attach_dragapult_bench_empty": 0.7,
    "attach_dusknoir": 0.6,
    "attach_pre_evo_empty": 0.4,
    "attach_pre_evo_has_energy": 0.15,
    "attach_munkidori_empty": 0.55,
    "attach_munkidori_has_energy": 0.1,
    "attach_generic": 0.3,

    # lillie_or_search / recon_directive_timing / choose_first_or_second.
    "lillie_six_prizes": 1.0,
    "lillie_thin_hand": 0.9,
    "lillie_building": 0.75,
    "lillie_default": 0.6,
    "recon_directive": 0.9,
    "go_first": 0.95,

    # should_mulligan_keep.
    "mulligan_keep_basic": 0.8,
    "mulligan_keep_searcher": 0.55,
    "mulligan_redraw": 0.2,

    # discard_priority (rule A).
    "discard_guard_factor": 0.2,

    # switch_target_score (rules B / C).
    "switch_budew_ready": 0.5,
    "switch_budew_not_ready": 0.95,
    "switch_dragapult_charged": 0.9,
    "switch_dusknoir": 0.85,
    "switch_pre_evo_energy": 0.6,
    "switch_pre_evo_empty": 0.4,
    "switch_liability": 0.05,
    "switch_default": 0.3,

    # retreat_score (rules B / C).
    "retreat_ursaluna_free": 0.95,
    "retreat_ursaluna_paid": 0.6,
    "retreat_budew_attacker_waiting": 0.85,
    "retreat_budew_holding": 0.15,
    "retreat_dragapult_ready": 0.05,
    "retreat_attacker_waiting": 0.75,
    "retreat_default": 0.2,

    # search_target_score (rule D).
    "search_hit_dreepy": 0.95,
    "search_hit_budew": 0.85,
    "search_hit_drakloak": 0.7,
    "search_hit_duskull_early": 0.55,
    "search_hit_liability": 0.2,
    "search_hit_default": 0.4,

    # -----------------------------------------------------------------
    # main.py policy_rank and its _score_* helpers.
    # -----------------------------------------------------------------
    "policy_is_first_yes": 0.95,
    "policy_is_first_no": 0.05,
    "policy_mulligan_match": 0.9,
    "policy_mulligan_mismatch": 0.1,
    "policy_setup_budew": 0.90,
    "policy_setup_dreepy": 0.85,
    "policy_setup_duskull": 0.60,
    "policy_setup_liability": 0.15,
    "policy_setup_default": 0.50,
    "policy_evolve": 0.88,
    "policy_attack_ready": 0.80,
    "policy_attack_not_ready": 0.55,
    "policy_end": 0.05,
    "policy_yes": 0.55,
    "policy_no": 0.45,
    "policy_default": 0.40,
    "policy_exception_fallback": 0.30,

    "ability_dusclops_go": 0.92,
    "ability_dusclops_hold": 0.02,
    "ability_dusknoir_go": 0.94,
    "ability_dusknoir_hold": 0.02,
    "ability_drakloak_recon": 0.90,
    "ability_munkidori_online": 0.75,
    "ability_munkidori_offline": 0.10,
    "ability_fezandipiti": 0.70,
    "ability_default": 0.65,

    "attach_no_target": 0.60,
    "attach_no_match": 0.55,
    "attach_blend_base": 0.45,
    "attach_blend_mult": 0.5,

    "switch_no_target": 0.30,

    "play_gate_deny": 0.05,
    "play_gate_blend_base": 0.45,
    "play_gate_blend_mult": 0.45,
    "play_lillie_go": 0.93,
    "play_lillie_hold": 0.25,
    "play_search_items": 0.86,
    "play_rare_candy_ready": 0.84,
    "play_rare_candy_not_ready": 0.20,
    "play_hilda": 0.72,
    "play_night_stretcher": 0.60,
    "play_pokegear_open": 0.55,
    "play_pokegear_redundant": 0.10,
    "play_energy_search": 0.45,
    "play_crushing_hammer": 0.35,
    "play_default": 0.55,
    "play_none": 0.50,

    "boss_bench_threat": 0.90,
    "boss_bench_two_prize": 0.78,
    "boss_default": 0.35,
    "boss_fallback": 0.55,

    "damage_own_board": 0.01,
    "damage_blend_base": 0.20,
    "damage_blend_mult": 0.75,
    "damage_default": 0.50,
}


def _load_weights():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base_dir = "/kaggle_simulations/agent"
    for candidate in [
        os.path.join(base_dir, "dragapult_weights.json"),
        "dragapult_weights.json",
        "/kaggle_simulations/agent/dragapult_weights.json",
    ]:
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

HAND_VALUE = {
    ID.DREEPY: W["hand_value_dreepy"],
    ID.DRAKLOAK: W["hand_value_drakloak"],
    ID.DRAGAPULT_EX: W["hand_value_dragapult_ex"],
    ID.DUSKULL: W["hand_value_duskull"],
    ID.DUSCLOPS: W["hand_value_dusclops"],
    ID.DUSKNOIR: W["hand_value_dusknoir"],
    ID.MUNKIDORI: W["hand_value_munkidori"],
    ID.BUDEW: W["hand_value_budew"],
    ID.MEOWTH_EX: W["hand_value_meowth_ex"],
    ID.LATIAS_EX: W["hand_value_latias_ex"],
    ID.FEZANDIPITI_EX: W["hand_value_fezandipiti_ex"],
    ID.BLOODMOON_URSALUNA_EX: W["hand_value_bloodmoon_ursaluna_ex"],
    ID.BUDDY_BUDDY_POFFIN: W["hand_value_buddy_buddy_poffin"],
    ID.LILLIES_DETERMINATION: W["hand_value_lillies_determination"],
    ID.POKEGEAR_3: W["hand_value_pokegear_3"],
    ID.POKE_PAD: W["hand_value_poke_pad"],
    ID.RARE_CANDY: W["hand_value_rare_candy"],
    ID.BOSSES_ORDERS: W["hand_value_bosses_orders"],
    ID.NIGHT_STRETCHER: W["hand_value_night_stretcher"],
    ID.ULTRA_BALL: W["hand_value_ultra_ball"],
    ID.ENERGY_SEARCH: W["hand_value_energy_search"],
    ID.CRUSHING_HAMMER: W["hand_value_crushing_hammer"],
    ID.HILDA: W["hand_value_hilda"],
    ID.BASIC_FIRE_ENERGY: W["hand_value_basic_fire_energy"],
    ID.BASIC_PSYCHIC_ENERGY: W["hand_value_basic_psychic_energy"],
    ID.SPECIAL_DARKNESS_ENERGY: W["hand_value_special_darkness_energy"],
    ID.NEO_UPPER_ENERGY: W["hand_value_neo_upper_energy"],
}

# The 60-card list this build actually ships (mirrors deck.csv exactly; kept
# here too so `load_deck()` in main.py has a real source even if deck.csv is
# missing at runtime, e.g. a bare Kaggle submission tarball).
DECK_ID_LIST = (
    [ID.DREEPY] * 4 + [ID.DRAKLOAK] * 4 + [ID.DRAGAPULT_EX] * 3
    + [ID.DUSKULL] * 2 + [ID.DUSCLOPS] * 2 + [ID.DUSKNOIR]
    + [ID.MUNKIDORI] + [ID.BUDEW] * 2 + [ID.MEOWTH_EX] + [ID.LATIAS_EX]
    + [ID.FEZANDIPITI_EX] + [ID.BLOODMOON_URSALUNA_EX]
    + [ID.BUDDY_BUDDY_POFFIN] * 4 + [ID.LILLIES_DETERMINATION] * 4 + [ID.POKEGEAR_3] * 3
    + [ID.POKE_PAD] * 3 + [ID.RARE_CANDY] * 3 + [ID.BOSSES_ORDERS] * 3
    + [ID.NIGHT_STRETCHER] * 2 + [ID.ULTRA_BALL] * 3 + [ID.ENERGY_SEARCH]
    + [ID.CRUSHING_HAMMER] + [ID.HILDA] * 2
    + [ID.BASIC_PSYCHIC_ENERGY] * 3 + [ID.SPECIAL_DARKNESS_ENERGY]
    + [ID.BASIC_FIRE_ENERGY] * 3 + [ID.NEO_UPPER_ENERGY]
)
assert len(DECK_ID_LIST) == 60, f"DECK_ID_LIST has {len(DECK_ID_LIST)} cards, expected 60"


# ---------------------------------------------------------------------------
# Card index — thin wrapper so heuristics can ask "is this an ex" etc.
# without caring whether the data came from cg.api or the CSV fallback.
# ---------------------------------------------------------------------------

class CardIndex:
    def __init__(self, by_id=None):
        self.by_id = by_id or {}

    @classmethod
    def from_card_data(cls, cards):
        return cls(by_id={c.cardId: c for c in cards})

    def get(self, cid):
        return self.by_id.get(cid)

    def is_ex(self, cid):
        c = self.by_id.get(cid)
        if c is not None:
            return bool(getattr(c, "ex", False) or getattr(c, "megaEx", False))
        return cid in LIABILITY_2_PRIZE or cid == ID.DRAGAPULT_EX

    def name(self, cid):
        c = self.by_id.get(cid)
        return getattr(c, "name", None) if c is not None else None


# ---------------------------------------------------------------------------
# View — read-only lens over a State for our seat.
# ---------------------------------------------------------------------------

class View:
    __slots__ = ("state", "my_index", "opp_index", "me", "opp", "card_index")

    def __init__(self, state, seat, card_index=None):
        self.state = state
        self.my_index = seat
        self.opp_index = 1 - seat
        self.me = state.players[seat]
        self.opp = state.players[1 - seat]
        self.card_index = card_index or CardIndex()

    # --- board access -------------------------------------------------
    @property
    def my_active(self):
        act = self.me.active or []
        return act[0] if act else None

    @property
    def opp_active(self):
        act = self.opp.active or []
        return act[0] if act else None

    @property
    def my_bench(self):
        return list(self.me.bench or [])

    @property
    def opp_bench(self):
        return list(self.opp.bench or [])

    @property
    def my_board(self):
        return ([self.my_active] if self.my_active else []) + self.my_bench

    @property
    def opp_board(self):
        return ([self.opp_active] if self.opp_active else []) + self.opp_bench

    @property
    def hand_ids(self):
        return [c.id for c in (self.me.hand or [])]

    @property
    def turn(self):
        return getattr(self.state, "turn", 0)

    @property
    def my_prizes_left(self):
        return len(self.me.prize or [])

    @property
    def opp_prizes_left(self):
        return len(self.opp.prize or [])

    # --- counting helpers (used directly by main.py's policy_rank) ----
    def count_in_play(self, ids):
        ids = set(ids)
        return sum(1 for p in self.my_board if p is not None and p.id in ids)

    def count_in_hand(self, ids):
        ids = set(ids)
        return sum(1 for cid in self.hand_ids if cid in ids)

    def count_opp_in_play(self, ids):
        ids = set(ids)
        return sum(1 for p in self.opp_board if p is not None and p.id in ids)

    def count_in_discard(self, ids):
        ids = set(ids)
        return sum(1 for c in (self.me.discard or []) if c.id in ids)

    def energy_count(self, pokemon):
        return len(getattr(pokemon, "energies", None) or [])

    def has_ability_source(self, cid):
        """True if a Pokemon with this card id is anywhere on our board."""
        return self.count_in_play([cid]) > 0


# ---------------------------------------------------------------------------
# Phase / readiness helpers
# ---------------------------------------------------------------------------

def detect_phase(view):
    """Coarse turn-count based phase label, used for logging/evaluation."""
    t = view.turn
    if t <= 2:
        return "opening"
    if t <= 6:
        return "setup"
    if view.count_in_play([ID.DRAGAPULT_EX]) or view.count_in_play([ID.DUSKNOIR]):
        return "attacking"
    return "midgame"


def phantom_dive_available(view):
    """Is our active Dragapult ex carrying enough energy to threaten Phantom Dive?"""
    p = view.my_active
    if p is None or p.id != ID.DRAGAPULT_EX:
        return False
    return view.energy_count(p) >= 2


def munkidori_online(view):
    """Adrena-Brain requires a Darkness energy attached to Munkidori."""
    for p in view.my_board:
        if p is not None and p.id == ID.MUNKIDORI:
            for c in getattr(p, "energyCards", None) or []:
                if c.id == ID.SPECIAL_DARKNESS_ENERGY:
                    return True
    return False


def detonators_ready(view):
    """Do we have a Cursed Blast source (Dusclops/Dusknoir) on the board?"""
    return view.count_in_play([ID.DUSCLOPS, ID.DUSKNOIR]) > 0


def abilities_locked(view):
    """
    True if the opponent has a live source that could be shutting our
    abilities off. We don't have full stadium/ability-lock visibility from
    State alone, so this is a conservative heuristic: assume unlocked unless
    we can positively detect a blocker (extend here as opponent decks reveal
    ability-lock tech).
    """
    return False


def plan_prizes_this_turn(view, target_prizes):
    """
    Would taking `target_prizes` more prizes this turn end the game (rule 5
    prize math: never detonate Cursed Blast while the opponent sits on their
    last prize unless it actually wins).
    """
    return view.opp_prizes_left <= target_prizes


# ---------------------------------------------------------------------------
# Heuristics service
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    key: str
    detail: str


@dataclass
class Schedule:
    adherence: float
    missed: list


class EvalResult:
    __slots__ = ("score", "phase", "features", "schedule", "violations")

    def __init__(self, score, phase, features, schedule, violations):
        self.score = score
        self.phase = phase
        self.features = features
        self.schedule = schedule
        self.violations = violations

    def top_gaps(self, n=3):
        gaps = sorted(
            ((k, 1.0 - v) for k, v in self.features.items()),
            key=lambda t: -t[1],
        )
        return gaps[:n]


class Heuristics:
    """Builds Views and scores positions. Never raises — every feature access
    is defensive so a partially-populated observation still yields a number."""

    def __init__(self, card_index=None):
        self.card_index = card_index or CardIndex()

    def view(self, state, seat=0):
        return View(state, seat, self.card_index)

    # -- 22 normalized [0,1] features describing schedule adherence ----
    def _features(self, v):
        f = {}
        f["dreepy_down_t1"] = 1.0 if (v.turn > 1 or v.count_in_play([ID.DREEPY, ID.DRAKLOAK, ID.DRAGAPULT_EX]) >= 1) else 0.0
        f["energy_curve"] = min(1.0, sum(v.energy_count(p) for p in v.my_board if p) / max(1, v.turn))
        f["bench_open_slot"] = 1.0 if len(v.my_bench) < (v.me.benchMax or 5) else 0.0
        f["main_line_count"] = min(1.0, v.count_in_play([ID.DREEPY, ID.DRAKLOAK, ID.DRAGAPULT_EX]) / 3.0)
        f["attacker_ready"] = 1.0 if phantom_dive_available(v) else 0.0
        f["budew_locking"] = 1.0 if (v.my_active is not None and v.my_active.id == ID.BUDEW) else 0.0
        f["detonator_available"] = 1.0 if detonators_ready(v) else 0.0
        f["hand_size"] = min(1.0, len(v.hand_ids) / 6.0)
        f["prize_lead"] = max(0.0, min(1.0, 0.5 + 0.1 * (v.opp_prizes_left - v.my_prizes_left)))
        f["overbench_risk"] = 1.0 - min(1.0, sum(1 for p in v.my_bench if p and p.id in LIABILITY_2_PRIZE) / 2.0)
        # A 2-prize basic sitting active is a standing risk (one KO hands the
        # opponent two prizes instead of one) at any point in the game, not
        # just the opening turns — this has to be a scored feature, not just
        # a logged violation, or the search's own leaf-evaluation will happily
        # walk into exactly the position the heuristic policy tries to avoid.
        f["active_safety"] = 0.0 if (v.my_active is not None and v.my_active.id in LIABILITY_2_PRIZE) else 1.0
        return f

    def evaluate(self, state, seat=0):
        v = self.view(state, seat)
        feats = self._features(v)
        score = sum(feats.values()) / max(1, len(feats))

        violations = []
        if v.my_active is not None and v.my_active.id in LIABILITY_2_PRIZE:
            violations.append(Violation("liability_active", "2-prize basic is active"))
        if len(v.my_bench) >= (v.me.benchMax or 5):
            violations.append(Violation("overbench", "bench is full"))

        # Fold violations into the actual score search optimizes for — a
        # feature average alone lets one catastrophic risk get diluted away
        # by several unrelated fine features.
        score = max(0.0, score - W["violation_penalty"] * len(violations))

        missed = [k for k, val in feats.items() if val < 0.34]
        schedule = Schedule(adherence=feats.get("main_line_count", 0.0), missed=missed)

        return EvalResult(score, detect_phase(v), feats, schedule, violations)

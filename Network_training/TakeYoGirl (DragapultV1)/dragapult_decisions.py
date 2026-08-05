"""
dragapult_decisions.py — decision gates consumed by main.py's policy_rank.

Each function answers one game-plan question (attack now? bench this?
retreat? which search hit?) using only the read-only `View`. Everything
returns a `Decision` (recommended flag + 0..1 confidence + a reason string
that shows up verbatim in live_rule_executions.log) so main.py's f-string
logging (`f"{d}"`) works without special-casing.

Every numeric score below is read from `W` (dragapult_heuristics.W) instead
of hardcoded, so train_genetic_dragapult.py can tune this deck's policy the
same way the other decks in this repo are tuned.
"""

from dragapult_heuristics import (
    ID, LIABILITY_2_PRIZE, SEARCH_ITEMS, W,
    phantom_dive_available, munkidori_online, detonators_ready,
)


class Decision:
    __slots__ = ("recommended", "score", "reason")

    def __init__(self, recommended, score=0.5, reason=""):
        self.recommended = recommended
        self.score = score
        self.reason = reason

    def __repr__(self):
        tag = "YES" if self.recommended else "NO"
        return f"{tag} ({self.reason})" if self.reason else tag

    __str__ = __repr__


class Target:
    __slots__ = ("pokemon", "name", "is_bench", "threat_value", "prizes", "counters_to_ko", "efficiency")


class TurnAdvice:
    __slots__ = ("dusclops", "dusknoir", "lillie")

    def __init__(self, dusclops, dusknoir, lillie):
        self.dusclops = dusclops
        self.dusknoir = dusknoir
        self.lillie = lillie


# ---------------------------------------------------------------------------
# Target ranking — who on the opponent's board is worth hitting.
# ---------------------------------------------------------------------------

def _make_target(view, p, is_bench):
    prizes = 2 if view.card_index.is_ex(p.id) else 1
    hp = getattr(p, "hp", 0) or 0
    counters_to_ko = max(1, -(-hp // 10))
    energy_n = view.energy_count(p)

    threat = (
        W["threat_prize_mult"] * prizes
        + min(W["threat_energy_cap"], W["threat_energy_mult"] * energy_n)
        + min(W["threat_hp_cap"], hp / W["threat_hp_div"])
    )
    if not is_bench:
        threat += W["threat_active_bonus"]
    threat = max(0.0, min(1.0, threat))

    efficiency = max(0.0, 1.0 - hp / W["efficiency_hp_div"])

    t = Target()
    t.pokemon = p
    t.name = view.card_index.name(p.id) or str(p.id)
    t.is_bench = is_bench
    t.threat_value = threat
    t.prizes = prizes
    t.counters_to_ko = counters_to_ko
    t.efficiency = efficiency
    return t


def rank_targets(view):
    """Opponent board, best-target-first, for Boss's Orders / Cursed Blast /
    damage-counter placement (rule 5 & 6)."""
    targets = []
    if view.opp_active is not None:
        targets.append(_make_target(view, view.opp_active, is_bench=False))
    for p in view.opp_bench:
        if p is not None:
            targets.append(_make_target(view, p, is_bench=True))
    targets.sort(key=lambda t: (-t.threat_value, -t.prizes, t.counters_to_ko))
    return targets


def best_placement(view, budget_counters):
    """Bench subset (list of Pokemon) that a `budget_counters`-sized spread
    (e.g. Phantom Dive's 6) can KO for the most prizes without waste."""
    bench = [p for p in view.opp_bench if p is not None]
    n = len(bench)
    best_combo, best_prizes = [], 0
    for mask in range(1 << n):
        combo, needed = [], 0
        for i in range(n):
            if mask & (1 << i):
                p = bench[i]
                needed += max(1, -(-getattr(p, "hp", 10) // 10))
                combo.append(p)
        if needed <= budget_counters:
            prizes = sum(2 if view.card_index.is_ex(p.id) else 1 for p in combo)
            if prizes > best_prizes or (prizes == best_prizes and len(combo) > len(best_combo)):
                best_prizes, best_combo = prizes, combo
    return best_combo


# ---------------------------------------------------------------------------
# Rule 5 — Cursed Blast prize math.
# ---------------------------------------------------------------------------

def should_cursed_blast(view, use_dusknoir=False):
    if view.opp_prizes_left <= 1:
        return Decision(False, 0.0, "opponent on last prize — self-KO would hand them the win")

    counters = 13 if use_dusknoir else 5
    dmg = counters * 10
    best = None
    for t in rank_targets(view):
        if getattr(t.pokemon, "hp", 0) <= dmg:
            if best is None or t.prizes > best.prizes or (t.prizes == best.prizes and t.threat_value > best.threat_value):
                best = t

    if best is None:
        return Decision(False, W["cursedblast_no_target"], "nothing dies to this counter count — hold it")

    if view.opp_prizes_left <= best.prizes:
        return Decision(True, W["cursedblast_win"], f"KOs {best.name} for the win")
    if best.prizes >= 2:
        return Decision(True, W["cursedblast_buy_two"], f"KOs {best.name} — buys 2 prizes for the 1 we concede")
    return Decision(False, W["cursedblast_hold"], f"only a 1-for-1 trade on {best.name} — hold it (rule 5)")


def advise_turn(view):
    return TurnAdvice(
        dusclops=should_cursed_blast(view, use_dusknoir=False),
        dusknoir=should_cursed_blast(view, use_dusknoir=True),
        lillie=lillie_or_search(view),
    )


# ---------------------------------------------------------------------------
# Rules 4 / 8 / 9 / D — bench discipline & Dreepy priority.
# ---------------------------------------------------------------------------

def should_bench(view, cid):
    bench_max = getattr(view.me, "benchMax", 5) or 5
    open_slots = bench_max - len(view.my_bench)

    if open_slots <= 0:
        return Decision(False, 0.0, "bench is full")

    if open_slots == 1 and cid not in (ID.DREEPY, ID.DRAKLOAK, ID.BUDEW):
        return Decision(False, W["bench_last_slot_deny"], "keep the last bench slot open (rule 9)")

    if cid in LIABILITY_2_PRIZE:
        existing = sum(1 for p in view.my_board if p and p.id in LIABILITY_2_PRIZE)
        if existing >= 1:
            return Decision(False, W["bench_liability_existing_deny"], "already have a 2-prize liability out (rule 4)")
        if cid == ID.LATIAS_EX and view.my_active is not None and view.my_active.id == ID.BLOODMOON_URSALUNA_EX:
            return Decision(True, W["bench_liability_latias_rescue"], "Latias ex frees the Ursaluna retreat (rule C)")
        return Decision(True, W["bench_liability_default"], "single 2-prize utility body")

    if cid == ID.DUSKULL:
        if view.turn <= 4:
            return Decision(True, W["bench_duskull_early"], "Duskull is still cheap this early (rule 8)")
        return Decision(False, W["bench_duskull_late_deny"], "too late for Duskull — dead weight from here (rule 8)")

    if cid == ID.DREEPY:
        return Decision(True, W["bench_dreepy"], "Dreepy line is the whole game plan (rule D)")

    if cid == ID.MUNKIDORI:
        return Decision(True, W["bench_munkidori"], "cheap utility body")

    if cid == ID.BUDEW:
        if view.count_in_play([ID.BUDEW]) >= 1:
            return Decision(False, W["bench_budew_dup_deny"], "already have a Budew doing the item-lock job")
        if view.turn > 2 or _attacker_charged_on_bench(view) or view.count_in_play([ID.DRAGAPULT_EX, ID.DRAKLOAK]) >= 1:
            return Decision(False, 0.0, "late game Budew bench ban — Budew is useless on bench after early setup")
        return Decision(True, W["bench_budew"], "Budew for the free item lock (rule B)")

    return Decision(True, W["bench_default"], "no specific gate")


# ---------------------------------------------------------------------------
# Energy attachment hard limits & color matching.
# ---------------------------------------------------------------------------

def get_pokemon_max_energy_cost(view, pokemon):
    cid = getattr(pokemon, "id", None)
    if cid == ID.BUDEW:
        return 0
    if cid == ID.DREEPY:
        return 1
    if cid in (ID.DRAKLOAK, ID.DRAGAPULT_EX, ID.DUSKULL, ID.DUSCLOPS, ID.DUSKNOIR):
        return 2
    if cid == ID.MUNKIDORI:
        return 1
    if cid == ID.BLOODMOON_URSALUNA_EX:
        opp_prizes = len(getattr(view.opp, "prize", []) or []) if hasattr(view, "opp") else 6
        prizes_taken = max(0, 6 - opp_prizes)
        return max(0, 5 - prizes_taken)
    return 2


def is_valid_energy_for_pokemon(view, energy_cid, pokemon):
    cid = getattr(pokemon, "id", None)
    if cid == ID.BUDEW:
        return False

    # Special Darkness Energy (#7) is reserved exclusively for Munkidori (#112)
    if energy_cid == ID.SPECIAL_DARKNESS_ENERGY and cid != ID.MUNKIDORI:
        return False

    if cid == ID.MUNKIDORI:
        return energy_cid in (ID.SPECIAL_DARKNESS_ENERGY, ID.BASIC_PSYCHIC_ENERGY)

    attached = getattr(pokemon, "energyCards", []) or []
    attached_ids = [c.id for c in attached if hasattr(c, "id")]

    # Dragapult ex / Drakloak / Dreepy need 1 Fire + 1 Psychic (or 1 Neo Upper)
    if cid in (ID.DRAGAPULT_EX, ID.DRAKLOAK, ID.DREEPY):
        if energy_cid == ID.NEO_UPPER_ENERGY:
            return len(attached_ids) == 0
        has_fire = any(c in (ID.BASIC_FIRE_ENERGY, ID.NEO_UPPER_ENERGY) for c in attached_ids)
        has_psychic = any(c in (ID.BASIC_PSYCHIC_ENERGY, ID.NEO_UPPER_ENERGY) for c in attached_ids)
        if energy_cid == ID.BASIC_FIRE_ENERGY:
            return not has_fire
        if energy_cid == ID.BASIC_PSYCHIC_ENERGY:
            return not has_psychic
        return False

    if cid in (ID.DUSKULL, ID.DUSCLOPS, ID.DUSKNOIR):
        return energy_cid in (ID.BASIC_PSYCHIC_ENERGY, ID.NEO_UPPER_ENERGY)

    return True


def energy_attach_target(view):
    active = view.my_active
    ranked = []
    for p in view.my_board:
        if p is None:
            continue
        is_active = (p is active)
        energy_n = view.energy_count(p)
        max_needed = get_pokemon_max_energy_cost(view, p)

        # Hard Cap: if pokemon already has needed energies for its most costing attack, stop giving energy!
        if energy_n >= max_needed:
            score, why = 0.0, f"hard limit: already has max required energy ({energy_n}/{max_needed})"
        elif p.id == ID.BUDEW:
            score, why = 0.0, "hard limit: Budew attacks for free (0 energy)"
        elif p.id in (ID.MEOWTH_EX, ID.FEZANDIPITI_EX, ID.LATIAS_EX, ID.BLOODMOON_URSALUNA_EX):
            score, why = (W["attach_utility_active_empty"], "stuck active utility body") if (is_active and energy_n == 0) else (W["attach_utility_bench"], "utility body, not the attacker")
        elif p.id == ID.DRAGAPULT_EX:
            if energy_n == 1:
                score, why = W["attach_dragapult_one_energy"], "second energy completes Phantom Dive"
            else:
                score, why = (W["attach_dragapult_active_empty"] if is_active else W["attach_dragapult_bench_empty"]), "priming the attacker"
        elif p.id in (ID.DREEPY, ID.DRAKLOAK):
            score, why = (W["attach_pre_evo_empty"], "light early investment") if energy_n == 0 else (W["attach_pre_evo_has_energy"], "pre-evolution — don't overinvest")
        elif p.id == ID.DUSKNOIR:
            score, why = W["attach_dusknoir"], "Shadow Bind backup attacker"
        elif p.id == ID.MUNKIDORI:
            score, why = (W["attach_munkidori_empty"], "needs its one Darkness for Adrena-Brain") if energy_n == 0 else (W["attach_munkidori_has_energy"], "already has what it needs")
        else:
            score, why = W["attach_generic"], "generic"

        ranked.append((p, score, why))

    ranked.sort(key=lambda t: -t[1])
    return ranked


# ---------------------------------------------------------------------------
# Rule 7 — Lillie vs. holding for search.
# ---------------------------------------------------------------------------

def lillie_or_search(view):
    hand_ids = list(view.hand_ids)
    has_nondiscard_search = any(cid in (ID.BUDDY_BUDDY_POFFIN, ID.POKEGEAR_3, ID.ENERGY_SEARCH, ID.ULTRA_BALL, ID.NIGHT_STRETCHER) for cid in hand_ids)
    has_benchable = any(cid in (ID.DREEPY, ID.DRAKLOAK, ID.DRAGAPULT_EX, ID.DUSKULL) for cid in hand_ids) and len(view.my_bench) < 5
    has_playable_energy = any(cid in (ID.BASIC_FIRE_ENERGY, ID.BASIC_PSYCHIC_ENERGY, ID.NEO_UPPER_ENERGY) for cid in hand_ids) and not getattr(view.me, "energyAttached", False)

    # Hold Lillie while unplayed non-discard search items, Dragapults, or energy remain in hand
    if has_nondiscard_search or has_benchable or has_playable_energy:
        return Decision(False, W["play_lillie_hold"], "hold Lillie until non-discard search, benching, and energy placement are complete")

    hand_n = len(hand_ids)
    # Reshuffle with Lillie if hand size < 6 after playing search/pokemon/energy
    if hand_n < 6:
        return Decision(True, W["play_lillie_go"], f"hand size ({hand_n}) < 6 after setup — reshuffle with Lillie")

    return Decision(False, W["play_lillie_hold"], "hand size >= 6 — no need to reshuffle yet")


def recon_directive_timing(view):
    return Decision(True, W["recon_directive"], "free card selection — always take it")


def choose_first_or_second(view):
    return Decision(True, W["go_first"], "go first — first attachment/evolution beats the extra card (rule 1)")


def should_mulligan_keep(view, hand_ids):
    ids = list(hand_ids)
    if ID.BUDEW in ids:
        return Decision(True, W["mulligan_keep_basic"], "has Budew in opening hand to open and item-lock from turn 1")
    search = sum(1 for cid in ids if cid in SEARCH_ITEMS or cid == ID.POKEGEAR_3)
    basics = sum(1 for cid in ids if cid in (ID.DREEPY, ID.DUSKULL))
    if search >= 1 and basics >= 1:
        return Decision(True, W["mulligan_keep_searcher"], "no Budew directly, but has basic + searcher to dig for Budew")
    return Decision(False, W["mulligan_redraw"], "no Budew in opening hand — redraw deck to get Budew")


# ---------------------------------------------------------------------------
# Rule A — discard priority (protect our last draw engine).
# ---------------------------------------------------------------------------

def discard_priority(view, cid, hand_value):
    """Higher = discard this first. Overrides the flat HAND_VALUE lookup so
    we never strand ourselves with no way to draw more cards (rule A)."""
    base = 1.0 - hand_value.get(cid, 0.35)

    if cid == ID.LILLIES_DETERMINATION:
        copies_in_hand = view.count_in_hand([ID.LILLIES_DETERMINATION])
        other_draw = (
            view.count_in_play([ID.DRAKLOAK]) > 0
            or view.count_in_hand([ID.POKEGEAR_3]) > 0
            or view.count_in_hand([ID.HILDA]) > 0
            or view.count_in_play([ID.FEZANDIPITI_EX]) > 0
        )
        if copies_in_hand <= 1 and not other_draw:
            return 0.0
        if copies_in_hand <= 1:
            return base * W["discard_guard_factor"]

    return base


# ---------------------------------------------------------------------------
# Rules B / C — who should be active, and whether to retreat there.
# ---------------------------------------------------------------------------

def _attacker_charged_on_bench(view):
    """True if Dragapult ex (2+ energy) or Dusknoir is sitting on the bench,
    ready to swing but not yet active. `phantom_dive_available` can't answer
    this — it only looks at the current active slot, which is exactly the
    position we're trying to decide whether to leave."""
    for p in view.my_bench:
        if p is None:
            continue
        if p.id == ID.DRAGAPULT_EX and view.energy_count(p) >= 2:
            return True
        if p.id == ID.DUSKNOIR:
            return True
    return False


def switch_target_score(view, cid, pokemon):
    """Score a candidate to become our new Active Pokemon."""
    energy_n = view.energy_count(pokemon)

    if cid == ID.BUDEW:
        # Rule B: Budew belongs active whenever nothing better is ready to
        # attack — it swings Itchy Pollen for free and item-locks every turn
        # at zero cost until we're set up.
        attacker_ready = phantom_dive_available(view) or _attacker_charged_on_bench(view) or view.count_in_play([ID.DUSKNOIR]) > 0
        return W["switch_budew_ready"] if attacker_ready else W["switch_budew_not_ready"]

    if cid == ID.DRAGAPULT_EX and energy_n >= 2:
        return W["switch_dragapult_charged"]

    if cid == ID.DUSKNOIR:
        return W["switch_dusknoir"]

    if cid in (ID.DREEPY, ID.DRAKLOAK):
        return W["switch_pre_evo_energy"] if energy_n > 0 else W["switch_pre_evo_empty"]

    if cid in (ID.MEOWTH_EX, ID.FEZANDIPITI_EX, ID.LATIAS_EX, ID.BLOODMOON_URSALUNA_EX):
        # Rule C: once we're off these, don't volunteer them back into active.
        return W["switch_liability"]

    return W["switch_default"]


def retreat_score(view):
    """Should we retreat this turn at all? (rules B & C)."""
    active = view.my_active
    if active is None:
        return 0.0

    if active.id == ID.BLOODMOON_URSALUNA_EX:
        # Rule C: Ursaluna is dead weight active — leave the instant we can,
        # and Latias ex's Skyliner ability makes that retreat free.
        free_retreat = view.count_in_play([ID.LATIAS_EX]) > 0
        return W["retreat_ursaluna_free"] if free_retreat else W["retreat_ursaluna_paid"]

    attacker_waiting = _attacker_charged_on_bench(view)

    if active.id == ID.BUDEW:
        # Rule B: hold the item lock until a real attacker is charged and
        # waiting to come in — not just "already active", which would never
        # be true for the very retreat that brings it in.
        return W["retreat_budew_attacker_waiting"] if attacker_waiting else W["retreat_budew_holding"]

    if active.id == ID.DRAGAPULT_EX and view.energy_count(active) >= 2:
        return W["retreat_dragapult_ready"]   # our attacker is already in — stay and swing

    if attacker_waiting:
        # Something charged is stuck on the bench behind a non-attacker
        # active. Get out of the way and bring it in.
        return W["retreat_attacker_waiting"]

    return W["retreat_default"]


# ---------------------------------------------------------------------------
# Rule D — search-hit priority (Dreepy first).
# ---------------------------------------------------------------------------

def search_target_score(view, cid):
    if cid == ID.DRAGAPULT_EX:
        return W["search_hit_dragapult_ex"]
    if cid == ID.DREEPY:
        return W["search_hit_dreepy"]
    if cid == ID.DRAKLOAK:
        return W["search_hit_drakloak"]
    if cid in (ID.BASIC_FIRE_ENERGY, ID.BASIC_PSYCHIC_ENERGY, ID.NEO_UPPER_ENERGY):
        return W["search_hit_energy"]
    if cid == ID.BUDEW:
        if view.turn <= 2 and view.count_in_play([ID.BUDEW]) == 0 and not _attacker_charged_on_bench(view) and view.count_in_play([ID.DRAGAPULT_EX, ID.DRAKLOAK]) == 0:
            return W["search_hit_budew"]
        return 0.0
    if cid == ID.DUSKULL and view.turn <= 4:
        return W["search_hit_duskull_early"]
    if cid in LIABILITY_2_PRIZE:
        return W["search_hit_liability"]
    return W["search_hit_default"]

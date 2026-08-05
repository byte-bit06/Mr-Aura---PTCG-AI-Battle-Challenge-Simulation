"""
dragapult_priorities.py — fixes for three bugs the battle transcripts exposed.

Each function returns a score in [0,1], or None meaning "no opinion, use the
existing weight". Drop-in: call them from the matching branches of
`policy_rank` in main.py.

--------------------------------------------------------------------------
BUG 1 — attack selection is blind
--------------------------------------------------------------------------
main.py scores every ATTACK option identically:

    s = W["policy_attack_ready"] if phantom_dive_available(view) else ...

Every attack gets the same number, so ties break by option index. The agent
cannot tell Phantom Dive from Dragapult's cheap attack, or either from
Budew's Itchy Pollen. Game 12 built Dragapult ex, attached Neo Upper Energy,
promoted it, and then used attackId 153 — one damage placement all game.
Game 9 (the only win in 14) used attackId 154 and placed six.

Fix: score attacks by their actual damage, read from `cg.api.all_attack()`.

--------------------------------------------------------------------------
BUG 2 — retreating discards the energy we just attached
--------------------------------------------------------------------------
Game 13, turn 10, in order:

    EVOLVE -> Dragapult ex
    ATTACH Basic {R} Energy -> Dragapult ex (active)
    RETREAT Dragapult
    DISCARD ENERGY Dragapult ex   (retreat cost)
    SWITCH: PICK Budew
    ATTACK Budew (attackId 323)      <- 10 damage

It built the win condition, fuelled it, threw the fuel away to retreat it,
and attacked for 10 with a 30 HP Budew. Game 14 does the same thing three
times with Duskull and Meowth ex.

`retreat_score` only protects Dragapult at 2+ energy:

    if active.id == ID.DRAGAPULT_EX and view.energy_count(active) >= 2:
        return W["retreat_dragapult_ready"]

At one energy it falls through to `retreat_default` and retreats anyway.
That single missing case is why 57% of all attached energy is discarded.

Fix: veto any retreat that pays energy, unless the retreat is free or the
active is genuinely dead weight.

--------------------------------------------------------------------------
BUG 3 — energy goes onto bodies that never attack
--------------------------------------------------------------------------
`attach_utility_active_empty` is 0.54, so Duskull, Meowth ex and Budew are
attractive attach targets whenever they're active. They cannot use that
energy, and it is usually discarded to a retreat on the same turn.

Fix: only the Dragapult line and Munkidori are real attach targets.
"""

from dragapult_heuristics import ID

# Bodies that can actually convert energy into damage or an ability.
REAL_ATTACH_TARGETS = {ID.DRAGAPULT_EX, ID.DRAKLOAK, ID.DREEPY, ID.MUNKIDORI}

# Bodies we hold energy off entirely — they attack for chip damage at best.
NEVER_ATTACH = {ID.BUDEW, ID.DUSKULL, ID.DUSCLOPS, ID.MEOWTH_EX,
                ID.FEZANDIPITI_EX, ID.LATIAS_EX}

MAX_REFERENCE_DAMAGE = 200.0   # Phantom Dive's active damage

# A hard veto, not a low score. The search builds its candidate list by
# calling policy_rank, so an option merely ranked last is still explored and
# can still be chosen on rollout value. Options scoring at or below this are
# DROPPED from the ranking entirely and never reach the search.
HARD_VETO = -1.0
VETO_THRESHOLD = -0.5

# END is different from a veto. If every real action is vetoed, ending the
# turn is the CORRECT move — better to hold the energy than to dump it on a
# body that cannot use it and then retreat. So END sits below every real
# action but above the veto line, and therefore always survives the filter.
END_LAST = -0.4


def is_veto(score):
    return score is not None and score <= VETO_THRESHOLD


# ---------------------------------------------------------------------------
# Attack table, built once from the engine
# ---------------------------------------------------------------------------

_ATTACKS = {}


def build_attack_table(all_attack_fn=None):
    """
    Map attackId -> (name, damage, energy_cost). Call once at startup:

        from cg.api import all_attack
        build_attack_table(all_attack)
    """
    global _ATTACKS
    if all_attack_fn is None:
        try:
            from cg.api import all_attack as all_attack_fn
        except Exception:
            return _ATTACKS
    try:
        _ATTACKS = {
            a.attackId: (
                getattr(a, "name", "") or "",
                int(getattr(a, "damage", 0) or 0),
                list(getattr(a, "energies", []) or []),
            )
            for a in all_attack_fn()
        }
    except Exception:
        pass
    return _ATTACKS


def attack_info(attack_id):
    return _ATTACKS.get(attack_id)


# ---------------------------------------------------------------------------
# BUG 1 — score attacks by what they actually do
# ---------------------------------------------------------------------------

def attack_score(view, option, opt_get):
    """
    Score a single ATTACK option. `opt_get(option, key)` reads a field.

    Kept below the score of free actions (playing cards, evolving, using
    abilities) so the agent still empties its hand first — attacking ends
    the turn. Among attacks, the best one now actually wins.
    """
    aid = opt_get(option, "attackId")
    info = attack_info(aid)
    if info is None:
        return None                      # no table — fall back to the weight
    name, damage, cost = info

    score = 0.30 + 0.40 * min(1.0, damage / MAX_REFERENCE_DAMAGE)

    # Spread attacks (Phantom Dive) are the deck's win condition: their real
    # output is far above the printed active damage.
    if "phantom" in name.lower():
        score += 0.10

    # Taking the KO now is worth more than the raw damage suggests.
    opp = view.opp_active
    if opp is not None and damage >= getattr(opp, "hp", 10 ** 6):
        score += 0.10

    # Chip attacks are near-worthless once a real attacker exists anywhere.
    if damage <= 20 and _has_real_attacker(view):
        score = min(score, 0.15)

    return max(0.0, min(0.80, score))


def _has_real_attacker(view):
    for p in view.my_board:
        if p is not None and getattr(p, "id", None) == ID.DRAGAPULT_EX:
            return True
    return False


# ---------------------------------------------------------------------------
# BUG 2 — never pay energy to retreat
# ---------------------------------------------------------------------------

def retreat_veto(view):
    """
    Return a near-zero score to block a retreat, or None to let the existing
    `retreat_score` decide.

    A retreat that discards energy is a strictly negative trade for this deck:
    it costs an attachment we only get one of per turn, and the deck runs 8
    energy total.
    """
    active = view.my_active
    if active is None:
        return None

    energy_on_active = len(getattr(active, "energies", None) or [])
    if energy_on_active == 0:
        return None                      # free to leave, no opinion

    # Latias ex's Skyliner makes BASIC Pokemon retreat for nothing.
    free = _free_retreat(view, active)
    if free:
        return None

    aid = getattr(active, "id", None)

    # Dead weight is worth the energy to escape.
    if aid == ID.BLOODMOON_URSALUNA_EX:
        return None

    return HARD_VETO                     # everything else: hold position


def _free_retreat(view, active):
    has_latias = any(getattr(p, "id", None) == ID.LATIAS_EX
                     for p in view.my_board if p is not None)
    if not has_latias:
        return False
    # Skyliner only zeroes the cost for Basic Pokemon.
    return getattr(active, "id", None) in (
        ID.DREEPY, ID.DUSKULL, ID.BUDEW, ID.MUNKIDORI, ID.MEOWTH_EX,
        ID.LATIAS_EX, ID.FEZANDIPITI_EX, ID.BLOODMOON_URSALUNA_EX)


# ---------------------------------------------------------------------------
# BUG 3 — attach only to bodies that use energy
# ---------------------------------------------------------------------------

def attach_veto(view, option, opt_get):
    """
    Return a near-zero score for attaching to a body that cannot convert the
    energy, or None to let the existing attach ranking decide.
    """
    area = opt_get(option, "inPlayArea")
    idx = opt_get(option, "inPlayIndex") or 0
    target = _target_of(view, area, idx)
    if target is None:
        return None
    aid = getattr(target, "id", None)

    if aid in REAL_ATTACH_TARGETS:
        return None
    if aid == ID.BLOODMOON_URSALUNA_EX and view.my_prizes_left() <= 3:
        return None                      # its cost drops as they take prizes
    if aid in NEVER_ATTACH:
        return HARD_VETO
    return None


def _target_of(view, area, idx):
    if area == 4:                        # ACTIVE
        return view.my_active
    if area == 5:                        # BENCH
        bench = view.my_bench
        return bench[idx] if 0 <= idx < len(bench) else None
    return None


# ---------------------------------------------------------------------------
# BUG 5 — energy is discarded to pay Ultra Ball, in an 8-energy deck
# ---------------------------------------------------------------------------

ENERGY_IDS = {2, 5, 7, 10}          # Fire, Psychic, Darkness, Neo Upper
ENERGY_FLOOR = 3                    # below this, energy is untouchable

# Discard priority is (1 - hand_value), and the tuned hand_values put energy
# near the bottom: neo_upper_energy 0.30, basic_fire 0.43, basic_psychic 0.45
# — all below Pokegear (0.50). So Ultra Ball's cost eats the one resource the
# deck cannot replace. Phantom Dive needs two energy on one body and the list
# runs eight energy total with a single Energy Search.


def discard_veto(view, cid):
    """Refuse to discard energy while the deck is short of it."""
    if cid not in ENERGY_IDS:
        return None
    on_board = sum(len(getattr(p, "energies", None) or [])
                   for p in view.my_board if p is not None)
    in_hand = sum(1 for c in view.hand_ids if c in ENERGY_IDS)
    if on_board + in_hand <= ENERGY_FLOOR:
        return HARD_VETO
    return None


# ---------------------------------------------------------------------------
# BUG 4 — END is a floor, not a last resort
# ---------------------------------------------------------------------------

def end_turn_score(options, opt_get, type_of_end, type_of_no):
    """
    Return a score for the END option. Several tuned weights sit *below*
    `policy_end` (attach_budew is literally 0.0), so whenever every available
    action happens to be low-scored the agent simply stops playing.

    END should never compete with a legal action, but it must remain
    selectable: if every real option is vetoed, ending the turn is right.
    """
    for o in options:
        t = opt_get(o, "type")
        t = getattr(t, "value", t)
        if t not in (type_of_end, type_of_no):
            return END_LAST
    return None

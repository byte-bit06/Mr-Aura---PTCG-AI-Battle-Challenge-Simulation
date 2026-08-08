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
NEVER_ATTACH = {ID.BUDEW, ID.DUSKULL, ID.DUSCLOPS, ID.MEOWTH_EX, ID.LATIAS_EX}

MAX_REFERENCE_DAMAGE = 200.0   # Phantom Dive's active damage

# Cards not present in dragapult_heuristics.ID
ID_CRISPIN = 1198              # supporter: attach 1 basic energy + 1 to hand

# The plan, in one place. Everything below is scored against it:
#   T1  three Dreepy on board
#   T2  Rare Candy one of them straight to Dragapult ex, that one attacks
#   T2+ the rest become Drakloak and Recon Directive every turn
#   T3  Phantom Dive, and every turn after
# Recon Directive is what pays for running eight energy, so bench Drakloak
# count is an engine stat, not a board stat.
RUSH_TURNS = 3                 # turns in which setup outranks everything

SUPPORTERS = {ID.LILLIES_DETERMINATION, ID.BOSSES_ORDERS, ID.HILDA, ID_CRISPIN}
ENERGY_IDS = {2, 5, 7, 10}     # Fire, Psychic, Darkness, Neo Upper

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

def ready_attacker_on_bench(view):
    """A bench Pokemon that could Phantom Dive right now if it were active."""
    for p in view.my_bench:
        if p is None or getattr(p, "id", None) != ID.DRAGAPULT_EX:
            continue
        e = list(getattr(p, "energies", None) or [])
        if e.count(RAINBOW) >= 2:
            return p
        if all(c in e or RAINBOW in e for c in PHANTOM_DIVE_COST):
            return p
    return None


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

    # Promoting a loaded attacker beats every energy-preservation concern.
    # Game 23: a Phantom-Dive-ready Dragapult sat on the bench for SEVEN
    # turns while a 30 HP Budew attacked for 10 a turn, because this veto
    # dropped `retreat` from the ranking whenever the active held energy.
    if getattr(active, "id", None) != ID.DRAGAPULT_EX:
        if ready_attacker_on_bench(view) is not None:
            return 0.96

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
        # REGRESSION FIX. Vetoing outright meant that whenever the only
        # bodies in play were Budew / Duskull / Meowth ex, EVERY attachment
        # was blocked and the energy sat in hand for the rest of the game
        # (game 14: five turns, 0.07 attach/turn). The manual attachment does
        # not carry over, so a wasted attach still beats no attach. Only
        # refuse when something better is actually on the board.
        has_real = any(getattr(p, "id", None) in REAL_ATTACH_TARGETS
                       for p in view.my_board if p is not None)
        return HARD_VETO if has_real else 0.30
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

ENERGY_FLOOR = 3                    # below this, energy is untouchable

# Discard priority is (1 - hand_value), and the tuned hand_values put energy
# near the bottom: neo_upper_energy 0.30, basic_fire 0.43, basic_psychic 0.45
# — all below Pokegear (0.50). So Ultra Ball's cost eats the one resource the
# deck cannot replace. Phantom Dive needs two energy on one body and the list
# runs eight energy total with a single Energy Search.


# Cards the plan cannot spare. Game 13 turn 2 discarded BOTH copies of
# Lillie's Determination to an Ultra Ball cost, on the turn the first player
# cannot play a Supporter anyway - throwing away the turn-2 draw.
PROTECTED_FROM_DISCARD = {ID.DRAGAPULT_EX, ID.RARE_CANDY}


def discard_veto(view, cid):
    """Refuse to discard energy, or a piece the setup plan still needs."""
    if cid in PROTECTED_FROM_DISCARD:
        return HARD_VETO
    if cid == ID.LILLIES_DETERMINATION:
        # Only spare it while it is one of our last ways to refuel.
        in_hand = sum(1 for c in view.hand_ids if c in SUPPORTERS)
        return HARD_VETO if in_hand <= 2 else None
    if cid not in ENERGY_IDS:
        return None
    on_board = sum(len(getattr(p, "energies", None) or [])
                   for p in view.my_board if p is not None)
    in_hand = sum(1 for c in view.hand_ids if c in ENERGY_IDS)
    if on_board + in_hand <= ENERGY_FLOOR:
        return HARD_VETO
    return None


# ---------------------------------------------------------------------------
# BUG 6 — evolutions are all scored with one weight
# ---------------------------------------------------------------------------
# `policy_evolve` is a single number for every EVOLVE option, so ties break by
# option index — the same blindness that stopped the agent choosing Phantom
# Dive over Itchy Pollen. It cannot prefer "evolve a bench Dreepy into
# Drakloak" (the draw/energy engine) over anything else on offer.
#
# The deck's engine is Recon Directive: every Drakloak on the bench digs
# further each turn, which is what pays for running only eight energy. More
# Drakloak is compounding value; the attacker goes to Dragapult ex.




def evolve_score(view, cid, option=None, opt_get=None):
    """
    Score an evolution. WHERE it lands matters as much as what it is.

    Game 25: Rare Candy put Dragapult ex onto a BENCH Dreepy while a 0-energy
    Duskull held the active spot. Duskull could not pay its retreat cost, so
    the attacker was stranded on the bench for three turns and only came up
    after Duskull was knocked out. A Dragapult that cannot be promoted is not
    an attacker.
    """
    on_active = None
    if option is not None and opt_get is not None:
        area = opt_get(option, "inPlayArea")
        if area in (4, 5):
            on_active = (area == 4)

    if cid == ID.DRAGAPULT_EX:
        base = 0.98 if view.turn <= RUSH_TURNS * 2 else 0.92
        if on_active is False and not _can_promote(view):
            # It would be stranded. Still better than nothing late, but it
            # must not outrank evolving the active.
            return 0.35
        if on_active:
            base = min(0.995, base + 0.02)
        return base
    if cid == ID.DRAKLOAK:
        # Each one is another Recon Directive every turn. Stack them.
        have = view.count_in_play([ID.DRAKLOAK])
        return 0.95 if have < 3 else 0.86
    if cid in (ID.DUSCLOPS, ID.DUSKNOIR):
        return 0.70
    return None


# ---------------------------------------------------------------------------
# BUG 9 — the setup race is not prioritised
# ---------------------------------------------------------------------------
# Dragapult was arriving on turn 6-10. It needs to arrive on turn 2 via Rare
# Candy. `play_default` is 0.54 and Rare Candy only beats it when a Duskull
# or Dreepy happens to be in play — nothing makes the Candy line the point of
# the early turns, and nothing values Crispin's energy acceleration at all.


def play_score(view, cid):
    early = view.turn <= RUSH_TURNS * 2
    line_in_play = view.count_in_play([ID.DREEPY, ID.DRAKLOAK])
    have_pult = (ID.DRAGAPULT_EX in view.hand_ids
                 or view.count_in_play([ID.DRAGAPULT_EX]) > 0)

    if cid == ID.RARE_CANDY:
        # Candy is only worth its slot when it converts a body into Dragapult.
        if line_in_play and ID.DRAGAPULT_EX in view.hand_ids:
            return 0.99
        return 0.20

    if cid == ID_CRISPIN:
        # Energy acceleration: one attached plus one to hand, which is exactly
        # the two energy Phantom Dive needs.
        on_board = sum(len(getattr(p, "energies", None) or [])
                       for p in view.my_board if p is not None)
        return 0.96 if on_board < 2 else 0.72

    if cid == ID.BOSSES_ORDERS:
        # Boss's Orders is a SUPPORTER. Playing it burns the once-per-turn
        # Supporter slot that Lillie's Determination / Hilda / Crispin need,
        # and the transcripts show it being fired on turn 2 for no gain while
        # Hilda sat in hand. It is only worth the slot when the gust converts
        # into a knockout THIS turn.
        return 0.93 if _boss_converts(view) else 0.08

    if cid == ID.BUDDY_BUDDY_POFFIN:
        # Three Dreepy on turn 1 is the target.
        return 0.97 if (early and line_in_play < 3) else 0.80

    if cid == ID.POKE_PAD:
        return 0.90 if (early and line_in_play < 3) else 0.70

    if cid == ID.ULTRA_BALL:
        # Worth two cards early only while it's finding the line.
        return 0.88 if (early and not have_pult) else 0.62

    return None


def _can_promote(view):
    """
    Could we actually get a bench attacker into the active spot next turn?
    True if the active can pay its retreat cost, or is a free-retreat Basic
    with Latias ex out, or is already a Dragapult.
    """
    active = view.my_active
    if active is None:
        return True
    aid = getattr(active, "id", None)
    if aid == ID.DRAGAPULT_EX:
        return True
    if len(getattr(active, "energies", None) or []) >= 1:
        return True                       # can pay a retreat
    return _free_retreat(view, active)


# Phantom Dive costs {R}{P}. Attaching two of the same type strands the
# attacker on its weaker attack - game 25 put {P}{P} on Dragapult and could
# only use attackId 153 all game.
FIRE, PSYCHIC, RAINBOW = 2, 5, 10
PHANTOM_DIVE_COST = (FIRE, PSYCHIC)


def attach_energy_fit(view, option, opt_get):
    """Prefer the energy type the attacker is still missing."""
    area = opt_get(option, "inPlayArea")
    idx = opt_get(option, "inPlayIndex") or 0
    target = _target_of(view, area, idx)
    if target is None:
        return None
    if getattr(target, "id", None) not in (ID.DRAGAPULT_EX, ID.DRAKLOAK, ID.DREEPY):
        return None

    card = opt_get(option, "cardId")
    have = list(getattr(target, "energies", None) or [])
    if RAINBOW in have or card == RAINBOW:
        return 0.97 if card == RAINBOW else None   # Neo Upper covers both
    missing = [e for e in PHANTOM_DIVE_COST if e not in have]
    if not missing:
        return None                        # already paid; no opinion
    if card in missing:
        return 0.97                        # completes or advances the cost
    if card in PHANTOM_DIVE_COST:
        return 0.40                        # duplicate type, blocks the dive
    return None


def _boss_converts(view):
    """True if we can actually knock out something on their bench right now."""
    active = view.my_active
    ready = (active is not None
             and getattr(active, "id", None) == ID.DRAGAPULT_EX
             and len(getattr(active, "energies", None) or []) >= 2)
    if not ready:
        return False
    reach = MAX_REFERENCE_DAMAGE          # Phantom Dive to the new active
    for p in view.opp_bench:
        if p is not None and getattr(p, "hp", 10 ** 6) <= reach:
            return True
    return False


def search_score(view, cid):
    """What to take when a search puts a card into hand."""
    line_in_play = view.count_in_play([ID.DREEPY, ID.DRAKLOAK])
    early = view.turn <= RUSH_TURNS * 2
    in_hand = view.hand_ids

    have_pult = (ID.DRAGAPULT_EX in in_hand
                 or view.count_in_play([ID.DRAGAPULT_EX]) > 0)
    have_candy = ID.RARE_CANDY in in_hand

    # The win condition outranks everything. `search_target_score` sends every
    # 2-prize Pokemon to `search_hit_liability` (0.20, the lowest value in the
    # table), so Ultra Ball would essentially never fetch Dragapult ex — which
    # is why it arrived on turn 6-9 instead of turn 2.
    if cid == ID.DRAGAPULT_EX and not have_pult:
        return 0.99 if (have_candy and line_in_play) else 0.94
    if cid == ID.RARE_CANDY and have_pult and line_in_play:
        return 0.98
    if cid == ID.DREEPY and line_in_play < 3:
        return 0.97                       # three bodies first
    if cid == ID_CRISPIN:
        return 0.92
    if cid == ID.DRAKLOAK:
        return 0.88                       # engine
    if cid == ID.MEOWTH_EX:
        has_supporter = any(c in SUPPORTERS for c in in_hand)
        if not has_supporter and view.count_in_play([ID.MEOWTH_EX]) == 0:
            return 0.90                   # a real out to a Supporter
        return None
    if cid in ENERGY_IDS:
        on_board = sum(len(getattr(p, "energies", None) or [])
                       for p in view.my_board if p is not None)
        return 0.90 if on_board < 2 else 0.55
    if cid in SUPPORTERS and early:
        return 0.82
    return None


# ---------------------------------------------------------------------------
# BUG 7 — Meowth ex is treated as a liability, not as a supporter-out
# ---------------------------------------------------------------------------
# `search_target_score` sends every 2-prize Pokemon to `search_hit_liability`
# (0.20, the lowest value there is). Meowth ex is a 2-prize body, so Ultra
# Ball will essentially never fetch it — but its ability is one of the deck's
# main ways to find a Supporter, which is the whole reason it's in the 60.


# ---------------------------------------------------------------------------
# BUG 8 — declining our own ability prompts
# ---------------------------------------------------------------------------
# The transcripts show `PLAY Meowth ex` immediately followed by
# `ACTIVATE: no` (game 21 turn 9, game 22 turn 12). The agent benched its
# supporter-finder and then refused to use it. `_CTX_ACTIVATE = 43` is
# defined in main.py but never referenced, so the prompt falls through to the
# generic yes/no weights.


def activate_score(is_yes):
    """Our own on-play abilities are free value — take them."""
    return 0.88 if is_yes else 0.12


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

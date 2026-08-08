"""
Dragapult ex / Dusknoir Agent — Heuristic Evaluation + Expectimax Turn Search
============================================================================

Entry point: `agent(obs_dict) -> list[int]`, matching the harness contract.

This file is *plumbing only*. All strategy lives in three modules that sit
alongside it:

    dragapult_heuristics.py   position evaluation (22 normalized features)
    dragapult_decisions.py    decision gates (Cursed Blast, placement, ...)
    dragapult_search.py       expectimax / UCT turn search over cg.api

Strategic directives (derived from the deck guide, enforced by those modules):
  1. Go first. First attachment and first evolution beat the extra card.
  2. Turn 1: at least one Dreepy down, one energy attached, a bench slot left
     open, and Lillie access secured. Turn 2: Drakloak up, Duskull seeded.
  3. One energy every turn, without exception. Missed attachments are the
     single largest scoring penalty after overbenching.
  4. Never overbench two-prize Pokemon. One 2-prize attacker is the plan;
     every extra is a prize the opponent gets to choose.
  5. Cursed Blast concedes a prize — it must buy two, remove a blocker
     (Psyduck / Rabsca / Lillie's Clefairy / their Munkidori), or be held.
     Never detonate while the opponent is on their last prize.
  6. Phantom Dive's 6 counters are bench-only; Cursed Blast and Adrena Brain
     go anywhere. Overkill is waste; damage left out of range gets healed off.
  7. Prioritize our own setup over disrupting theirs. Disruption is what you
     do once you're already playing the game.
  8. Duskull hits the board early or not at all — a 60 HP body is a liability
     from the midgame on.
  9. Keep the last bench slot open. A locked bench removes our outs.

Safety contract: this module never raises out of `agent()`. Every path ends
in `sanitize_action`, which guarantees a legal selection.
"""

import os
import sys
import time
import json
import csv
import traceback

# --- make sibling modules importable regardless of how we're launched -------
try:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _BASE_DIR = "/kaggle_simulations/agent"
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

RULE_LOG_FILE = os.path.join(_BASE_DIR, "live_rule_executions.log")


_SUPPRESS_LOG = [False]   # set while policy_rank runs inside search's simulated rollout


def log_rule_execution(msg):
    if _SUPPRESS_LOG[0]:
        return
    sys.stderr.write(f"{msg}\n")
    try:
        with open(RULE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


try:
    with open(RULE_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== DRAGAPULT AGENT — HEURISTIC + SEARCH EXECUTION LOG ===\n\n")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Strategy modules
# ---------------------------------------------------------------------------

_STRATEGY_OK = True
try:
    from dragapult_heuristics import (
        DECK_ID_LIST, ID, CardIndex, Heuristics, View,
        detect_phase, phantom_dive_available, munkidori_online,
        detonators_ready, abilities_locked, plan_prizes_this_turn,
        HAND_VALUE, LIABILITY_2_PRIZE, SEARCH_ITEMS, W,
    )
    from dragapult_decisions import (
        advise_turn, should_cursed_blast, should_bench, energy_attach_target,
        lillie_or_search, recon_directive_timing, rank_targets, best_placement,
        should_mulligan_keep, choose_first_or_second,
        discard_priority, switch_target_score, retreat_score, search_target_score,
    )
    from dragapult_search import (
        SearchConfig, TurnSearch, enumerate_moves, move_signature,
        option_signature, OptionType, SelectContext, SelectType,
    )
except Exception as _e:  # pragma: no cover - only fires on a broken bundle
    _STRATEGY_OK = False
    log_rule_execution(f"  [FATAL] strategy modules unavailable: {_e}")
    DECK_ID_LIST = []


# ---------------------------------------------------------------------------
# Deck
# ---------------------------------------------------------------------------

_FALLBACK_DECK = (
    [119] * 4 + [120] * 4 + [121] * 3          # Dreepy / Drakloak / Dragapult ex
    + [131] * 2 + [132] * 2 + [133]            # Duskull / Dusclops / Dusknoir
    + [112] + [235] * 2 + [1071] + [184]       # Munkidori / Budew / Meowth ex / Latias ex
    + [140] + [44]                             # Fezandipiti ex / Bloodmoon Ursaluna ex
    + [1086] * 4 + [1227] * 4 + [1122] * 3     # Poffin / Lillie's Determination / Pokegear
    + [1152] * 3 + [1079] * 3 + [1182] * 3     # Poke Pad / Rare Candy / Boss's Orders
    + [1097] * 2 + [1121] * 3 + [1119]         # Night Stretcher / Ultra Ball / Energy Search
    + [1120] + [1225] * 2                      # Crushing Hammer / Hilda
    + [5] * 3 + [7] + [2] * 3 + [10]           # Psychic / Darkness / Fire / Neo Upper Energy
)


def load_deck():
    for p in [os.path.join(_BASE_DIR, "deck.csv"), "deck.csv",
              "/kaggle_simulations/agent/deck.csv"]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    cards = [int(line) for line in f if line.strip()]
                if len(cards) == 60:
                    return cards
            except Exception:
                pass
    deck = list(DECK_ID_LIST) if DECK_ID_LIST else list(_FALLBACK_DECK)
    return deck if len(deck) == 60 else list(_FALLBACK_DECK)


my_deck = load_deck()
log_rule_execution(f"  [DECK LOADED] {len(my_deck)} cards | unique={len(set(my_deck))}")


# ---------------------------------------------------------------------------
# Engine binding
# ---------------------------------------------------------------------------

_SEARCH_OK = False
_CG = {}
try:
    from cg.api import (
        all_card_data, search_begin, search_step, search_end, search_release,
        to_observation_class,
    )
    _CG = {
        "all_card_data": all_card_data,
        "search_begin": search_begin,
        "search_step": search_step,
        "search_end": search_end,
        "search_release": search_release,
        "to_observation_class": to_observation_class,
    }
    _SEARCH_OK = True
except Exception as _e:
    log_rule_execution(f"  [ENGINE] cg.api unavailable ({_e}); running heuristic-only.")


class EngineAdapter:
    """
    Normalizes the two things that differ between engine builds:

    * `search_begin` signature. The docs give eight positional parameters;
      some builds accept `your_deck=` alone with the rest defaulted. We try
      the full call, then progressively simpler ones, and remember which
      worked so we only pay for the probe once.
    * Return shape. `ApiResult(state, error)` vs a bare `SearchState`.
    """

    def __init__(self):
        self._begin_style = None

    @staticmethod
    def _unwrap(result):
        if result is None:
            return None
        if hasattr(result, "searchId"):
            return result
        if getattr(result, "error", 0):
            return None
        return getattr(result, "state", None)

    def search_begin(self, observation, your_deck, your_prize, opponent_deck,
                     opponent_prize, opponent_hand, opponent_active, manual_coin=False):
        fn = _CG.get("search_begin")
        if fn is None:
            return None
        attempts = [
            ("full", lambda: fn(observation, your_deck, your_prize, opponent_deck,
                                opponent_prize, opponent_hand, opponent_active, manual_coin)),
            ("kw", lambda: fn(observation, your_deck=your_deck, your_prize=your_prize,
                              opponent_deck=opponent_deck, opponent_prize=opponent_prize,
                              opponent_hand=opponent_hand, opponent_active=opponent_active,
                              manual_coin=manual_coin)),
            ("deck_only", lambda: fn(observation, your_deck=your_deck)),
            ("bare", lambda: fn(observation)),
        ]
        if self._begin_style is not None:
            attempts = [a for a in attempts if a[0] == self._begin_style] + \
                       [a for a in attempts if a[0] != self._begin_style]
        for name, call in attempts:
            try:
                state = self._unwrap(call())
                if state is not None:
                    if self._begin_style != name:
                        log_rule_execution(f"  [ENGINE] search_begin style = '{name}'")
                        self._begin_style = name
                    return state
            except TypeError:
                continue
            except Exception:
                continue
        return None

    def search_step(self, search_id, select):
        fn = _CG.get("search_step")
        if fn is None:
            return None
        try:
            return self._unwrap(fn(search_id, list(select)))
        except Exception:
            return None

    def search_release(self, search_id):
        fn = _CG.get("search_release")
        if fn is None or search_id is None:
            return
        try:
            fn(search_id)
        except Exception:
            pass

    def search_end(self):
        fn = _CG.get("search_end")
        if fn is None:
            return
        try:
            fn()
        except Exception:
            pass

    def to_observation_class(self, obs_dict):
        fn = _CG.get("to_observation_class")
        if fn is None:
            return _wrap(obs_dict)
        try:
            return fn(obs_dict)
        except Exception:
            return _wrap(obs_dict)


ENGINE = EngineAdapter()


# ---------------------------------------------------------------------------
# Dict -> attribute shim (only used if to_observation_class is missing)
# ---------------------------------------------------------------------------


class _Wrap:
    """Read-only attribute view over a dict, so heuristics can use getattr."""

    __slots__ = ("_d", "_cache")

    def __init__(self, d):
        object.__setattr__(self, "_d", d)
        object.__setattr__(self, "_cache", {})

    def __getattr__(self, key):
        d = object.__getattribute__(self, "_d")
        if key not in d:
            raise AttributeError(key)
        cache = object.__getattribute__(self, "_cache")
        if key not in cache:
            cache[key] = _wrap(d[key])
        return cache[key]

    def get(self, key, default=None):
        d = object.__getattribute__(self, "_d")
        return _wrap(d[key]) if key in d else default

    def __repr__(self):
        return f"_Wrap({object.__getattribute__(self, '_d')!r})"


def _wrap(v):
    if isinstance(v, dict):
        return _Wrap(v)
    if isinstance(v, list):
        return [_wrap(x) for x in v]
    return v


# ---------------------------------------------------------------------------
# Card index
# ---------------------------------------------------------------------------


def _build_card_index():
    if not _STRATEGY_OK:
        return None
    if _SEARCH_OK:
        try:
            idx = CardIndex.from_card_data(_CG["all_card_data"]())
            log_rule_execution(f"  [CARDS] indexed {len(idx.by_id)} cards from cg.api")
            return idx
        except Exception as e:
            log_rule_execution(f"  [CARDS] all_card_data failed: {e}")
    # CSV fallback, same file the harness ships.
    for name in ["EN_Card_Data.csv", "EN_Card_Data copy.csv",
                 os.path.join("data", "EN_Card_Data.csv")]:
        p = os.path.join(_BASE_DIR, name)
        if not os.path.exists(p):
            continue
        try:
            rows = {}
            with open(p, mode="r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    raw = (row.get("Card ID") or "").strip()
                    if not raw.isdigit():
                        continue
                    cid = int(raw)
                    nm = (row.get("Card Name") or "").strip()
                    rule = (row.get("Rule") or "").lower()
                    stage = (row.get("Stage (Pokémon)/Type (Energy and Trainer)") or "").lower()
                    is_ex = "ex" in rule or "ex" in stage or nm.lower().endswith(" ex")
                    rows[cid] = type("CD", (), {
                        "cardId": cid, "name": nm, "ex": is_ex, "megaEx": "mega" in nm.lower(),
                    })()
            if rows:
                log_rule_execution(f"  [CARDS] indexed {len(rows)} cards from {name}")
                return CardIndex(by_id=rows)
        except Exception as e:
            log_rule_execution(f"  [CARDS] csv parse failed ({name}): {e}")
    log_rule_execution("  [CARDS] no card data available; opponent threats will read as generic")
    return CardIndex()


CARD_INDEX = _build_card_index()
HEURISTICS = Heuristics(CARD_INDEX) if _STRATEGY_OK else None
# >>> dragapult_patch:logger_construction >>>

# --- battle transcript logging (diagnostics only, no effect on play) -------
try:
    from battle_log import BattleLogger
    BATTLE_LOG = BattleLogger(
        card_index=getattr(HEURISTICS, "card_index", None) or CARD_INDEX)
    log_rule_execution(f"  [BATTLE LOG] writing to {BATTLE_LOG.path}")
except Exception as _e:
    class _NullLog:
        path = "(disabled)"
        def observe(self, *a, **k): pass
        def source(self, *a, **k): pass
        def record_result(self, *a, **k): pass
        def flush(self): pass
    BATTLE_LOG = _NullLog()
    log_rule_execution(f"  [BATTLE LOG] disabled: {_e}")
# <<< dragapult_patch:logger_construction <<<



# ---------------------------------------------------------------------------
# Search configuration — tuned for a per-move wall clock, not for offline use
# ---------------------------------------------------------------------------

MOVE_TIME_BUDGET = float(os.environ.get("DRAGAPULT_MOVE_BUDGET", "3.0"))

# The search only overrides the heuristic policy when it actually separates
# the candidates. A search that expanded nothing, or that scores its top two
# moves within this margin, has told us nothing the policy didn't already
# know — and the policy encodes rules the evaluator can't see at one ply
# (Cursed Blast prize math, bench discipline, Boss targeting). Ties go to
# the prior.
SEARCH_TIE_EPSILON = 0.01

SEARCH_CFG = SearchConfig(
    determinizations=4,
    max_branch=8,
    max_nodes=6000,
    max_depth=48,
    time_budget_s=MOVE_TIME_BUDGET / 2.0,
    total_time_budget_s=MOVE_TIME_BUDGET,
    exact_coin=True,
    risk_aversion=0.25,
    mode="auto",
    auto_uct_threshold=14,
    uct_iterations=250,
    seed=None,
) if _STRATEGY_OK else None

SEARCHER = None   # constructed after policy_rank is defined below, so search can use it as its rollout/candidate policy instead of a disconnected generic ranker


# ---------------------------------------------------------------------------
# Plan cache: search once per turn, replay the line
# ---------------------------------------------------------------------------


class _Plan:
    def __init__(self):
        self.moves = []
        self.sigs = []
        self.turn = None
        self.stats = {"searches": 0, "replays": 0, "invalidations": 0, "policy": 0}

    def reset(self, turn):
        if self.moves or self.sigs:
            self.stats["invalidations"] += 1
        self.moves, self.sigs, self.turn = [], [], turn

    def take(self, select_obj):
        """Return the next planned move remapped onto the live option list."""
        if not self.moves:
            return None
        want = self.sigs[0] if self.sigs else None
        options = getattr(select_obj, "option", None) or []
        if want:
            by_sig = {}
            for i, o in enumerate(options):
                by_sig.setdefault(option_signature(o), i)
            remapped = []
            for s in want:
                if s not in by_sig:
                    return None
                remapped.append(by_sig[s])
            self.moves.pop(0)
            self.sigs.pop(0)
            self.stats["replays"] += 1
            return remapped
        move = self.moves.pop(0)
        if self.sigs:
            self.sigs.pop(0)
        if all(0 <= i < len(options) for i in move) and move:
            self.stats["replays"] += 1
            return move
        return None

    def store(self, moves, sigs):
        self.moves = [list(m) for m in moves]
        self.sigs = list(sigs)


PLAN = _Plan()


# ---------------------------------------------------------------------------
# Heuristic policy — used when search is unavailable or out of time
# ---------------------------------------------------------------------------

_CTX_DISCARD = {8, 10, 26, 27, 29, 30}
_CTX_DAMAGE = {13, 14, 15}
_CTX_SETUP = {1, 2}
_CTX_SWITCH_TARGET = {3, 4}   # SWITCH, TO_ACTIVE — which of our own Pokemon takes the active spot
_CTX_SEARCH_RESULT = {5, 7}   # TO_BENCH, TO_HAND — resolving a search/dig effect's hit
_CTX_YESNO_COIN = 46
_CTX_IS_FIRST = 41
_CTX_MULLIGAN = 42
_CTX_ACTIVATE = 43


def _opt(o, key, default=None):
    """Read a field from an option that may be a dataclass, a _Wrap, or a raw dict."""
    if isinstance(o, dict):
        v = o.get(key, default)
    else:
        v = getattr(o, key, default)
    return default if v is None else v


def _resolve_card(view, select_obj, area, index, player_index):
    """Look up the actual card behind an option's (area, index, playerIndex).
    Most option types (PLAY, ATTACH, EVOLVE, ABILITY, CARD/SWITCH/DISCARD/...)
    do NOT carry a populated `cardId` field per the engine's own option docs
    — only a few (ATTACK's attackId, SKILL) do. Everything else has to be
    resolved back through the zone it points at."""
    if area is None or index is None:
        return None
    pidx = player_index if player_index is not None else view.my_index
    try:
        if area == 1:  # DECK — only visible via select.deck
            deck = _opt(select_obj, "deck", None) or []
            return deck[index] if 0 <= index < len(deck) else None
        ps = view.state.players[pidx]
        if area == 2:    # HAND
            zone = ps.hand or []
        elif area == 3:  # DISCARD
            zone = ps.discard or []
        elif area == 4:  # ACTIVE
            zone = ps.active or []
        elif area == 5:  # BENCH
            zone = ps.bench or []
        elif area == 6:  # PRIZE
            zone = ps.prize or []
        elif area == 7:  # STADIUM
            zone = view.state.stadium or []
        elif area == 12:  # LOOKING
            zone = view.state.looking or []
        else:
            return None
        return zone[index] if 0 <= index < len(zone) else None
    except Exception:
        return None


def _resolve_cid(view, select_obj, o, otype):
    """cardId if the engine actually populated it; otherwise resolve it from
    the option's area/index (PLAY implies our own hand, since that field
    isn't even sent for PLAY options)."""
    cid = _opt(o, "cardId", None)
    if cid is not None:
        return cid
    area = _opt(o, "area", None)
    index = _opt(o, "index", None)
    pidx = _opt(o, "playerIndex", None)
    if otype == OptionType.PLAY:
        area = 2
        pidx = view.my_index
    card = _resolve_card(view, select_obj, area, index, pidx)
    return getattr(card, "id", None) if card is not None else None



# >>> dragapult_patch:priority_override_helper >>>

# --- transcript-driven priority fixes -------------------------------------
try:
    from dragapult_priorities import (
        build_attack_table, attack_score, retreat_veto, attach_veto,
        end_turn_score, discard_veto, evolve_score, search_score,
        activate_score, play_score, attach_energy_fit)
    try:
        from cg.api import all_attack as _all_attack
        build_attack_table(_all_attack)
        log_rule_execution("  [PRIORITIES] attack damage table loaded")
    except Exception as _e:
        log_rule_execution(f"  [PRIORITIES] attack table unavailable: {_e}")
    _PRIORITIES_OK = True
except Exception as _e:
    _PRIORITIES_OK = False
    log_rule_execution(f"  [PRIORITIES] disabled: {_e}")


def _priority_override(view, select_obj, options, o, otype):
    """Veto or boost that outranks the tuned weight. None = no opinion."""
    if not _PRIORITIES_OK:
        return None
    try:
        _ctx = _opt(select_obj, "context", None)
        _ctx = getattr(_ctx, "value", _ctx)
        if _ctx in (8, 10):          # DISCARD, TO_DECK_BOTTOM
            return discard_veto(view, _resolve_cid(view, select_obj, o, otype))
        if _ctx == 43:               # ACTIVATE — our own ability prompt
            if otype in (OptionType.YES, OptionType.NO):
                return activate_score(otype == OptionType.YES)
        if _ctx in (7, 1):           # TO_HAND / DECK search target
            return search_score(view, _resolve_cid(view, select_obj, o, otype))
        if otype == OptionType.EVOLVE:
            return evolve_score(view, _resolve_cid(view, select_obj, o, otype),
                                o, _opt)
        if otype == OptionType.PLAY:
            return play_score(view, _resolve_cid(view, select_obj, o, otype))
        if otype == OptionType.ATTACK:
            return attack_score(view, o, _opt)
        if otype == OptionType.RETREAT:
            return retreat_veto(view)
        if otype == OptionType.ATTACH:
            veto = attach_veto(view, o, _opt)
            if veto is not None:
                return veto
            return attach_energy_fit(view, o, _opt)
        if otype == OptionType.END:
            return end_turn_score(options, _opt, OptionType.END, OptionType.NO)
    except Exception:
        return None
    return None
# <<< dragapult_patch:priority_override_helper <<<

def policy_rank(view, select_obj, options):
    """
    Rule-based ordering of option indices, sourced from the decision module.
    Returns indices best-first. This is the fallback when the search can't
    run, and the candidate ordering the search expands first when it can.
    """
    ctx = _opt(select_obj, "context", None)
    ctx_val = getattr(ctx, "value", ctx)
    scored = []

    # Pre-compute per-turn advice once; several branches reuse it.
    try:
        advice = advise_turn(view)
    except Exception:
        advice = None

    for i, o in enumerate(options):
        otype = _opt(o, "type", None)
        otype = getattr(otype, "value", otype)
        cid = _resolve_cid(view, select_obj, o, otype)
        s = 0.30

        try:
            # --- opening decisions -------------------------------------
            if ctx_val == _CTX_IS_FIRST:
                s = W["policy_is_first_yes"] if otype == OptionType.YES else W["policy_is_first_no"]
                _log_once("first_or_second", "  [RULE 1] Going first — first attachment + first evolution.")

            elif ctx_val == _CTX_MULLIGAN:
                keep = should_mulligan_keep(view, [c for c in view.hand_ids])
                want_redraw = not keep.recommended
                s = W["policy_mulligan_match"] if ((otype == OptionType.YES) == want_redraw) else W["policy_mulligan_mismatch"]

            elif ctx_val in _CTX_SETUP:
                # Lead with a 1-prize body; never open a 2-prize liability if
                # anything else is legal.
                if cid in (ID.BUDEW,):
                    s = W["policy_setup_budew"]
                elif cid == ID.DREEPY:
                    s = W["policy_setup_dreepy"]
                elif cid == ID.DUSKULL:
                    s = W["policy_setup_duskull"]
                elif cid in LIABILITY_2_PRIZE:
                    s = W["policy_setup_liability"]
                else:
                    s = W["policy_setup_default"]

            # --- discards: protect our last draw engine first (rule A) --
            elif ctx_val in _CTX_DISCARD:
                s = discard_priority(view, cid, HAND_VALUE)

            # --- damage placement --------------------------------------
            elif ctx_val in _CTX_DAMAGE:
                s = _score_damage_target(view, o, cid)

            # --- who becomes our new active (rules B & C) ---------------
            elif ctx_val in _CTX_SWITCH_TARGET:
                s = _score_switch_target(view, o, cid)

            # --- resolving a search/dig hit: Dreepy first (rule D) ------
            elif ctx_val in _CTX_SEARCH_RESULT:
                s = search_target_score(view, cid)

            # --- main actions ------------------------------------------
            elif otype == OptionType.ABILITY:
                s = _score_ability(view, cid, advice)
            elif otype == OptionType.EVOLVE:
                s = W["policy_evolve"]
            elif otype == OptionType.ATTACH:
                s = _score_attach(view, o)
            elif otype == OptionType.PLAY:
                s = _score_play(view, cid, advice)
            elif otype == OptionType.ATTACK:
                s = W["policy_attack_ready"] if phantom_dive_available(view) else W["policy_attack_not_ready"]
            elif otype == OptionType.RETREAT:
                try:
                    s = retreat_score(view)
                except Exception:
                    s = W["retreat_default"]
            elif otype == OptionType.END:
                s = W["policy_end"]
            elif otype in (OptionType.YES, OptionType.NO):
                s = W["policy_yes"] if otype == OptionType.YES else W["policy_no"]
            else:
                s = W["policy_default"]
        except Exception as _e:
            _log_once(f"policy_exc_{ctx_val}_{otype}", f"  [POLICY OPTION EXCEPTION] ctx={ctx_val} otype={otype} cid={cid}: {type(_e).__name__}: {_e}")
            s = W["policy_exception_fallback"]

        # >>> dragapult_patch:priority_overrides__attack___retreat___attach___end >>>
        ov = _priority_override(view, select_obj, options, o, otype)
        if ov is not None:
            s = ov
        # <<< dragapult_patch:priority_overrides__attack___retreat___attach___end <<<
        scored.append((s, i))

    scored.sort(key=lambda t: (-t[0], t[1]))
    # >>> dragapult_patch:drop_vetoed_options_from_the_ranking >>>
    _legal_ranked = [i for _s, i in scored if _s > -0.5]
    if _legal_ranked:
        return _legal_ranked
    # <<< dragapult_patch:drop_vetoed_options_from_the_ranking <<<
    return [i for _, i in scored]


def _score_ability(view, cid, advice):
    """Cursed Blast is gated; everything else is cheap value."""
    if cid == ID.DUSCLOPS:
        d = advice.dusclops if advice else should_cursed_blast(view, use_dusknoir=False)
        log_rule_execution(f"  [RULE 5] {d}")
        return W["ability_dusclops_go"] if d.recommended else W["ability_dusclops_hold"]
    if cid == ID.DUSKNOIR:
        d = advice.dusknoir if advice else should_cursed_blast(view, use_dusknoir=True)
        log_rule_execution(f"  [RULE 5] {d}")
        return W["ability_dusknoir_go"] if d.recommended else W["ability_dusknoir_hold"]
    if cid == ID.DRAKLOAK:
        return W["ability_drakloak_recon"]            # Recon Directive: free card selection, always
    if cid == ID.MUNKIDORI:
        return W["ability_munkidori_online"] if munkidori_online(view) else W["ability_munkidori_offline"]
    if cid == ID.FEZANDIPITI_EX:
        return W["ability_fezandipiti"]
    return W["ability_default"]


def _score_attach(view, o):
    """Rank attachment targets: Dragapult line first, then the single Darkness."""
    try:
        ranked = energy_attach_target(view)
    except Exception:
        return W["attach_no_target"]
    in_area = _opt(o, "inPlayArea", None)
    in_idx = _opt(o, "inPlayIndex", None)
    board = []
    if in_area == 4:
        board = [p for p in (getattr(view.me, "active", []) or []) if p is not None]
    elif in_area == 5:
        board = view.my_bench
    target = board[in_idx] if (in_idx is not None and 0 <= in_idx < len(board)) else None
    if target is None:
        return W["attach_no_target"]
    for p, score, why in ranked:
        if p is target:
            return W["attach_blend_base"] + W["attach_blend_mult"] * score
    return W["attach_no_match"]


def _score_switch_target(view, o, cid):
    """Rank a candidate to become our new Active Pokemon (rules B & C)."""
    player_idx = _opt(o, "playerIndex", None)
    if player_idx is not None and player_idx != view.my_index:
        return W["switch_no_target"]
    area = _opt(o, "area", None)
    idx = _opt(o, "index", None)
    board = view.my_bench if area == 5 else ([view.my_active] if view.my_active else [])
    pokemon = board[idx] if (idx is not None and 0 <= idx < len(board)) else None
    if pokemon is None:
        return W["switch_no_target"]
    try:
        return switch_target_score(view, cid, pokemon)
    except Exception:
        return W["switch_no_target"]


def _score_play(view, cid, advice):
    if cid is None:
        return W["play_none"]

    # Rule 9: never take the last bench slot with a non-line body.
    if cid in (ID.DREEPY, ID.DUSKULL, ID.BUDEW, ID.MUNKIDORI, ID.MEOWTH_EX,
               ID.FEZANDIPITI_EX, ID.LATIAS_EX, ID.BLOODMOON_URSALUNA_EX):
        try:
            gate = should_bench(view, cid)
        except Exception:
            gate = None
        if gate is not None:
            if not gate.recommended:
                log_rule_execution(f"  [RULE 4/8/9] {gate}")
                return W["play_gate_deny"]
            return W["play_gate_blend_base"] + W["play_gate_blend_mult"] * gate.score

    if cid == ID.LILLIES_DETERMINATION:
        d = advice.lillie if advice else lillie_or_search(view)
        log_rule_execution(f"  [RULE 7] {d}")
        return W["play_lillie_go"] if d.recommended else W["play_lillie_hold"]

    if cid in SEARCH_ITEMS:
        return W["play_search_items"]     # Poffin / Pad / Ultra Ball: dig early
    if cid == ID.RARE_CANDY:
        return W["play_rare_candy_ready"] if view.count_in_play([ID.DUSKULL, ID.DREEPY]) else W["play_rare_candy_not_ready"]
    if cid == ID.BOSSES_ORDERS:
        return _score_boss(view)
    if cid == ID.HILDA:
        return W["play_hilda"]
    if cid == ID.NIGHT_STRETCHER:
        return W["play_night_stretcher"]
    if cid == ID.POKEGEAR_3:
        return W["play_pokegear_open"] if not view.count_in_hand([ID.LILLIES_DETERMINATION]) else W["play_pokegear_redundant"]
    if cid == ID.ENERGY_SEARCH:
        return W["play_energy_search"]
    if cid == ID.CRUSHING_HAMMER:
        return W["play_crushing_hammer"]
    return W["play_default"]


def _score_boss(view):
    """
    Rule 5 support: Boss's Orders is a premium resource. Spend it to drag out
    a blocker we can't otherwise reach, or to convert a bench KO into a prize.
    """
    try:
        targets = rank_targets(view)
    except Exception:
        return W["boss_fallback"]
    for t in targets:
        if t.is_bench and t.threat_value >= 0.75:
            log_rule_execution(f"  [RULE 5] Boss's Orders — dragging {t.name} (severity {t.threat_value:.2f}).")
            return W["boss_bench_threat"]
    for t in targets:
        if t.is_bench and t.prizes >= 2 and t.counters_to_ko <= 20:
            return W["boss_bench_two_prize"]
    return W["boss_default"]


def _score_damage_target(view, o, cid):
    """
    Rule 6: counters go where they take prizes or remove blockers, and never
    where the target survives out of next turn's range.
    """
    owner = _opt(o, "playerIndex", None)
    if owner is not None and owner == view.my_index:
        return W["damage_own_board"]      # never place on our own board
    try:
        for t in rank_targets(view):
            tid = getattr(t.pokemon, "id", None)
            if tid == cid:
                return W["damage_blend_base"] + W["damage_blend_mult"] * t.efficiency
    except Exception:
        pass
    return W["damage_default"]


# Built here (not up with SEARCH_CFG) so search can drive its root-candidate
# ranking and rollout continuation with the real heuristic policy instead of
# dragapult_search's own generic, deck-blind fallback ranker.
def _quiet_policy_rank(view, select_obj, options):
    """Same ranking search uses to drive candidate selection and rollout,
    but silenced — search calls this on hundreds of simulated hypothetical
    states per real decision, and log_rule_execution's disk write on every
    one of them was both burying real game history under fictional rollout
    noise and eating into the per-move search time budget."""
    _SUPPRESS_LOG[0] = True
    try:
        return policy_rank(view, select_obj, options)
    finally:
        _SUPPRESS_LOG[0] = False


SEARCHER = TurnSearch(ENGINE, HEURISTICS, SEARCH_CFG, policy_fn=_quiet_policy_rank) if (_STRATEGY_OK and _SEARCH_OK) else None


_LOGGED_ONCE = set()


def _log_once(key, msg):
    if key not in _LOGGED_ONCE:
        _LOGGED_ONCE.add(key)
        log_rule_execution(msg)


# ---------------------------------------------------------------------------
# Fallback logging + action sanitizing (never returns an illegal selection)
# ---------------------------------------------------------------------------


def _log_fallback_state(obs_dict, reason=""):
    try:
        current = obs_dict.get("current", {}) if isinstance(obs_dict, dict) else {}
        my_idx = current.get("yourIndex", 0) if isinstance(current, dict) else 0
        players = current.get("players", []) if isinstance(current, dict) else []
        my_p = players[my_idx] if (isinstance(players, list) and len(players) > my_idx
                                   and isinstance(players[my_idx], dict)) else {}
        active_list = my_p.get("active", []) or []
        active = active_list[0] if active_list and isinstance(active_list[0], dict) else {}
        board = (f"Active ID={active.get('id')}, HP={active.get('hp', 0)}, "
                 f"BenchCount={len(my_p.get('bench', []) or [])}, "
                 f"HandCount={my_p.get('handCount', len(my_p.get('hand', []) or []))}")
        log_rule_execution(f"  [FALLBACK LOGGED] Reason: {reason} | {board}")
    except Exception as e:
        log_rule_execution(f"  [FALLBACK LOGGING EXCEPTION] {e}")


def sanitize_action(chosen_indices, select_data, obs_dict=None):
    options = select_data.get("option", []) if isinstance(select_data, dict) else []
    n_opts = len(options)
    if n_opts == 0:
        if obs_dict:
            _log_fallback_state(obs_dict, reason="No options available in select_data")
        return [0]

    max_count = select_data.get("maxCount", 1) if isinstance(select_data, dict) else 1
    min_count = select_data.get("minCount", 1) if isinstance(select_data, dict) else 1
    max_count = max_count if isinstance(max_count, int) and max_count > 0 else 1
    min_count = min_count if isinstance(min_count, int) and min_count >= 0 else 1

    unique = []
    for idx in (chosen_indices or []):
        if isinstance(idx, int) and 0 <= idx < n_opts and idx not in unique:
            unique.append(idx)

    if not unique:
        if obs_dict:
            _log_fallback_state(obs_dict, reason="Fallback [0] — no valid chosen_indices")
        unique = [0]

    if len(unique) < min_count:
        for i in range(n_opts):
            if i not in unique:
                unique.append(i)
                if len(unique) >= min_count:
                    break

    target_count = min(max_count, max(min_count, len(unique)))
    return unique[:target_count]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------



# >>> dragapult_patch:sanitize_action_wrapper >>>

# --- record every returned selection --------------------------------------
_sanitize_action_impl = sanitize_action


def sanitize_action(chosen_indices, select_data, obs_dict=None):
    result = _sanitize_action_impl(chosen_indices, select_data, obs_dict)
    try:
        BATTLE_LOG.observe(obs_dict, result)
    except Exception:
        pass
    return result
# <<< dragapult_patch:sanitize_action_wrapper <<<
def agent(obs_dict: dict) -> list[int]:
    select_data = obs_dict.get("select") if isinstance(obs_dict, dict) else None

    # Initial deck submission.
    if select_data is None:
        if isinstance(obs_dict, dict) and obs_dict.get("step", 0) == 0:
            log_rule_execution("  [SETUP] submitting 60-card deck list")
            return my_deck
        return []

    options = select_data.get("option") if isinstance(select_data, dict) else None
    if not options:
        return [0]

    current = obs_dict.get("current")
    if current is None or not _STRATEGY_OK:
        return sanitize_action([0], select_data, obs_dict)

    started = time.time()
    try:
        obs = ENGINE.to_observation_class(obs_dict)
        state = getattr(obs, "current", None)
        select_obj = getattr(obs, "select", None)
        if state is None or select_obj is None:
            return sanitize_action([0], select_data, obs_dict)

        seat = getattr(state, "yourIndex", 0)
        view = HEURISTICS.view(state, seat=seat)
        turn = getattr(state, "turn", 0)

        # --- turn boundary: drop any stale plan -------------------------
        if PLAN.turn != turn:
            PLAN.reset(turn)
            try:
                ev = HEURISTICS.evaluate(state, seat=seat)
                log_rule_execution(
                    f"\n[Turn {turn}] score={ev.score:.3f} phase={ev.phase} "
                    f"schedule={ev.schedule.adherence:.0%} missed={','.join(ev.schedule.missed) or '-'}"
                )
                for k, gap in ev.top_gaps(3):
                    log_rule_execution(f"  [GAP] {k} = {ev.features[k]:.2f} (cost {gap:.2f})")
                for v in ev.violations:
                    log_rule_execution(f"  [VIOLATION] {v.key}: {v.detail}")
            except Exception as e:
                log_rule_execution(f"  [EVAL EXCEPTION] {e}")

        def _describe(indices):
            parts = []
            for i in indices:
                if 0 <= i < len(options):
                    o = options[i]
                    ot = _opt(o, "type", None)
                    ot = getattr(ot, "value", ot)
                    resolved_cid = _resolve_cid(view, select_obj, o, ot)
                    parts.append(f"i={i} type={ot} card={resolved_cid} atk={_opt(o,'attackId')} area={_opt(o,'area')}/{_opt(o,'index')} inplay={_opt(o,'inPlayArea')}/{_opt(o,'inPlayIndex')}")
            ctxv = getattr(_opt(select_obj, 'context', None), 'value', _opt(select_obj, 'context', None))
            return f"ctx={ctxv} " + " | ".join(parts)

        # --- 1. replay a cached plan if it still fits -------------------
        replay = PLAN.take(select_obj)
        if replay:
            log_rule_execution(f"  [PLAN REPLAY] {replay} :: {_describe(replay)}")
            return sanitize_action(replay, select_data, obs_dict)

        # --- 2. heuristic candidate ordering ----------------------------
        # Rank against the converted options, not the raw dicts: _opt handles
        # both, but the converted list is what the search also sees, so the
        # two orderings stay consistent.
        ranked_options = getattr(select_obj, "option", None) or options
        ranked = policy_rank(view, select_obj, ranked_options)

        # --- 3. search, if the engine exposes it and time remains -------
        if SEARCHER is not None and (time.time() - started) < MOVE_TIME_BUDGET * 0.5:
            try:
                res = SEARCHER.search(obs, opponent_prior=None)
                ranked_moves = sorted(res.moves, key=lambda m: -m.mean)
                separation = (ranked_moves[0].mean - ranked_moves[1].mean
                              if len(ranked_moves) > 1 else float("inf"))
                usable = bool(res.best_move) and all(0 <= i < len(options) for i in res.best_move)
                trusted = usable and res.nodes > 0 and separation >= SEARCH_TIE_EPSILON
                # >>> dragapult_patch:search_must_clear_its_own_noise_floor >>>
                _noise_floor = max(m.spread for m in ranked_moves[:2]) if ranked_moves else 0.0
                trusted = trusted and separation >= _noise_floor
                if os.environ.get('DRAGAPULT_DISABLE_SEARCH'):
                    trusted = False
                # <<< dragapult_patch:search_must_clear_its_own_noise_floor <<<

                log_rule_execution(
                    f"  [SEARCH] {res.nodes} nodes / {res.worlds} worlds / {res.elapsed:.2f}s "
                    f"-> {res.best_move} value={res.value:.3f} sep={separation:.3f}"
                    f"{' TRUNCATED' if res.truncated else ''}"
                )
                for m in ranked_moves[:3]:
                    log_rule_execution(
                        f"    [CANDIDATE] {m.label} mean={m.mean:.3f} "
                        f"worst={m.worst:.3f} spread={m.spread:.3f}"
                    )
                    if m.spread > 0.25:
                        log_rule_execution(
                            f"    [FRAGILE] {m.label} depends heavily on the sampled world."
                        )

                if trusted:
                    log_rule_execution(f"  [CHOSE-SEARCH] {_describe(res.best_move)}")
                    PLAN.store(res.best_line[1:], res.best_line_sigs[1:])
                    PLAN.turn = turn
                    PLAN.stats["searches"] += 1
                    # >>> dragapult_patch:search_source_tag >>>
                    BATTLE_LOG.source("search", f"sep={separation:.3f}")
                    # <<< dragapult_patch:search_source_tag <<<
                    return sanitize_action(res.best_move, select_data, obs_dict)

                log_rule_execution(
                    "  [SEARCH] result not separating (nodes={n}, sep={s:.3f}); "
                    "deferring to heuristic policy".format(n=res.nodes, s=separation)
                )
            except Exception as e:
                log_rule_execution(f"  [SEARCH EXCEPTION] {e}")

        # --- 4. policy fallback -----------------------------------------
        PLAN.stats["policy"] += 1
        # >>> dragapult_patch:policy_source_tag >>>
        BATTLE_LOG.source("policy")
        # <<< dragapult_patch:policy_source_tag <<<
        chosen = _fill_multi(ranked, select_data)
        log_rule_execution(f"  [POLICY] chose {chosen} from {len(options)} options :: {_describe(chosen)}")
        return sanitize_action(chosen, select_data, obs_dict)

    except Exception as e:
        log_rule_execution(f"  [AGENT EXCEPTION] {e}\n{traceback.format_exc(limit=3)}")
        return sanitize_action([0], select_data, obs_dict)


def _fill_multi(ranked, select_data):
    """Take as many of the top-ranked options as minCount/maxCount demand."""
    min_count = select_data.get("minCount", 1) if isinstance(select_data, dict) else 1
    min_count = min_count if isinstance(min_count, int) and min_count > 0 else 1
    return ranked[:max(1, min_count)] if ranked else [0]
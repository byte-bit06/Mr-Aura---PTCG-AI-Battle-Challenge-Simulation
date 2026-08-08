"""
dragapult_search.py — single-ply Monte Carlo look-ahead over cg.api.

Scope, honestly stated: this is NOT a full multi-turn UCT/expectimax tree.
It takes the top `max_branch` candidate moves at the current decision point,
determinizes the unknown cards (opponent hand/deck, our own deck order)
`determinizations` times per candidate, plays each one out through the
engine (`search_begin`/`search_step`) with a cheap greedy rollout policy to
the end of the turn (or `max_depth` steps, whichever comes first), and
scores the resulting board with `Heuristics.evaluate`. The candidate with
the best mean score wins, but only if it actually separates from the
runner-up — main.py already discards ties/low-node results and falls back
to the heuristic policy, so failures here are always safe, never fatal.

Every external call (search_begin/search_step/search_release) is wrapped so
a bad prediction or an engine quirk degrades to "no evidence" (nodes=0)
rather than raising into the agent.
"""

import random

from cg.api import OptionType, SelectContext, SelectType

from dragapult_heuristics import ID, LIABILITY_2_PRIZE, DECK_ID_LIST


# ---------------------------------------------------------------------------
# Config / result shapes
# ---------------------------------------------------------------------------

class SearchConfig:
    def __init__(self, determinizations=4, max_branch=8, max_nodes=6000,
                 max_depth=48, time_budget_s=1.5, total_time_budget_s=3.0,
                 exact_coin=True, risk_aversion=0.25, mode="auto",
                 auto_uct_threshold=14, uct_iterations=250, seed=None):
        self.determinizations = determinizations
        self.max_branch = max_branch
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self.time_budget_s = time_budget_s
        self.total_time_budget_s = total_time_budget_s
        self.exact_coin = exact_coin
        self.risk_aversion = risk_aversion
        self.mode = mode
        self.auto_uct_threshold = auto_uct_threshold
        self.uct_iterations = uct_iterations
        self.seed = seed


class MoveStat:
    __slots__ = ("move", "label", "mean", "worst", "spread")

    def __init__(self, move, label, samples):
        self.move = move
        self.label = label
        self.mean = sum(samples) / len(samples) if samples else 0.0
        self.worst = min(samples) if samples else 0.0
        self.spread = (max(samples) - min(samples)) if samples else 0.0


class SearchResult:
    __slots__ = ("moves", "best_move", "best_line", "best_line_sigs",
                 "nodes", "worlds", "elapsed", "value", "truncated")

    def __init__(self):
        self.moves = []
        self.best_move = []
        self.best_line = [[]]
        self.best_line_sigs = [[]]
        self.nodes = 0
        self.worlds = 0
        self.elapsed = 0.0
        self.value = 0.0
        self.truncated = False


# ---------------------------------------------------------------------------
# Option / move signatures — used by main.py's plan-cache replay.
# ---------------------------------------------------------------------------

def _f(o, key):
    return o.get(key) if isinstance(o, dict) else getattr(o, key, None)


def option_signature(o):
    ot = _f(o, "type")
    return (
        getattr(ot, "value", ot),
        _f(o, "area"), _f(o, "index"), _f(o, "playerIndex"),
        _f(o, "inPlayArea"), _f(o, "inPlayIndex"),
        _f(o, "cardId"), _f(o, "attackId"),
        _f(o, "toolIndex"), _f(o, "energyIndex"),
        _f(o, "specialConditionType"),
    )


def move_signature(move):
    return tuple(move)


def enumerate_moves(select_obj, ranked_indices, max_branch):
    """Legal candidate moves from a ranked option ordering, capped at
    max_branch. Multi-select contexts (minCount>1) take the top-ranked
    block as a single combined move rather than exploring combinations —
    that keeps branching tractable; main.py's heuristic policy already
    handles the general multi-select case well on its own."""
    options = getattr(select_obj, "option", None) or []
    min_count = getattr(select_obj, "minCount", 1) or 0
    max_count = getattr(select_obj, "maxCount", 1) or 1
    n = max(1, min_count)

    if n <= 1:
        moves = [[i] for i in ranked_indices[:max_branch]]
    else:
        block = ranked_indices[:max(n, min(max_count, len(ranked_indices)))]
        moves = [block] if block else [[]]
    return moves or [[0] if options else []]


# ---------------------------------------------------------------------------
# Rollout policy — cheap, self-contained, only needs to be "reasonable"
# since only the root branch choice is actually being compared.
# ---------------------------------------------------------------------------

def _rollout_rank(options):
    scored = []
    for i, o in enumerate(options):
        ot = _f(o, "type")
        ot = getattr(ot, "value", ot)
        cid = _f(o, "cardId")
        if ot == OptionType.ATTACK:
            s = 0.95
        elif ot == OptionType.EVOLVE:
            s = 0.85
        elif ot == OptionType.ABILITY:
            s = 0.7
        elif ot == OptionType.ATTACH:
            s = 0.6
        elif ot == OptionType.PLAY:
            s = 0.55 if cid not in LIABILITY_2_PRIZE else 0.3
        elif ot == OptionType.RETREAT:
            s = 0.15
        elif ot == OptionType.END:
            s = 0.05
        elif ot == OptionType.YES:
            s = 0.55
        elif ot == OptionType.NO:
            s = 0.45
        else:
            s = 0.4
        scored.append((s, i))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [i for _, i in scored]


# ---------------------------------------------------------------------------
# Deck prediction — rough, structurally-valid guesses for search_begin.
# Wrong guesses just add sampling noise; they can't corrupt real game state.
# ---------------------------------------------------------------------------

def _basic_pokemon_id(card_index):
    for cid, cd in getattr(card_index, "by_id", {}).items():
        if getattr(cd, "basic", False):
            return cid
    return ID.DREEPY


def _predict_deck(known_remaining_ids, count, filler_id, rng):
    pool = list(known_remaining_ids)
    while len(pool) < count:
        pool.append(filler_id)
    rng.shuffle(pool)
    return pool[:count]


def _unseen_pool(deck_id_list, visible_ids):
    pool = list(deck_id_list)
    for cid in visible_ids:
        if cid in pool:
            pool.remove(cid)
    return pool


class TurnSearch:
    def __init__(self, engine, heuristics, cfg, policy_fn=None):
        """
        policy_fn(view, select_obj, options) -> ranked option indices,
        best-first. Optional, but without it the search falls back to the
        generic `_rollout_rank` below for both root-candidate selection and
        rollout continuation — which knows nothing about this deck's actual
        game plan (Dreepy priority, Budew item lock, Cursed Blast math...).
        A search built on that alone will happily "trust" and lock in moves
        that are actively worse than what the real heuristic policy would
        have picked, purely because they separate from noise. Wire the real
        `policy_rank` in here so search refines good candidates instead of
        overriding them with a blind one.
        """
        self.engine = engine
        self.heuristics = heuristics
        self.cfg = cfg
        self.policy_fn = policy_fn

    def _rank(self, view, select_obj, options):
        if self.policy_fn is not None:
            try:
                ranked = self.policy_fn(view, select_obj, options)
                if ranked:
                    return ranked
            except Exception:
                pass
        return _rollout_rank(options)

    # -- public API ------------------------------------------------------
    def search(self, obs, opponent_prior=None):
        import time
        started = time.time()
        res = SearchResult()
        rng = random.Random(self.cfg.seed)

        try:
            select = obs.select
            state = obs.current
            options = list(getattr(select, "option", None) or [])
            if not options or state is None:
                return res

            seat = getattr(state, "yourIndex", 0)
            view = self.heuristics.view(state, seat=seat)
            card_index = self.heuristics.card_index

            ranked = self._rank(view, select, options)
            candidates = enumerate_moves(select, ranked, self.cfg.max_branch)
            if not candidates:
                return res

            my_state = state.players[seat]
            opp_state = state.players[1 - seat]

            my_known = [c.id for c in (my_state.hand or [])]
            for c in (my_state.discard or []):
                my_known.append(c.id)
            for p in view.my_board:
                if p:
                    my_known.append(p.id)
            my_unseen = _unseen_pool(DECK_ID_LIST, my_known)

            opp_visible = [c.id for c in (opp_state.discard or [])]
            for p in view.opp_board:
                if p:
                    opp_visible.append(p.id)
            filler = _basic_pokemon_id(card_index)

            total_nodes = 0
            worlds = 0
            for move in candidates:
                if not move:
                    continue
                samples = []
                for _ in range(max(1, self.cfg.determinizations)):
                    if (time.time() - started) > self.cfg.total_time_budget_s:
                        res.truncated = True
                        break
                    score = self._simulate_one(
                        obs, move, seat, view, card_index, rng,
                        my_unseen, my_state, opp_state, opp_visible, filler,
                    )
                    if score is not None:
                        samples.append(score)
                        total_nodes += 1
                        worlds += 1
                if samples:
                    label = f"move={move}"
                    res.moves.append(MoveStat(move, label, samples))

            res.nodes = total_nodes
            res.worlds = worlds
            res.elapsed = time.time() - started

            if res.moves:
                best = max(res.moves, key=lambda m: m.mean)
                res.best_move = best.move
                res.best_line = [best.move]
                res.best_line_sigs = [[option_signature(options[i]) for i in best.move if 0 <= i < len(options)]]
                res.value = best.mean

            return res
        except Exception:
            return res
        finally:
            try:
                self.engine.search_end()
            except Exception:
                pass

    # -- one determinization: begin, apply root move, short rollout ------
    def _simulate_one(self, obs, move, seat, view, card_index, rng,
                       my_unseen, my_state, opp_state, opp_visible, filler):
        search_id = None
        try:
            your_deck = _predict_deck(my_unseen, my_state.deckCount, filler, rng)
            your_prize = _predict_deck(my_unseen, len(my_state.prize or []), filler, rng)
            opponent_deck = _predict_deck(opp_visible, opp_state.deckCount, filler, rng)
            opponent_prize = _predict_deck(opp_visible, len(opp_state.prize or []), filler, rng)
            opponent_hand = _predict_deck(opp_visible, opp_state.handCount, filler, rng)
            opp_active = opp_state.active or []
            opponent_active = [] if (opp_active and opp_active[0] is not None) else [filler]

            search_state = self.engine.search_begin(
                obs, your_deck, your_prize, opponent_deck,
                opponent_prize, opponent_hand, opponent_active,
            )
            if search_state is None:
                return None
            search_id = getattr(search_state, "searchId", None)

            cur = self._advance(search_state, move)
            if cur is None:
                return None

            start_turn = getattr(view.state, "turn", 0)
            final_state = getattr(getattr(cur, "observation", cur), "current", None)

            for _ in range(self.cfg.max_depth):
                observation = getattr(cur, "observation", cur)
                sel = getattr(observation, "select", None)
                st = getattr(observation, "current", None)
                if st is not None:
                    final_state = st
                if sel is None or st is None:
                    break
                if getattr(st, "turn", 0) != start_turn:
                    break
                opts = list(getattr(sel, "option", None) or [])
                if not opts:
                    break
                ended = any(getattr(o, "type", None) == OptionType.END for o in opts)
                step_view = self.heuristics.view(st, seat=seat)
                pick = self._rank(step_view, sel, opts)[:1]
                cur = self._advance(cur, pick)
                if cur is None:
                    break
                observation = getattr(cur, "observation", cur)
                st2 = getattr(observation, "current", None)
                if st2 is not None:
                    final_state = st2
                if ended:
                    break

            if final_state is None:
                return None

            ev = self.heuristics.evaluate(final_state, seat=seat)
            return ev.score
        except Exception:
            return None
        finally:
            if search_id is not None:
                try:
                    self.engine.search_release(search_id)
                except Exception:
                    pass

    def _advance(self, search_state, indices):
        try:
            return self.engine.search_step(search_state.searchId, indices)
        except Exception:
            return None

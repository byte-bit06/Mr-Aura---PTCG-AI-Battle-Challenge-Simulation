"""
battle_log.py \u2014 human-readable battle transcripts for diagnosis.

The rule-execution log answers "what did the scorer think". This answers
"what actually happened", in card names, small enough to paste into a chat.

Output (default `battle_log.txt`, next to this file):

    \u2550\u2550 GAME 2 \u2550\u2550  seat 0 \u00b7 going first
    \u2500\u2500 my turn 3 (engine turn 5) \u2500\u2500
      hand  Dreepy, Rare Candy, Fire Energy, Lillie's Determination
      me    ACT Budew 70/70 e0 \u00b7 BENCH Drakloak 100/100 e1, Duskull 60/60 e0
            prizes 6 \u00b7 deck 31
      opp   ACT Charizard ex 330/330 e2 \u00b7 BENCH Pidgey 60/60 e0
            prizes 6 \u00b7 hand 4
      \u00b7 EVOLVE Drakloak                                    [policy]
      \u00b7 ABILITY Drakloak (Recon Directive)                 [search sep=0.04]
      \u00b7 RETREAT Budew  \u2192  paid 1 energy                    [policy]  \u26a0 PAID RETREAT
      \u00b7 ATTACH Fire Energy \u2192 Dragapult ex (active)         [policy]
      \u00b7 ATTACK Phantom Dive                                [search sep=0.12]
      \u00b7 DAMAGE \u00d76 \u2192 Pidgey                                 [policy]
      turn: attached 1 \u00b7 discarded 1 \u00b7 net 0 \u00b7 energy left in hand 0

    \u2500\u2500 RESULT: LOSS at engine turn 14 \u2500\u2500
      attach/turn 0.71 \u00b7 lost to retreat 3 \u00b7 retreats 3 \u00b7 attacks 2 \u00b7 dives 1
      \u26a0 2 turns ended with energy in hand and no attachment made

Controls (environment variables):
    DRAGAPULT_BATTLE_LOG    output path (default battle_log.txt beside this file)
    DRAGAPULT_LOG_GAMES     how many recent games to keep (default 3, 0 = all)
    DRAGAPULT_LOG_MODE      "full" (every action) or "summary" (per-turn totals
                            and the result block only). Default "full".

Standalone analysis of an existing transcript:
    python3 battle_log.py battle_log.txt
"""

import os
import sys
import atexit
from collections import Counter

# --- option / context codes (mirrored so this file imports standalone) -----

T_NUMBER, T_YES, T_NO, T_CARD = 0, 1, 2, 3
T_TOOL, T_ENERGY_CARD, T_ENERGY = 4, 5, 6
T_PLAY, T_ATTACH, T_EVOLVE, T_ABILITY = 7, 8, 9, 10
T_DISCARD, T_RETREAT, T_ATTACK, T_END = 11, 12, 13, 14

CTX = {
    0: "MAIN", 1: "SETUP_ACTIVE", 2: "SETUP_BENCH", 3: "SWITCH", 4: "TO_ACTIVE",
    5: "TO_BENCH", 6: "TO_FIELD", 7: "TO_HAND", 8: "DISCARD", 9: "TO_DECK",
    10: "TO_DECK_BOTTOM", 13: "DAMAGE_COUNTER", 14: "DAMAGE_ANY", 15: "DAMAGE",
    16: "REMOVE_DAMAGE", 17: "HEAL", 18: "EVOLVES_FROM", 19: "EVOLVES_TO",
    21: "ATTACH_FROM", 22: "ATTACH_TO", 24: "LOOK", 25: "EFFECT_TARGET",
    26: "DISCARD_ENERGY_CARD", 30: "DISCARD_ENERGY", 35: "ATTACK", 37: "EVOLVE",
    38: "DRAW_COUNT", 39: "DAMAGE_COUNT", 41: "IS_FIRST", 42: "MULLIGAN",
    43: "ACTIVATE", 46: "COIN", 47: "CONDITION",
}

TYPE_NAME = {
    T_NUMBER: "NUMBER", T_YES: "YES", T_NO: "NO", T_CARD: "PICK",
    T_TOOL: "TOOL", T_ENERGY_CARD: "ENERGY-CARD", T_ENERGY: "ENERGY",
    T_PLAY: "PLAY", T_ATTACH: "ATTACH", T_EVOLVE: "EVOLVE",
    T_ABILITY: "ABILITY", T_DISCARD: "DISCARD", T_RETREAT: "RETREAT",
    T_ATTACK: "ATTACK", T_END: "END",
}

PHANTOM_DIVE_ATTACK_ID = 154   # seen in the transcripts: 6 counters placed
DRAGAPULT_ID = 121
DRAKLOAK_ID = 120
DREEPY_ID = 119

ENERGY_NAME = {1: "{G}", 2: "{R}", 3: "{W}", 4: "{L}", 5: "{P}", 6: "{F}",
               7: "{D}", 8: "{M}", 9: "{N}", 10: "{RAINBOW}", 0: "{C}"}


def _f(o, key, default=None):
    if isinstance(o, dict):
        v = o.get(key, default)
    else:
        v = getattr(o, key, default)
    return default if v is None else v


def _val(x):
    return getattr(x, "value", x)


class BattleLogger:
    def __init__(self, card_index=None, path=None, keep_games=None, mode=None):
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = "."
        self.path = path or os.environ.get(
            "DRAGAPULT_BATTLE_LOG", os.path.join(base, "battle_log.txt"))
        self.keep = int(os.environ.get("DRAGAPULT_LOG_GAMES", "3")
                        if keep_games is None else keep_games)
        self.mode = (mode or os.environ.get("DRAGAPULT_LOG_MODE", "full")).lower()
        self.card_index = card_index

        self.games = []        # list[list[str]] \u2014 rendered game blocks
        self.totals = Counter()
        self.game_count = 0

        self._lines = []
        self._turn_lines = []
        self._cur = None       # per-game counters
        self._turn = None      # per-turn counters
        self._seat = 0
        self._engine_turn = None
        self._my_turn_no = 0
        self._started = False
        self._next_source = ("policy", "")
        # Log full option lists on MAIN prompts up to this engine turn, so we
        # can tell "rejected the play" apart from "the play was never legal".
        self._opt_log_until = int(os.environ.get("DRAGAPULT_LOG_OPTIONS_UNTIL", "6"))
        atexit.register(self._at_exit)

    def _at_exit(self):
        """Close whatever game was still in progress, then write."""
        try:
            if self._started:
                self.end_game()
            else:
                self.flush()
        except Exception:
            pass

    # -- naming ---------------------------------------------------------

    def name(self, cid):
        if cid is None:
            return "?"
        if self.card_index is not None:
            try:
                n = self.card_index.name(cid)
                if n:
                    return n.title() if n.islower() else n
            except Exception:
                pass
        cd = self._card(cid)
        n = getattr(cd, "name", None)
        if n:
            return n
        return f"card:{cid}"

    # Zone codes used by option.area (same mapping main.py resolves against).
    _AREA_DECK, _AREA_HAND, _AREA_DISCARD = 1, 2, 3
    _AREA_ACTIVE, _AREA_BENCH, _AREA_PRIZE = 4, 5, 6
    _AREA_STADIUM, _AREA_LOOKING = 7, 12

    def _resolve_cid(self, view, select_data, o, otype):
        """
        Most option types do not carry a populated cardId \u2014 the engine only
        fills it for a few. Everything else has to be resolved back through
        the (area, index, playerIndex) it points at, or the transcript is
        just a wall of question marks.
        """
        cid = _f(o, "cardId")
        if cid is not None:
            return cid
        area = _f(o, "area")
        index = _f(o, "index")
        pidx = _f(o, "playerIndex")

        if otype == T_PLAY:            # PLAY implies our own hand
            area, pidx = self._AREA_HAND, view.my_index
        if otype in (T_ATTACK, T_RETREAT) and area is None:
            return _f(self._active_of(view, view.my_index), "id")
        if area is None or index is None:
            return None

        try:
            if area == self._AREA_DECK:
                zone = (_f(select_data, "deck", []) or [])
                return _f(zone[index], "id") if 0 <= index < len(zone) else None
            players = _f(view.state, "players", []) or []
            p = pidx if pidx is not None else view.my_index
            ps = players[p] if 0 <= p < len(players) else {}
            zone = {
                self._AREA_HAND: _f(ps, "hand", []) or [],
                self._AREA_DISCARD: _f(ps, "discard", []) or [],
                self._AREA_ACTIVE: _f(ps, "active", []) or [],
                self._AREA_BENCH: _f(ps, "bench", []) or [],
                self._AREA_PRIZE: _f(ps, "prize", []) or [],
                self._AREA_STADIUM: _f(view.state, "stadium", []) or [],
                self._AREA_LOOKING: _f(view.state, "looking", []) or [],
            }.get(area)
            if zone is None or not (0 <= index < len(zone)):
                return None
            return _f(zone[index], "id")
        except Exception:
            return None

    @staticmethod
    def _active_of(view, pidx):
        players = _f(view.state, "players", []) or []
        ps = players[pidx] if 0 <= pidx < len(players) else {}
        act = _f(ps, "active", []) or []
        return act[0] if act and act[0] is not None else None

    def _pkm(self, p):
        if p is None:
            return "\u2014"
        cid = _f(p, "id")
        hp, mx = _f(p, "hp", 0), _f(p, "maxHp", 0)
        e = _f(p, "energies", []) or []
        tools = _f(p, "tools", []) or []
        s = f"{self.name(cid)} {hp}/{mx} e{len(e)}"
        if e:
            s += "[" + "".join(ENERGY_NAME.get(_val(x), "?") for x in e) + "]"
        if tools:
            s += f" +{len(tools)}tool"
        return s

    # -- game lifecycle -------------------------------------------------

    def start_game(self, seat=0, going_first=None):
        self.end_game(result=None)
        self.game_count += 1
        self._started = True
        self._seat = seat
        self._my_turn_no = 0
        self._engine_turn = None
        self._cur = Counter()
        self._lines = []
        first = ("going first" if going_first else
                 "going second" if going_first is False else "order unknown")
        self._header_idx = len(self._lines)
        self._lines.append(f"\n\u2550\u2550 GAME {self.game_count} \u2550\u2550  seat {seat} \u00b7 {first}")

    def turn(self, view):
        """Call once at each new engine turn where we're asked to act."""
        if not self._started:
            self.start_game(seat=getattr(view, "my_index", 0))
        self._flush_turn()
        st = view.state
        # firstPlayer is -1 during setup; backfill the header once it's known.
        fp = _f(st, "firstPlayer", -1)
        if fp in (0, 1) and getattr(self, "_header_idx", None) is not None:
            if "order unknown" in self._lines[self._header_idx]:
                order = "going first" if fp == self._seat else "going second"
                self._lines[self._header_idx] = (
                    f"\n\u2550\u2550 GAME {self.game_count} \u2550\u2550  seat {self._seat} \u00b7 {order}")
        et = _f(st, "turn", 0)
        self._engine_turn = et
        self._my_turn_no += 1
        self._cur["turns"] += 1
        self._turn = Counter()

        # Engine / setup-race tracking. The plan is Dragapult by my turn 2 and
        # Phantom Dive from turn 3, paid for by Recon Directive on the bench.
        board_ids = [_f(p, "id") for p in ([view.my_active] + view.my_bench)
                     if p is not None]
        if DRAGAPULT_ID in board_ids and not self._cur.get("pult_turn"):
            self._cur["pult_turn"] = self._my_turn_no
        self._cur["drakloak_now"] = board_ids.count(DRAKLOAK_ID)

        # A ready attacker sitting on the bench is dead weight. Count the
        # turns it happens - it is invisible in every other statistic.
        act_id = _f(view.my_active, "id") if view.my_active is not None else None
        if act_id != DRAGAPULT_ID:
            for p in view.my_bench:
                if p is None or _f(p, "id") != DRAGAPULT_ID:
                    continue
                e = list(_f(p, "energies", []) or [])
                if e.count(10) >= 2 or all(c in e or 10 in e for c in (2, 5)):
                    self._cur["stranded_turns"] += 1
                    break
        self._cur["line_now"] = sum(1 for c in board_ids
                                    if c in (DREEPY_ID, DRAKLOAK_ID, DRAGAPULT_ID))
        # Sample the board at the START of my SECOND prompt: on the setup
        # prompt (engine turn 0) nothing is on the field yet, so measuring
        # there reported 0.00 every single game regardless of what happened.
        if self._engine_turn and not self._cur.get("line_measured"):
            self._cur["line_t1"] = self._cur["line_now"]
            self._cur["line_measured"] = 1

        me, opp = view.me, view.opp
        hand = list(view.hand_ids)
        self._turn["energy_in_hand"] = sum(1 for c in hand if self._is_energy(c))

        L = self._turn_lines = []
        L.append(f"\n\u2500\u2500 my turn {self._my_turn_no} (engine turn {et}) \u2500\u2500")
        if hand:
            L.append("  hand  " + ", ".join(self.name(c) for c in hand))
        else:
            L.append("  hand  (hidden or empty)")
        L.append("  me    ACT " + self._pkm(view.my_active) +
                 " \u00b7 BENCH " + (", ".join(self._pkm(p) for p in view.my_bench) or "\u2014"))
        L.append(f"        prizes {len(_f(me,'prize',[]) or [])} \u00b7 "
                 f"deck {_f(me,'deckCount',0)}")
        L.append("  opp   ACT " + self._pkm(view.opp_active) +
                 " \u00b7 BENCH " + (", ".join(self._pkm(p) for p in view.opp_bench) or "\u2014"))
        L.append(f"        prizes {len(_f(opp,'prize',[]) or [])} \u00b7 "
                 f"hand {_f(opp,'handCount',0)}")

    def _card(self, cid):
        """CardIndex has been refactored more than once \u2014 try both accessors
        and fall back to None rather than taking down the whole hook."""
        idx = self.card_index
        if idx is None or cid is None:
            return None
        for attr in ("get", "data"):
            fn = getattr(idx, attr, None)
            if callable(fn):
                try:
                    return fn(cid)
                except Exception:
                    pass
        try:
            return getattr(idx, "by_id", {}).get(cid)
        except Exception:
            return None

    def _is_energy(self, cid):
        cd = self._card(cid)
        if cd is not None:
            return "energy" in (getattr(cd, "name", "") or "").lower()
        return cid in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 20)

    # -- decisions ------------------------------------------------------

    def _log_options(self, view, select_obj, options, chosen, ctx):
        """
        Dump the FULL option list on early MAIN prompts.

        Without this we can only see what was chosen, which cannot tell the
        difference between "the agent rejected Rare Candy" and "Rare Candy
        was never a legal option". Those need opposite fixes, and guessing
        wrong costs a whole test run.
        """
        if ctx != 0 or not self._engine_turn:
            return
        if self._engine_turn > self._opt_log_until:
            return
        picked = set(chosen or [])
        parts = []
        for i, o in enumerate(options):
            t = _val(_f(o, "type", None))
            cid = self._resolve_cid(view, select_obj, o, t)
            nm = self.name(cid) if cid is not None else ""
            tag = {T_PLAY: "play", T_ATTACH: "attach", T_EVOLVE: "evolve",
                   T_ABILITY: "ability", T_ATTACK: "attack",
                   T_RETREAT: "retreat", T_END: "end"}.get(t, str(t))
            label = f"{tag}:{nm}" if nm else tag
            parts.append(("*" if i in picked else "") + label)
        self._turn_lines.append("    avail  " + " | ".join(parts))

    def decision(self, view, select_obj, options, chosen, source="policy",
                 detail=""):
        """Record one selection. `chosen` is the list of option indices."""
        if not self._started:
            self.start_game(seat=getattr(view, "my_index", 0))
        if self._turn is None:
            self._turn = Counter()

        ctx = _val(_f(select_obj, "context", None))
        ctx_name = CTX.get(ctx, f"ctx{ctx}")
        self._log_options(view, select_obj, options, chosen, ctx)

        # Was an attachment even available this turn? Without this, ending a
        # turn holding energy with no legal attach target reads as a mistake.
        for o in options:
            if _val(_f(o, "type", None)) == T_ATTACH:
                self._turn["attach_offered"] = 1
                break

        for idx in (chosen or []):
            if not (isinstance(idx, int) and 0 <= idx < len(options)):
                continue
            o = options[idx]
            otype = _val(_f(o, "type", None))
            cid = self._resolve_cid(view, select_obj, o, otype)
            try:
                line = self._render(view, o, otype, cid, ctx, ctx_name)
            except Exception as ex:
                line = f"{ctx_name}: {TYPE_NAME.get(otype, otype)} card:{cid} (render failed: {ex})"
            self._count(view, o, otype, cid, ctx)
            tag = f"[{source}{(' ' + detail) if detail else ''}]"
            warn = self._warn(view, otype, cid, ctx)
            self._turn_lines.append(f"  \u00b7 {line:<50} {tag}{warn}")

    def _render(self, view, o, otype, cid, ctx, ctx_name):
        nm = self.name(cid)
        if ctx == 30 or ctx == 26:
            return f"DISCARD ENERGY {nm}  (retreat/attack cost)"
        if ctx in (13, 14, 15):
            owner = _f(o, "playerIndex")
            side = "ours" if owner == view.my_index else "theirs"
            return f"DAMAGE \u2192 {nm} ({side})"
        if ctx == 41:
            return "GO FIRST" if otype == T_YES else "GO SECOND"
        if ctx == 42:
            return "MULLIGAN: redraw" if otype == T_YES else "MULLIGAN: keep"
        if ctx in (1, 2):
            return f"SETUP {'ACTIVE' if ctx == 1 else 'BENCH'} {nm}"
        if otype == T_ATTACH:
            area = _f(o, "inPlayArea")
            i = _f(o, "inPlayIndex", 0)
            where = "active" if area == 4 else f"bench {i}"
            return f"ATTACH {nm} \u2192 {self._target_name(view, area, i)} ({where})"
        if otype == T_ATTACK:
            return f"ATTACK {nm} (attackId {_f(o,'attackId')})"
        if otype == T_ABILITY:
            return f"ABILITY {nm}"
        if otype == T_EVOLVE:
            return f"EVOLVE \u2192 {nm}"
        if otype == T_PLAY:
            return f"PLAY {nm}"
        if otype == T_RETREAT:
            return f"RETREAT {self._pkm(view.my_active).split(' ')[0]}"
        if otype == T_END:
            return "END TURN"
        if otype in (T_YES, T_NO):
            return f"{ctx_name}: {'yes' if otype == T_YES else 'no'}"
        if otype == T_NUMBER:
            return f"{ctx_name}: {_f(o,'number')}"
        return f"{ctx_name}: {TYPE_NAME.get(otype, otype)} {nm}"

    def _target_name(self, view, area, i):
        board = ([p for p in (_f(view.me, "active", []) or []) if p is not None]
                 if area == 4 else view.my_bench)
        if 0 <= (i or 0) < len(board):
            return self.name(_f(board[i or 0], "id"))
        return "?"

    def _count(self, view, o, otype, cid, ctx):
        c, t = self._cur, self._turn
        if otype == T_ATTACH:
            c["attach"] += 1; t["attach"] += 1
        elif otype == T_RETREAT:
            c["retreat"] += 1; t["retreat"] += 1
        elif otype == T_ATTACK:
            c["attack"] += 1; t["attack"] += 1
            # Only a real Phantom Dive counts. Cursed Blast also places
            # counters, so keying off damage placement over-reported this.
            if _f(o, "attackId") == PHANTOM_DIVE_ATTACK_ID:
                if not c.get("first_dive_turn"):
                    c["first_dive_turn"] = self._my_turn_no
                c["dives"] += 1
        elif otype == T_ABILITY:
            c["ability"] += 1
            if cid == DRAKLOAK_ID:
                c["recon"] += 1          # the deck's actual draw engine
        elif otype == T_EVOLVE:
            c["evolve"] += 1
        elif otype == T_PLAY:
            c["play"] += 1
        if ctx in (26, 30):
            c["energy_discarded"] += 1; t["discard"] += 1
        if ctx in (13, 14, 15):
            c["damage_placed"] += 1; t["damage"] += 1
            if _f(o, "playerIndex") == view.my_index:
                c["damage_on_self"] += 1

    def _warn(self, view, otype, cid, ctx):
        if ctx in (26, 30):
            return "  \u26a0 ENERGY PAID"
        if ctx in (13, 14, 15) and _f(view, "my_index", 0) is not None:
            pass
        return ""

    # -- turn / game close ----------------------------------------------

    def _flush_turn(self):
        if not self._turn_lines:
            return
        t = self._turn or Counter()
        att, dis = t.get("attach", 0), t.get("discard", 0)
        eih = t.get("energy_in_hand", 0)
        line = (f"  turn: attached {att} \u00b7 discarded {dis} \u00b7 net {att - dis}"
                f" \u00b7 energy in hand at start {eih}")
        # Setup (engine turn 0) has no attachment step, and an attach that was
        # never offered is not a miss.
        if att == 0 and eih > 0 and t.get("attach_offered") and self._engine_turn:
            line += "   \u26a0 MISSED ATTACHMENT"
            self._cur["missed_attach"] += 1
        elif att == 0 and eih > 0 and not t.get("attach_offered") and self._engine_turn:
            line += "   (no attach target offered)"
            self._cur["no_attach_target"] += 1
        if dis > att:
            line += "   \u26a0 NET ENERGY LOSS"
        self._turn_lines.append(line)
        if self.mode == "summary":
            keep = [l for l in self._turn_lines
                    if not l.lstrip().startswith("\u00b7")]
            self._lines.extend(keep)
        else:
            self._lines.extend(self._turn_lines)
        self._turn_lines = []

    def end_game(self, result=None, winner=None):
        if not self._started:
            return
        self._flush_turn()
        c = self._cur or Counter()
        turns = max(1, c.get("turns", 1))
        outcome = "UNKNOWN"
        if winner is not None:
            outcome = "WIN" if winner == self._seat else "LOSS"
        elif result is not None:
            outcome = str(result)
        self._lines.append(
            f"\n\u2500\u2500 RESULT: {outcome} at engine turn {self._engine_turn} \u2500\u2500")
        self._lines.append(
            f"  attach/turn {c.get('attach',0)/turns:.2f} \u00b7 "
            f"lost to retreat {c.get('energy_discarded',0)} \u00b7 "
            f"retreats {c.get('retreat',0)} \u00b7 attacks {c.get('attack',0)} \u00b7 "
            f"damage placements {c.get('damage_placed',0)}")
        net = c.get("attach", 0) - c.get("energy_discarded", 0)
        self._lines.append(
            f"  net energy on board {net} \u00b7 evolutions {c.get('evolve',0)} \u00b7 "
            f"abilities {c.get('ability',0)} \u00b7 plays {c.get('play',0)}")

        # --- the setup race: this is what decides the game ---
        pult = c.get("pult_turn")
        dive = c.get("first_dive_turn")
        self._lines.append(
            "  SETUP RACE  Dragapult online: "
            + (f"my turn {pult}" if pult else "NEVER")
            + "  (target 2)  \u00b7  first Phantom Dive: "
            + (f"my turn {dive}" if dive else "NEVER")
            + "  (target 3)")
        self._lines.append(
            f"  ENGINE      Dreepy line on turn 1: {c.get('line_t1',0)} (target 3) \u00b7 "
            f"Phantom Dives {c.get('dives',0)} \u00b7 "
            f"Recon Directive used {c.get('recon',0)}x "
            f"({c.get('recon',0)/turns:.2f} per turn)")
        if c.get("stranded_turns"):
            self._lines.append(
                f"  \u26a0 {c['stranded_turns']} turn(s) with a Phantom-Dive-ready "
                f"Dragapult stuck on the BENCH")
        if c.get("no_attach_target"):
            self._lines.append(
                f"  \u00b7 {c['no_attach_target']} turn(s) held energy with no legal "
                f"attach target offered")
        if c.get("missed_attach"):
            self._lines.append(
                f"  \u26a0 {c['missed_attach']} turn(s) ended with energy in hand "
                f"and no attachment made")
        if c.get("damage_on_self"):
            self._lines.append(
                f"  \u26a0 {c['damage_on_self']} damage counter(s) placed on OUR board")
        if c.get("damage_placed", 0) == 0:
            self._lines.append("  \u26a0 never placed a damage counter (no Phantom Dive)")
        if c.get("attack", 0) == 0:
            self._lines.append("  \u26a0 never attacked")

        if c.get("pult_turn"):
            self.totals["pult_games"] += 1
        if c.get("first_dive_turn"):
            self.totals["dive_games"] += 1
        for k, v in c.items():
            if k in ("drakloak_now", "line_now"):
                continue
            self.totals[k] += v
        self.totals["games"] += 1
        if outcome == "WIN":
            self.totals["wins"] += 1

        self.games.append(self._lines)
        if self.keep > 0 and len(self.games) > self.keep:
            self.games = self.games[-self.keep:]
        self._started = False
        self._lines = []
        self.flush()

    # -- one-line integration hook ---------------------------------------

    def source(self, source, detail=""):
        """Tag where the next recorded decision came from."""
        self._next_source = (source, detail)

    def observe(self, obs_dict, chosen):
        """
        Single hook. Call from sanitize_action with the final selection \u2014
        every return path in agent() funnels through there, including the
        exception fallback, so nothing goes unrecorded.
        """
        try:
            if not isinstance(obs_dict, dict):
                return
            current = obs_dict.get("current")
            if current is None:
                if obs_dict.get("step", 0) == 0:
                    self.end_game()          # flush the previous game
                return

            seat = _f(current, "yourIndex", 0)
            if not self._started:
                first = _f(current, "firstPlayer", -1)
                self.start_game(
                    seat=seat,
                    going_first=(first == seat) if first in (0, 1) else None)

            view = DictView(current, seat)
            turn = _f(current, "turn", 0)

            # New-game boundary. We cannot rely on seeing the deck submission:
            # agent() returns the deck list before reaching sanitize_action, so
            # the hook never observes it. The turn counter resetting downward is
            # the reliable signal. Seat changes count too \u2014 the evaluator alternates
            # which side we play.
            if self._started and self._engine_turn is not None and (
                    turn < self._engine_turn or seat != self._seat):
                self.end_game()
                first = _f(current, "firstPlayer", -1)
                self.start_game(
                    seat=seat,
                    going_first=(first == seat) if first in (0, 1) else None)

            if turn != self._engine_turn:
                self.turn(view)

            select_data = obs_dict.get("select") or {}
            options = select_data.get("option") or []
            src, detail = getattr(self, "_next_source", ("policy", ""))
            self._next_source = ("policy", "")
            self.decision(view, select_data, options, chosen, src, detail)

            result = _f(current, "result", -1)
            if result is not None and result != -1:
                self.end_game(winner=result)
        except Exception as e:
            sys.stderr.write(f"[battle_log] observe failed: {e}\n")

    def record_result(self, winner):
        """Call from the training harness if it knows who won."""
        self.end_game(winner=winner)

    # -- output ----------------------------------------------------------

    def _aggregate(self):
        t = self.totals
        g = max(1, t.get("games", 0))
        turns = max(1, t.get("turns", 0))
        out = ["", "\u2550" * 62,
               f"AGGREGATE over {t.get('games',0)} completed game(s)",
               "\u2550" * 62]
        if t.get("wins"):
            out.append(f"  win rate            {100*t['wins']/g:.1f}%")
        out += [
            f"  attach / own turn   {t.get('attach',0)/turns:.2f}   (target 1.00)",
            f"  energy attached     {t.get('attach',0)/g:.2f} per game",
            f"  energy discarded    {t.get('energy_discarded',0)/g:.2f} per game"
            f"   ({100*t.get('energy_discarded',0)/max(1,t.get('attach',0)):.0f}% of attached)",
            f"  net energy          {(t.get('attach',0)-t.get('energy_discarded',0))/g:.2f} per game",
            f"  retreats            {t.get('retreat',0)/g:.2f} per game",
            f"  attacks             {t.get('attack',0)/g:.2f} per game",
            f"  damage placements   {t.get('damage_placed',0)/g:.2f} per game",
            f"  missed attachments  {t.get('missed_attach',0)} turn(s) total",
            "",
            f"  Dragapult online    {t.get('pult_turn',0)/max(1,t.get('pult_games',1)):.1f}"
            f" (avg my-turn, target 2) in {t.get('pult_games',0)}/{t.get('games',0)} games",
            f"  first Phantom Dive  {t.get('first_dive_turn',0)/max(1,t.get('dive_games',1)):.1f}"
            f" (avg my-turn, target 3) in {t.get('dive_games',0)}/{t.get('games',0)} games",
            f"  Recon Directive     {t.get('recon',0)/turns:.2f} per turn",
            f"  Dreepy line turn 1  {t.get('line_t1',0)/g:.2f} (target 3.00)",
            f"  attacker stranded   {t.get('stranded_turns',0)} turn(s) total"
            f" (ready Dragapult left on the bench)",
        ]
        return out

    def flush(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("DRAGAPULT BATTLE LOG \u2014 paste this whole file\n")
                for block in self.games:
                    f.write("\n".join(block) + "\n")
                f.write("\n".join(self._aggregate()) + "\n")
        except Exception as e:
            sys.stderr.write(f"[battle_log] write failed: {e}\n")


# ---------------------------------------------------------------------------
# Dict view \u2014 lets the logger read a raw obs_dict with no engine conversion
# ---------------------------------------------------------------------------


class DictView:
    """The handful of View fields the logger needs, read straight off the
    observation dict. Avoids depending on to_observation_class, so the hook
    works on every code path including exception fallbacks."""

    def __init__(self, current, seat):
        self.state = current
        self.my_index = seat
        self.opp_index = 1 - seat
        players = _f(current, "players", []) or []
        self.me = players[seat] if len(players) > seat else {}
        self.opp = players[self.opp_index] if len(players) > self.opp_index else {}

    @staticmethod
    def _first(lst):
        lst = lst or []
        return lst[0] if lst and lst[0] is not None else None

    @property
    def my_active(self):
        return self._first(_f(self.me, "active", []))

    @property
    def opp_active(self):
        return self._first(_f(self.opp, "active", []))

    @property
    def my_bench(self):
        return [p for p in (_f(self.me, "bench", []) or []) if p is not None]

    @property
    def opp_bench(self):
        return [p for p in (_f(self.opp, "bench", []) or []) if p is not None]

    @property
    def hand_ids(self):
        hand = _f(self.me, "hand", None)
        if not hand:
            return []
        return [_f(c, "id") for c in hand if c is not None]


# ---------------------------------------------------------------------------
# Standalone: re-derive the aggregate from a saved transcript
# ---------------------------------------------------------------------------

def analyze(path):
    import re
    text = open(path, encoding="utf-8", errors="replace").read()
    games = text.count("\u2550\u2550 GAME")
    print(f"games in transcript: {games}")
    for label, pat in [
        ("wins", r"RESULT: WIN"), ("losses", r"RESULT: LOSS"),
        ("paid retreats", r"\u26a0 ENERGY PAID"),
        ("missed attachments", r"\u26a0 MISSED ATTACHMENT"),
        ("net-loss turns", r"\u26a0 NET ENERGY LOSS"),
        ("games with no dive", r"never placed a damage counter"),
        ("games with no attack", r"never attacked"),
    ]:
        print(f"  {label:<22} {len(re.findall(pat, text))}")


if __name__ == "__main__":
    analyze(sys.argv[1] if len(sys.argv) > 1 else "battle_log.txt")

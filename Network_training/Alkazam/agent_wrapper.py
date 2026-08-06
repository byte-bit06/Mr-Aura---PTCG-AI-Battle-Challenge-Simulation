"""
agent_wrapper.py — attach battle logging to ANY agent, without patching it.

The Dragapult setup logs by inserting hooks into main.py with patch_main.py.
That only works because I wrote that main.py and know where its seams are.
For a third-party agent there are no seams, and editing someone else's file
to instrument it is the wrong trade anyway.

Every agent has the same contract: `agent(obs_dict) -> list[int]`. Both the
observation and the chosen indices pass through that one call, which is all
the logger needs. So wrap the function instead of editing the file:

    from agent_wrapper import wrap_agent
    logged, log = wrap_agent(their_agent, profile="alakazam")

What you lose compared to the patched version: the `[search]` / `[policy]`
source tags, which came from inside my own agent's decision layer. Everything
else - board state, hand, option lists, setup-race and engine metrics - is
derived from the observation and works unchanged.
"""

import inspect
import os

from battle_log import BattleLogger, PROFILES


def wrap_agent(agent_fn, profile=None, card_index=None, path=None,
               keep_games=None, logger=None):
    """
    Returns (wrapped_agent, logger).

    `agent_fn` may be a plain function or a module exposing `agent`.
    """
    if not callable(agent_fn) and hasattr(agent_fn, "agent"):
        agent_fn = agent_fn.agent
    if not callable(agent_fn):
        raise TypeError("agent_fn must be callable or expose .agent")

    log = logger or BattleLogger(card_index=card_index, path=path,
                                 keep_games=keep_games, profile=profile)

    # Some agents take (obs) and some take (obs, configuration).
    try:
        n_params = len(inspect.signature(agent_fn).parameters)
    except (TypeError, ValueError):
        n_params = 1

    def wrapped(obs_dict, configuration=None):
        try:
            result = (agent_fn(obs_dict, configuration) if n_params >= 2
                      else agent_fn(obs_dict))
        except Exception:
            log.flush()
            raise
        try:
            log.observe(obs_dict, result)
        except Exception as e:
            # Logging must never take the agent down mid-match.
            import sys
            sys.stderr.write(f"[agent_wrapper] logging failed: {e}\n")
        return result

    wrapped.__name__ = getattr(agent_fn, "__name__", "agent") + "_logged"
    return wrapped, log


def build_card_index():
    """Card names for the transcript. Falls back to bare ids."""
    try:
        from cg.api import all_card_data
        try:
            from dragapult_heuristics import CardIndex
            return CardIndex.from_card_data(all_card_data())
        except Exception:
            class _Idx:
                def __init__(self, cards):
                    self.by_id = {c.cardId: c for c in cards}

                def get(self, cid):
                    return self.by_id.get(cid)

                def name(self, cid):
                    c = self.by_id.get(cid)
                    return getattr(c, "name", None) if c else None

                def is_ex(self, cid):
                    c = self.by_id.get(cid)
                    return bool(getattr(c, "ex", False) or
                                getattr(c, "megaEx", False)) if c else False
            return _Idx(all_card_data())
    except Exception:
        return None

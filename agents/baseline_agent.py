"""
baseline_agent.py — The original hardcoded Kaggle heuristic bot.
Uses the exact same scoring constants as the notebook submission.
Never reads from optimized_weights.json — these values are frozen.
"""

import sys
sys.path.insert(0, ".")
import main as _main

# Original hardcoded constants from the Kaggle notebook
# (MEG variant IDs added — same constants apply, originals stay in main.py)
_ORIGINAL_WEIGHTS = {
    "W_PRIZE_MULT":             1000,
    "W_ENERGY_SCORE":            150,
    "W_TOOL_SCORE":              100,
    "W_STAGE2_SCORE":            250,
    "W_STAGE1_SCORE":            130,
    "W_ACTIVE_BONUS":            220,
    "W_TARGET_ACTIVE_BONUS":     300,
    "W_ENERGY_ACTIVE_BIAS":       10,
    "W_ENERGY_BASE":            8000,
    "W_ENERGY_NEED_BONUS":       100,
    "W_ENERGY_SURPLUS_PENALTY":   50,
    "W_EVOLVE_BASE":            9000,
    "W_TRAINER_BASE":          10000,
    "W_POKEMON_BASE":          20000,
    "W_RETREAT_SCORE":          2000,
    "W_ATTACK_SCORE":           1000,
}


def agent(obs_dict: dict) -> list[int]:
    """
    Runs the heuristic agent with the original hardcoded weights.
    Temporarily swaps main.W so the same dict-path logic is used,
    but with frozen original constants regardless of optimized_weights.json.
    """
    saved_W = _main.W
    # Also save/restore the per-turn plan state so baseline and candidate
    # don't share state when both are called as Python functions in the same process.
    saved_plan         = dict(_main._dict_plan)
    saved_pre_turn     = _main._dict_pre_turn
    saved_ability_used = _main._dict_ability_used
    try:
        _main.W = dict(_ORIGINAL_WEIGHTS)
        return _main.agent(obs_dict)
    finally:
        _main.W            = saved_W
        _main._dict_plan   = saved_plan
        _main._dict_pre_turn     = saved_pre_turn
        _main._dict_ability_used = saved_ability_used

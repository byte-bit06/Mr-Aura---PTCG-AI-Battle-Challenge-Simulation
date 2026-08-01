"""
train_genetic.py
----------------
Genetic / evolutionary training loop for the Pokemon TCG Kaggle competition.

Strategy
--------
1.  Start from the weights in optimized_weights.json (or defaults if absent).
2.  Each generation, spawn a population of mutants by nudging every weight
    by a Gaussian sample (+-mutation_sigma % of the current value).
3.  Run N self-play games per candidate:
        Player 0 = candidate (evolved weights from optimized_weights.json)
        Player 1 = original hardcoded baseline (baseline_agent.py)
4.  Win = state[0].reward == 1  (candidate beat the baseline)
5.  Pick the best-scoring candidate as the new champion.
6.  Repeat until any candidate hits WIN_RATE_TARGET win rate.
7.  Every game's HTML replay is saved to the replays/ folder.
"""

import copy
import json
import os
import random
import sys
import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
WEIGHTS_FILE      = "optimized_weights.json"   # champion weights (r/w)
CANDIDATE_FILE    = "candidate_weights.json"   # temp file each candidate run

POPULATION_SIZE   = 6       # elite + mutants per generation
GAMES_PER_EVAL    = 10      # matches per candidate per generation
WIN_RATE_TARGET   = 0.60    # stop when a candidate beats this threshold
MAX_GENERATIONS   = 200     # hard ceiling on generations
MUTATION_SIGMA    = 0.12    # std-dev of Gaussian mutation as fraction of weight
WEIGHT_MIN_FRAC   = 0.10    # weight cannot drop below 10% of its default

REPLAYS_DIR       = "replays"   # folder where HTML game replays are saved

_WEIGHT_DEFAULTS = {
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


# ── Weight helpers ────────────────────────────────────────────────────────────
def load_weights(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            merged = dict(_WEIGHT_DEFAULTS)
            merged.update({k: v for k, v in data.items() if k in _WEIGHT_DEFAULTS})
            return merged
        except Exception as exc:
            print(f"[warn] Could not load {path}: {exc}. Using defaults.")
    return dict(_WEIGHT_DEFAULTS)


def save_weights(weights: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(weights, f, indent=2)


def mutate(weights: dict) -> dict:
    mutant = {}
    for key, val in weights.items():
        default_val = _WEIGHT_DEFAULTS.get(key, val)
        sigma   = abs(val) * MUTATION_SIGMA
        new_val = val + random.gauss(0, sigma)
        floor   = abs(default_val) * WEIGHT_MIN_FRAC
        new_val = max(floor, new_val) if default_val > 0 else min(-floor, new_val)
        mutant[key] = round(new_val, 4)
    return mutant


# ── Deck loader ───────────────────────────────────────────────────────────────
def _load_deck() -> list[int]:
    path = "deck.csv"
    if not os.path.exists(path):
        path = "/kaggle_simulations/agent/deck.csv"
    with open(path) as f:
        return [int(line) for line in f if line.strip()]


# ── Replay saving ─────────────────────────────────────────────────────────────
def _save_replay(env, label: str) -> str:
    """Render and save an HTML replay. Returns the saved file path."""
    os.makedirs(REPLAYS_DIR, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
    name = f"{label}_{ts}.html"
    path = os.path.join(REPLAYS_DIR, name)
    try:
        html = env.render(mode="html")
        csp  = '<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">'
        html = html.replace("<head>", f"<head>\n{csp}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as exc:
        print(f"    [replay] Save failed: {exc}")
        return ""
    return path


# ── Win detection ─────────────────────────────────────────────────────────────
def _determine_winner(env) -> int:
    """1 = candidate (P0) won, -1 = baseline (P1) won, 0 = draw."""
    try:
        r0 = env.state[0].reward
        r1 = env.state[1].reward
        if r0 > r1: return  1
        if r1 > r0: return -1
    except Exception:
        pass
    return 0


# ── Agent factories ───────────────────────────────────────────────────────────
def _make_candidate_agent(weights: dict):
    """Return an agent function that uses the given weights."""
    import main as _main

    def _agent(obs_dict: dict) -> list[int]:
        saved_W            = _main.W
        saved_plan         = dict(_main._dict_plan)
        saved_pre_turn     = _main._dict_pre_turn
        saved_ability_used = _main._dict_ability_used
        try:
            _main.W = weights
            return _main.agent(obs_dict)
        finally:
            _main.W                  = saved_W
            _main._dict_plan         = saved_plan
            _main._dict_pre_turn     = saved_pre_turn
            _main._dict_ability_used = saved_ability_used

    return _agent


# ── Core evaluation ───────────────────────────────────────────────────────────
def evaluate_candidate(candidate_weights: dict, n_games: int,
                       gen: int, cand_idx: int) -> tuple[int, int]:
    """
    Play n_games of candidate (P0) vs original baseline (P1).
    Saves an HTML replay for every game.
    Returns (wins, losses).
    """
    from kaggle_environments import make
    import baseline_agent

    candidate_fn = _make_candidate_agent(candidate_weights)
    wins = losses = 0

    for game_idx in range(n_games):
        try:
            env    = make("cabt")
            env.run([candidate_fn, baseline_agent.agent])
            result = _determine_winner(env)

            if result == 1:
                wins   += 1
                outcome = "WIN"
            elif result == -1:
                losses += 1
                outcome = "LOSS"
            else:
                outcome = "DRAW"

            label    = f"gen{gen:03d}_cand{cand_idx}_game{game_idx+1:02d}_{outcome}"
            replay   = _save_replay(env, label)
            rel_path = os.path.relpath(replay) if replay else "not saved"
            print(f"    game {game_idx+1:2d}/{n_games}  {outcome:4s}  -> {rel_path}")

        except Exception as exc:
            print(f"    game {game_idx+1:2d} ERROR: {exc}")

    return wins, losses


# ── Main training loop ────────────────────────────────────────────────────────
def train():
    print("=" * 60)
    print("  Pokemon TCG Genetic Training Loop")
    print("  Candidate vs Original Baseline")
    print("=" * 60)

    deck = _load_deck()
    print(f"Deck loaded  : {len(deck)} cards")
    if len(deck) != 60:
        print(f"[ERROR] Deck must have 60 cards (got {len(deck)}). Aborting.")
        sys.exit(1)

    os.makedirs(REPLAYS_DIR, exist_ok=True)
    print(f"Replays dir  : {os.path.abspath(REPLAYS_DIR)}")

    champion = load_weights(WEIGHTS_FILE)
    save_weights(champion, WEIGHTS_FILE)

    print(f"Start weights: {WEIGHTS_FILE}")
    print(f"Win target   : {WIN_RATE_TARGET * 100:.0f}%")
    print(f"Games/eval   : {GAMES_PER_EVAL}")
    print(f"Population   : {POPULATION_SIZE}")
    print(f"Max gens     : {MAX_GENERATIONS}")
    print()

    best_ever_rate = 0.0

    for gen in range(1, MAX_GENERATIONS + 1):
        print(f"--- Generation {gen:3d} -------------------------------------------")

        population = [copy.deepcopy(champion)] + \
                     [mutate(champion) for _ in range(POPULATION_SIZE - 1)]

        gen_results = []

        for idx, candidate in enumerate(population):
            label = "elite " if idx == 0 else f"mutant {idx}"
            print(f"  [{label:8s}] vs baseline ({GAMES_PER_EVAL} games):")
            wins, losses = evaluate_candidate(candidate, GAMES_PER_EVAL, gen, idx)
            rate = wins / GAMES_PER_EVAL
            gen_results.append((rate, wins, losses, candidate))

            bar   = "#" * int(rate * 20) + "." * (20 - int(rate * 20))
            print(f"  [{label:8s}] RESULT: {wins}/{GAMES_PER_EVAL}  [{bar}] {rate*100:5.1f}%")

            if rate >= WIN_RATE_TARGET:
                print(f"\n*** TARGET REACHED! {label} hit {rate*100:.1f}% in gen {gen}. ***")
                save_weights(candidate, WEIGHTS_FILE)
                _cleanup_temp()
                print(f"Weights saved -> {WEIGHTS_FILE}")
                print(f"All replays   -> {os.path.abspath(REPLAYS_DIR)}/")
                return candidate

        best = max(gen_results, key=lambda r: r[0])
        best_rate, _, _, best_weights = best
        champion = best_weights

        if best_rate > best_ever_rate:
            best_ever_rate = best_rate
            save_weights(champion, WEIGHTS_FILE)
            print(f"  [NEW BEST] {best_rate*100:.1f}% -- weights saved.")
        else:
            print(f"  Best this gen: {best_rate*100:.1f}%  "
                  f"(all-time best: {best_ever_rate*100:.1f}%)")
        print()

    print(f"Max generations reached. Best: {best_ever_rate*100:.1f}%")
    save_weights(champion, WEIGHTS_FILE)
    _cleanup_temp()
    return champion


def _cleanup_temp():
    if os.path.exists(CANDIDATE_FILE):
        try: os.remove(CANDIDATE_FILE)
        except Exception: pass


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    train()

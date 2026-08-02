"""
optimize_ga.py — 100,000 Game Multi-Game Genetic Algorithm Optimizer for Wall_V10 V2
====================================================================================
Optimizes weight parameters in optimized_weights.json against meta gauntlet.
Continuously saves best weights to optimized_weights.json and timestamped checkpoints
to checkpoints/ directory. Final submission.tar.gz is built ONCE at the end of optimization.

Prize Ratio & Multi-Objective Fitness Objective:
  1. MAXIMIZES PRIZE RATIO: (Prizes_Taken + 0.01) / (Prizes_Conceded + 0.01) (+3000.0x)
  2. Maximizes Prize Cards Taken Us (+1000.0x per prize)
  3. Heavily Penalizes Prize Cards Conceded Opponent (-2500.0x per prize)
  4. Maximizes Total HP Damage Given (+1.0x per HP damage dealt)
  5. Minimizes Total HP Damage Taken (-1.5x per HP damage received)
  6. Win Bonus (+5000.0x per victory)
"""

import os
import sys
import json
import random
import copy
import time
import math
import tarfile
from kaggle_environments import make

# ── Path Setup ─────────────────────────────────────────────────────────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_network_training_dir = os.path.abspath(os.path.join(_this_dir, '..', '..'))
if _network_training_dir not in sys.path:
    sys.path.insert(0, _network_training_dir)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

CHECKPOINT_DIR = os.path.join(_this_dir, "checkpoints")
if not os.path.exists(CHECKPOINT_DIR):
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

HISTORY_LOG_FILE = os.path.join(_this_dir, "ga_optimization_history.log")

def log_ga_history(msg):
    sys.stdout.write(f"{msg}\n")
    sys.stdout.flush()
    try:
        with open(HISTORY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

# ── Patch Environment ──────────────────────────────────────────────────────
import cg.game as local_game
import cg.sim as local_sim
import kaggle_environments.envs.cabt.cabt as cabt_mod

cabt_mod.battle_start = local_game.battle_start
cabt_mod.battle_select = local_game.battle_select
cabt_mod.battle_finish = local_game.battle_finish
cabt_mod.visualize_data = local_game.visualize_data
cabt_mod.Battle = local_sim.Battle

# Opponents setup
_opp_dir = os.path.join(_network_training_dir, 'opponents')
if _opp_dir not in sys.path:
    sys.path.insert(0, _opp_dir)

import lucario_agent
import iono_agent
import dragapult_agent
import abomasnow_agent
import mcts_lucario_agent
import archaludon_cinderace_agent

opponents = [
    ('Lucario ex', lucario_agent.agent),
    ('Iono Deck', iono_agent.agent),
    ('Dragapult ex', dragapult_agent.agent),
    ('Abomasnow ex', abomasnow_agent.agent),
    ('MCTS Lucario', mcts_lucario_agent.agent),
    ('Archaludon Cinderace', archaludon_cinderace_agent.agent),
]

try:
    import alakazam_agent
    opponents.append(('Alakazam ex V21', alakazam_agent.agent))
except ImportError:
    pass

import Wall_V10.V2.main as v2_main

# ── Fitness Prize Ratio & Multi-Objective Weight Config ────────────────────
W_RATIO_MULT     = float(os.environ.get("GA_W_RATIO", "3000.0"))   # DIRECT PRIZE RATIO MAXIMIZER!
W_TAKEN_MULT     = float(os.environ.get("GA_W_TAKEN", "1000.0"))   # Rewards Prizes Taken Us
W_CONCEDED_MULT  = float(os.environ.get("GA_W_CONCEDED", "2500.0")) # Heavy penalty for losing prizes!
W_DMG_GIVEN_MULT = float(os.environ.get("GA_W_DMG_GIVEN", "1.0"))   # Reward for dealing damage!
W_DMG_TAKEN_MULT = float(os.environ.get("GA_W_DMG_TAKEN", "1.5"))   # Penalty for taking damage!
W_WIN_BONUS      = float(os.environ.get("GA_W_WIN_BONUS", "5000.0"))

GAMES_PER_OPPONENT = int(os.environ.get("GA_GAMES_PER_OPP", "4"))  # 4 games per opponent (2 P1, 2 P2) for 0 luck variance!
POPULATION_SIZE    = int(os.environ.get("GA_POP_SIZE", "40"))
GENERATIONS        = int(os.environ.get("GA_GENERATIONS", "90"))   # 90 Gens x 40 Pop x 28 Games = 100,800 Games!
MUTATION_RATE      = float(os.environ.get("GA_MUTATION_RATE", "0.25"))
MUTATION_STDEV     = float(os.environ.get("GA_MUTATION_STDEV", "0.15"))

# Top 5% Selection
TOP_5_PCT_COUNT    = max(2, int(math.ceil(POPULATION_SIZE * 0.05)))

def update_agent_weights(weights_dict):
    """Dynamically update live agent weights dictionary in main.py."""
    v2_main.W.clear()
    v2_main.W.update(weights_dict)
    # Recalculate normalized factors
    v2_main.w_prize   = weights_dict.get("W_PRIZE_MULT", 1050.0) / 1000.0
    v2_main.w_energy  = weights_dict.get("W_ENERGY_BASE", 8500.0) / 10000.0
    v2_main.w_evolve  = weights_dict.get("W_EVOLVE_BASE", 9500.0) / 10000.0
    v2_main.w_trainer = weights_dict.get("W_TRAINER_BASE", 10500.0) / 10000.0
    v2_main.w_pokemon = weights_dict.get("W_POKEMON_BASE", 20000.0) / 20000.0
    v2_main.w_attack  = weights_dict.get("W_ATTACK_SCORE", 1250.0) / 1000.0
    v2_main.w_retreat = weights_dict.get("W_RETREAT_SCORE", 1800.0) / 1000.0
    v2_main.w_tool    = weights_dict.get("W_TOOL_SCORE", 120.0) / 1000.0

def extract_total_field_hp(player_dict):
    if not isinstance(player_dict, dict): return 0
    total_hp = 0
    active_list = player_dict.get("active") or []
    if active_list and isinstance(active_list[0], dict):
        total_hp += active_list[0].get("hp", 0)
    bench_list = player_dict.get("bench") or []
    for b in bench_list:
        if isinstance(b, dict):
            total_hp += b.get("hp", 0)
    return total_hp

def evaluate_match(env, p1_agent, p2_agent):
    """Run a single match and return (winner_index, p1_prizes_taken, p2_prizes_taken, p1_dmg_given, p1_dmg_taken)."""
    steps = env.run([p1_agent, p2_agent])
    last_step = steps[-1]
    
    r1 = last_step[0].get("reward", 0) if isinstance(last_step[0], dict) else 0
    r2 = last_step[1].get("reward", 0) if (len(last_step) > 1 and isinstance(last_step[1], dict)) else 0
    
    p1_prizes_rem = 6
    p2_prizes_rem = 6

    p1_dmg_given = 0
    p1_dmg_taken = 0

    prev_p1_hp = None
    prev_p2_hp = None

    for step_pair in steps:
        if not isinstance(step_pair, list) or len(step_pair) == 0: continue
        agent_step = step_pair[0]
        if isinstance(agent_step, dict):
            obs = agent_step.get("observation") or {}
            curr = obs.get("current") or {}
            players = curr.get("players") or []
            if len(players) >= 2:
                if isinstance(players[0], dict):
                    pz = players[0].get("prize") or players[0].get("prizes")
                    p1_prizes_rem = len(pz) if isinstance(pz, list) else int(pz or 6)
                    curr_p1_hp = extract_total_field_hp(players[0])
                    if prev_p1_hp is not None and curr_p1_hp < prev_p1_hp:
                        p1_dmg_taken += (prev_p1_hp - curr_p1_hp)
                    prev_p1_hp = curr_p1_hp

                if isinstance(players[1], dict):
                    pz = players[1].get("prize") or players[1].get("prizes")
                    p2_prizes_rem = len(pz) if isinstance(pz, list) else int(pz or 6)
                    curr_p2_hp = extract_total_field_hp(players[1])
                    if prev_p2_hp is not None and curr_p2_hp < prev_p2_hp:
                        p1_dmg_given += (prev_p2_hp - curr_p2_hp)
                    prev_p2_hp = curr_p2_hp

    winner_idx = None
    if (r1 or 0) > (r2 or 0):
        winner_idx = 0
        p1_prizes_rem = 0
    elif (r2 or 0) > (r1 or 0):
        winner_idx = 1
        p2_prizes_rem = 0

    if winner_idx is None:
        if p1_prizes_rem < p2_prizes_rem: winner_idx = 0
        elif p2_prizes_rem < p1_prizes_rem: winner_idx = 1
        else: winner_idx = -1

    p1_prizes_taken = max(0, min(6, 6 - p1_prizes_rem))
    p2_prizes_taken = max(0, min(6, 6 - p2_prizes_rem))
    return winner_idx, p1_prizes_taken, p2_prizes_taken, p1_dmg_given, p1_dmg_taken

def evaluate_genome(env, genome):
    """Evaluate individual genome fitness across 4 games per opponent (2 P1, 2 P2) against meta gauntlet."""
    update_agent_weights(genome)
    
    total_fitness = 0.0
    total_my_prizes = 0
    total_opp_prizes = 0
    total_dmg_given = 0
    total_dmg_taken = 0
    total_wins = 0
    total_games = 0

    n_p1_games = GAMES_PER_OPPONENT // 2
    n_p2_games = GAMES_PER_OPPONENT - n_p1_games

    for opp_name, opp_agent in opponents:
        # P1 Matches
        for _ in range(n_p1_games):
            w1, p1_taken, p2_taken, d_given1, d_taken1 = evaluate_match(env, v2_main.agent, opp_agent)
            my_p1 = p1_taken
            opp_p1 = p2_taken
            won1 = (w1 == 0)
            
            # Direct Prize Ratio Maximizer: (Prizes_Taken + 0.01) / (Prizes_Conceded + 0.01)
            ratio1 = (my_p1 + 0.01) / (opp_p1 + 0.01)
            fit1 = (W_RATIO_MULT * ratio1) + (W_TAKEN_MULT * my_p1) - (W_CONCEDED_MULT * opp_p1) + (W_DMG_GIVEN_MULT * d_given1) - (W_DMG_TAKEN_MULT * d_taken1) + (W_WIN_BONUS if won1 else 0.0)

            total_fitness += fit1
            total_my_prizes += my_p1
            total_opp_prizes += opp_p1
            total_dmg_given += d_given1
            total_dmg_taken += d_taken1
            if won1: total_wins += 1
            total_games += 1

        # P2 Matches
        for _ in range(n_p2_games):
            w2, p1_taken, p2_taken, d_given2, d_taken2 = evaluate_match(env, opp_agent, v2_main.agent)
            my_p2 = p2_taken
            opp_p2 = p1_taken
            won2 = (w2 == 1)

            # Direct Prize Ratio Maximizer: (Prizes_Taken + 0.01) / (Prizes_Conceded + 0.01)
            ratio2 = (my_p2 + 0.01) / (opp_p2 + 0.01)
            fit2 = (W_RATIO_MULT * ratio2) + (W_TAKEN_MULT * my_p2) - (W_CONCEDED_MULT * opp_p2) + (W_DMG_GIVEN_MULT * d_given2) - (W_DMG_TAKEN_MULT * d_taken2) + (W_WIN_BONUS if won2 else 0.0)

            total_fitness += fit2
            total_my_prizes += my_p2
            total_opp_prizes += opp_p2
            total_dmg_given += d_given2
            total_dmg_taken += d_taken2
            if won2: total_wins += 1
            total_games += 1

    avg_fitness = total_fitness / max(1, total_games)
    avg_my_prizes = total_my_prizes / max(1, total_games)
    avg_opp_prizes = total_opp_prizes / max(1, total_games)
    avg_dmg_given = total_dmg_given / max(1, total_games)
    avg_dmg_taken = total_dmg_taken / max(1, total_games)
    win_rate = (total_wins / max(1, total_games)) * 100.0

    return avg_fitness, win_rate, avg_my_prizes, avg_opp_prizes, avg_dmg_given, avg_dmg_taken

def mutate(genome):
    """Apply Gaussian mutation to genome parameters."""
    child = copy.deepcopy(genome)
    for k in child:
        if k in {"VERSION", "generation_stats"} or not isinstance(child[k], (int, float)):
            continue
        if random.random() < MUTATION_RATE:
            orig = child[k]
            delta = random.gauss(0, max(1.0, abs(orig) * MUTATION_STDEV))
            new_val = orig + delta
            if orig > 0 and new_val <= 0:
                new_val = orig * 0.1
            child[k] = type(orig)(new_val)
    return child

def crossover(parent1, parent2):
    """Uniform crossover between two parent genomes."""
    child = copy.deepcopy(parent1)
    for k in child:
        if k in parent2 and random.random() < 0.5:
            child[k] = parent2[k]
    return child

def save_best_genome(best_genome, fitness, win_rate, my_pz, opp_pz, dmg_g, dmg_t, gen, total_games_so_far):
    """Continuously save best genome to optimized_weights.json and timestamped checkpoints."""
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    best_genome["VERSION"] = f"V2_GA_Gen{gen}_Games{total_games_so_far}_{timestamp}"
    best_genome["generation_stats"] = {
        "generation": gen,
        "total_games_evaluated": total_games_so_far,
        "fitness": fitness,
        "win_rate": win_rate,
        "avg_my_prizes": my_pz,
        "avg_opp_prizes": opp_pz,
        "prize_ratio": (my_pz + 0.01) / (opp_pz + 0.01),
        "avg_damage_given": dmg_g,
        "avg_damage_taken": dmg_t,
        "updated_at": timestamp
    }
    
    # 1. Main optimized_weights.json
    json_path = os.path.join(_this_dir, "optimized_weights.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(best_genome, f, indent=2)

    # 2. Checkpoint JSON File
    chk_path = os.path.join(CHECKPOINT_DIR, f"weights_gen{gen:03d}_fit{int(fitness)}.json")
    with open(chk_path, 'w', encoding='utf-8') as f:
        json.dump(best_genome, f, indent=2)

    log_ga_history(f"  [SAVED WEIGHTS] Updated {json_path} & Checkpoint {chk_path} (Gen {gen} | Games {total_games_so_far:,})")

def build_final_submission_tarball():
    """Build submission.tar.gz once at the end of optimization."""
    sub_path = os.path.join(_this_dir, "submission.tar.gz")
    cg_dir = os.path.join(_network_training_dir, "cg")
    v_files = ['main.py', 'deck.csv', '__init__.py', 'optimized_weights.json']
    try:
        with tarfile.open(sub_path, 'w:gz') as tar:
            for f in v_files:
                full = os.path.join(_this_dir, f)
                if os.path.exists(full):
                    tar.add(full, arcname=f)
            if os.path.exists(cg_dir):
                for root, dirs, files in os.walk(cg_dir):
                    for file in files:
                        fp = os.path.join(root, file)
                        tar.add(fp, arcname=fp.replace(os.sep, '/'))
        log_ga_history(f"\n[FINAL SUBMISSION ARCHIVE] Successfully built {sub_path} ({os.path.getsize(sub_path):,} bytes)")
    except Exception as e:
        log_ga_history(f"\n[Warning] Could not rebuild submission tar.gz: {e}")

def run_ga():
    env = make('cabt', debug=False)
    
    # Load existing optimized weights if available to resume training seamlessly
    base_genome = dict(v2_main._WEIGHT_DEFAULTS)
    existing_weights_path = os.path.join(_this_dir, "optimized_weights.json")
    if os.path.exists(existing_weights_path):
        try:
            with open(existing_weights_path) as f:
                loaded = json.load(f)
                base_genome.update({k: v for k, v in loaded.items() if k in v2_main._WEIGHT_DEFAULTS})
            log_ga_history(f"Loaded existing weights from {existing_weights_path} as base genome.")
        except Exception:
            pass

    # Initialize Population
    population = [copy.deepcopy(base_genome)]
    for _ in range(POPULATION_SIZE - 1):
        population.append(mutate(base_genome))

    games_per_indiv = len(opponents) * GAMES_PER_OPPONENT
    games_per_gen = POPULATION_SIZE * games_per_indiv
    total_target_games = GENERATIONS * games_per_gen

    log_ga_history(f"=== Starting 100,000 Game Multi-Game Genetic Algorithm Optimization for Wall_V10 V2 ===")
    log_ga_history(f"  Population Size:       {POPULATION_SIZE}")
    log_ga_history(f"  Generations:           {GENERATIONS}")
    log_ga_history(f"  Games per Candidate:   {games_per_indiv} ({GAMES_PER_OPPONENT} per opponent -> zero luck variance!)")
    log_ga_history(f"  Top 5% Elite Count:    {TOP_5_PCT_COUNT} (Only top 5% of bots breed children)")
    log_ga_history(f"  Games per Generation:  {games_per_gen}")
    log_ga_history(f"  Total Target Games:    {total_target_games:,}")
    log_ga_history(f"  Prize Ratio Mult:      +{W_RATIO_MULT}x (MAXIMIZES Prize Capture Ratio)")
    log_ga_history(f"  Prize Taken Mult:      +{W_TAKEN_MULT}x")
    log_ga_history(f"  Prize Conceded:       -{W_CONCEDED_MULT}x (Heavy Penalty)")
    log_ga_history(f"  Damage Given Mult:     +{W_DMG_GIVEN_MULT}x")
    log_ga_history(f"  Damage Taken Mult:     -{W_DMG_TAKEN_MULT}x")
    log_ga_history(f"  Win Bonus:            +{W_WIN_BONUS}x")
    log_ga_history(f"===============================================================================================\n")

    best_overall_genome = None
    best_overall_fitness = -float('inf')
    cum_games = 0

    for gen in range(1, GENERATIONS + 1):
        log_ga_history(f"--- Generation {gen}/{GENERATIONS} (Progress: {cum_games:,}/{total_target_games:,} games) ---")
        eval_results = []

        for idx, genome in enumerate(population):
            fit, wr, my_pz, opp_pz, dmg_g, dmg_t = evaluate_genome(env, genome)
            cum_games += games_per_indiv
            p_ratio = (my_pz + 0.01) / (opp_pz + 0.01)
            eval_results.append((fit, wr, my_pz, opp_pz, dmg_g, dmg_t, genome))
            log_ga_history(f"  Indiv {idx+1:02d}/{POPULATION_SIZE} (Game {cum_games:,}) -> Fit: {fit:+.1f} | WinRate: {wr:.1f}% | PrizeRatio: {p_ratio:.2f} (Us: {my_pz:.2f}, Opp: {opp_pz:.2f}) | Damage (Given: {dmg_g:.0f}, Taken: {dmg_t:.0f})")

        # Sort population by fitness (descending)
        eval_results.sort(key=lambda x: x[0], reverse=True)
        best_gen_fit, best_gen_wr, best_gen_mypz, best_gen_opppz, best_gen_dmgg, best_gen_dmgt, best_gen_genome = eval_results[0]

        best_p_ratio = (best_gen_mypz + 0.01) / (best_gen_opppz + 0.01)
        log_ga_history(f"--> Gen {gen} Best -> Fit: {best_gen_fit:+.1f} | WinRate: {best_gen_wr:.1f}% | PrizeRatio: {best_p_ratio:.2f} (Us: {best_gen_mypz:.2f}, Opp: {best_gen_opppz:.2f}) | Damage (Given: {best_gen_dmgg:.0f}, Taken: {best_gen_dmgt:.0f})")

        # CONTINUOUS SAVING: Save weights immediately whenever a new best fitness is reached
        if best_gen_fit > best_overall_fitness:
            best_overall_fitness = best_gen_fit
            best_overall_genome = copy.deepcopy(best_gen_genome)
            save_best_genome(best_overall_genome, best_gen_fit, best_gen_wr, best_gen_mypz, best_gen_opppz, best_gen_dmgg, best_gen_dmgt, gen, cum_games)

        # ── TOP 5% SELECTION & ELITE BREEDING ──
        elite_parents = [eval_results[i][6] for i in range(TOP_5_PCT_COUNT)]
        new_population = [copy.deepcopy(p) for p in elite_parents]

        # Breed remaining population ONLY using Top 5% parents!
        while len(new_population) < POPULATION_SIZE:
            p1 = random.choice(elite_parents)
            p2 = random.choice(elite_parents)
            child = crossover(p1, p2)
            child = mutate(child)
            new_population.append(child)

        population = new_population
        log_ga_history("")

    # Build final submission tarball ONLY at the end of optimization!
    build_final_submission_tarball()

    log_ga_history("=== 100,000 Game GA Optimization Completed Successfully ===")
    log_ga_history(f"Best Overall Fitness: {best_overall_fitness:+.2f}")

if __name__ == '__main__':
    run_ga()

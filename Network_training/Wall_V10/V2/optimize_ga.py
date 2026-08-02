"""
optimize_ga.py — Genetic Algorithm Optimizer for Wall_V10 V2
============================================================
Optimizes weight parameters in optimized_weights.json against meta gauntlet.

Multi-Objective Fitness Objective:
  1. Maximizes Prize Cards Taken Us (+1000.0x per prize)
  2. Heavily Penalizes Prize Cards Conceded Opponent (-2500.0x per prize)
  3. Maximizes Total HP Damage Given (+1.0x per HP damage dealt)
  4. Minimizes Total HP Damage Taken (-1.5x per HP damage received)
  5. Win Bonus (+5000.0x per victory)
"""

import os
import sys
import json
import random
import copy
import time
import tarfile
from kaggle_environments import make

# ── Path Setup ─────────────────────────────────────────────────────────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_network_training_dir = os.path.abspath(os.path.join(_this_dir, '..', '..'))
if _network_training_dir not in sys.path:
    sys.path.insert(0, _network_training_dir)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

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

# ── Fitness Multi-Objective Weight Config ──────────────────────────────────
W_TAKEN_MULT     = float(os.environ.get("GA_W_TAKEN", "1000.0"))
W_CONCEDED_MULT  = float(os.environ.get("GA_W_CONCEDED", "2500.0")) # Heavy penalty for losing prizes!
W_DMG_GIVEN_MULT = float(os.environ.get("GA_W_DMG_GIVEN", "1.0"))   # Reward for dealing damage!
W_DMG_TAKEN_MULT = float(os.environ.get("GA_W_DMG_TAKEN", "1.5"))   # Penalty for taking damage!
W_WIN_BONUS      = float(os.environ.get("GA_W_WIN_BONUS", "5000.0"))

POPULATION_SIZE = int(os.environ.get("GA_POP_SIZE", "8"))
GENERATIONS     = int(os.environ.get("GA_GENERATIONS", "15"))
MUTATION_RATE   = float(os.environ.get("GA_MUTATION_RATE", "0.20"))
MUTATION_STDEV  = float(os.environ.get("GA_MUTATION_STDEV", "0.15"))
ELITISM         = int(os.environ.get("GA_ELITISM", "2"))

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
    """Evaluate individual genome fitness against meta gauntlet opponents."""
    update_agent_weights(genome)
    
    total_fitness = 0.0
    total_my_prizes = 0
    total_opp_prizes = 0
    total_dmg_given = 0
    total_dmg_taken = 0
    total_wins = 0
    total_games = 0

    for opp_name, opp_agent in opponents:
        # Match 1: Bot as Player 1
        w1, p1_taken, p2_taken, d_given1, d_taken1 = evaluate_match(env, v2_main.agent, opp_agent)
        my_p1 = p1_taken
        opp_p1 = p2_taken
        won1 = (w1 == 0)
        fit1 = (W_TAKEN_MULT * my_p1) - (W_CONCEDED_MULT * opp_p1) + (W_DMG_GIVEN_MULT * d_given1) - (W_DMG_TAKEN_MULT * d_taken1) + (W_WIN_BONUS if won1 else 0.0)

        # Match 2: Bot as Player 2
        w2, p1_taken, p2_taken, d_given2, d_taken2 = evaluate_match(env, opp_agent, v2_main.agent)
        my_p2 = p2_taken
        opp_p2 = p1_taken
        won2 = (w2 == 1)
        fit2 = (W_TAKEN_MULT * my_p2) - (W_CONCEDED_MULT * opp_p2) + (W_DMG_GIVEN_MULT * d_given2) - (W_DMG_TAKEN_MULT * d_taken2) + (W_WIN_BONUS if won2 else 0.0)

        total_fitness += (fit1 + fit2)
        total_my_prizes += (my_p1 + my_p2)
        total_opp_prizes += (opp_p1 + opp_p2)
        total_dmg_given += (d_given1 + d_given2)
        total_dmg_taken += (d_taken1 + d_taken2)
        total_wins += (1 if won1 else 0) + (1 if won2 else 0)
        total_games += 2

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

def save_best_genome(best_genome, fitness, win_rate, my_pz, opp_pz, dmg_g, dmg_t, gen):
    """Save best genome to optimized_weights.json and rebuild submission.tar.gz."""
    best_genome["VERSION"] = f"V2_GA_Gen{gen}_{time.strftime('%Y%m%d_%H%M%S')}"
    best_genome["generation_stats"] = {
        "generation": gen,
        "fitness": fitness,
        "win_rate": win_rate,
        "avg_my_prizes": my_pz,
        "avg_opp_prizes": opp_pz,
        "avg_damage_given": dmg_g,
        "avg_damage_taken": dmg_t
    }
    
    json_path = os.path.join(_this_dir, "optimized_weights.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(best_genome, f, indent=2)
    print(f"  [Saved] Updated {json_path} (Gen {gen})", flush=True)

    # Rebuild submission archive
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
        print(f"  [Saved] Rebuilt submission archive {sub_path} ({os.path.getsize(sub_path):,} bytes)", flush=True)
    except Exception as e:
        print(f"  [Warning] Could not rebuild submission tar.gz: {e}")

def run_ga():
    env = make('cabt', debug=False)
    
    base_genome = dict(v2_main._WEIGHT_DEFAULTS)

    # Initialize Population
    population = [copy.deepcopy(base_genome)]
    for _ in range(POPULATION_SIZE - 1):
        population.append(mutate(base_genome))

    print(f"=== Starting Multi-Objective Genetic Algorithm Optimization for Wall_V10 V2 ===", flush=True)
    print(f"  Population Size:   {POPULATION_SIZE}", flush=True)
    print(f"  Generations:       {GENERATIONS}", flush=True)
    print(f"  Prize Taken Mult:  +{W_TAKEN_MULT}x", flush=True)
    print(f"  Prize Conceded:   -{W_CONCEDED_MULT}x (Heavy Penalty)", flush=True)
    print(f"  Damage Given Mult: +{W_DMG_GIVEN_MULT}x (Maximize HP Damage Dealt)", flush=True)
    print(f"  Damage Taken Mult: -{W_DMG_TAKEN_MULT}x (Minimize HP Damage Taken)", flush=True)
    print(f"  Win Bonus:        +{W_WIN_BONUS}x", flush=True)
    print(f"=================================================================================\n", flush=True)

    best_overall_genome = None
    best_overall_fitness = -float('inf')

    for gen in range(1, GENERATIONS + 1):
        print(f"--- Generation {gen}/{GENERATIONS} ---", flush=True)
        eval_results = []

        for idx, genome in enumerate(population):
            fit, wr, my_pz, opp_pz, dmg_g, dmg_t = evaluate_genome(env, genome)
            eval_results.append((fit, wr, my_pz, opp_pz, dmg_g, dmg_t, genome))
            print(f"  Indiv {idx+1}/{POPULATION_SIZE} -> Fit: {fit:+.1f} | WinRate: {wr:.1f}% | Prizes (Us: {my_pz:.2f}, Opp: {opp_pz:.2f}) | Damage (Given: {dmg_g:.0f}, Taken: {dmg_t:.0f})", flush=True)

        # Sort population by fitness (descending)
        eval_results.sort(key=lambda x: x[0], reverse=True)
        best_gen_fit, best_gen_wr, best_gen_mypz, best_gen_opppz, best_gen_dmgg, best_gen_dmgt, best_gen_genome = eval_results[0]

        print(f"Gen {gen} Best -> Fit: {best_gen_fit:+.1f} | WinRate: {best_gen_wr:.1f}% | Prizes (Us: {best_gen_mypz:.2f}, Opp: {best_gen_opppz:.2f}) | Damage (Given: {best_gen_dmgg:.0f}, Taken: {best_gen_dmgt:.0f})", flush=True)

        if best_gen_fit > best_overall_fitness:
            best_overall_fitness = best_gen_fit
            best_overall_genome = copy.deepcopy(best_gen_genome)
            save_best_genome(best_overall_genome, best_gen_fit, best_gen_wr, best_gen_mypz, best_gen_opppz, best_gen_dmgg, best_gen_dmgt, gen)

        # Selection & Reproduction for next generation
        new_population = []
        # Elitism
        for i in range(min(ELITISM, len(eval_results))):
            new_population.append(copy.deepcopy(eval_results[i][6]))

        # Breed remaining population
        while len(new_population) < POPULATION_SIZE:
            p1 = max(random.sample(eval_results, 3), key=lambda x: x[0])[6]
            p2 = max(random.sample(eval_results, 3), key=lambda x: x[0])[6]
            child = crossover(p1, p2)
            child = mutate(child)
            new_population.append(child)

        population = new_population
        print("", flush=True)

    print("=== Multi-Objective GA Optimization Completed Successfully ===", flush=True)
    print(f"Best Overall Fitness: {best_overall_fitness:+.2f}", flush=True)

if __name__ == '__main__':
    run_ga()

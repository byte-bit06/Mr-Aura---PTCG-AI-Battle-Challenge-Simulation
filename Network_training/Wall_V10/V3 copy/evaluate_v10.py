"""
evaluate_v10.py — Evaluation Harness & GA Fitness Evaluator
===========================================================
Runs matches of Wall_V10 against Meta Gauntlet opponents.
Calculates:
  - Win Rate %
  - Average Prizes Taken by Wall_V10 [0 - 6]
  - Average Prizes Conceded to Opponent [0 - 6]
  - Prize Differential Score = (Prizes Taken Us - Prizes Conceded Opponent)
"""

import os
import sys
import json
import importlib

# ── Path setup: ensure Network_training is on sys.path ───────────────────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_network_training_dir = os.path.abspath(os.path.join(_this_dir, '..', '..'))
if _network_training_dir not in sys.path:
    sys.path.insert(0, _network_training_dir)

from kaggle_environments import make

# ── Patch Kaggle Environment to use local C++ DLL with full card database ────
import cg.game as local_game
import cg.sim as local_sim
import kaggle_environments.envs.cabt.cabt as cabt_mod

cabt_mod.battle_start = local_game.battle_start
cabt_mod.battle_select = local_game.battle_select
cabt_mod.battle_finish = local_game.battle_finish
cabt_mod.visualize_data = local_game.visualize_data
cabt_mod.Battle = local_sim.Battle

# Path setup for opponents
_opp_dir = os.path.join(_network_training_dir, 'opponents')
if _opp_dir not in sys.path:
    sys.path.insert(0, _opp_dir)

import Wall_V10.main as v10_module
primary_agent = v10_module.agent
primary_name = "Wall_V10"

import lucario_agent
import iono_agent
import dragapult_agent
import abomasnow_agent
import mcts_lucario_agent
import archaludon_cinderace_agent

# Meta Gauntlet Opponents (Past models Wall_V1 & Wall_V6 removed per directive)
opponents = {
    'Lucario ex': lucario_agent.agent,
    'Iono Deck': iono_agent.agent,
    'Dragapult ex': dragapult_agent.agent,
    'Abomasnow ex': abomasnow_agent.agent,
    'MCTS Lucario': mcts_lucario_agent.agent,
    'Archaludon Cinderace': archaludon_cinderace_agent.agent,
}

try:
    import alakazam_agent
    opponents['Alakazam ex V31'] = alakazam_agent.agent
except ImportError:
    pass

replays_dir = os.path.join(os.path.dirname(__file__), 'replays')
os.makedirs(replays_dir, exist_ok=True)

def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    print(f'Match: {p1_name} vs {p2_name} ({match_name})', flush=True)
    steps = env.run([p1_agent, p2_agent])
    last_step = steps[-1]
    
    r1 = last_step[0].get("reward", 0) if isinstance(last_step[0], dict) else 0
    r2 = last_step[1].get("reward", 0) if (len(last_step) > 1 and isinstance(last_step[1], dict)) else 0
    
    winner = None
    p1_prizes_remaining = 6
    p2_prizes_remaining = 6

    # Extract final remaining prize counts from observation
    for agent_step in last_step:
        if isinstance(agent_step, dict):
            obs = agent_step.get("observation") or {}
            curr = obs.get("current") or {}
            players = curr.get("players") or []
            if len(players) >= 2:
                if isinstance(players[0], dict):
                    pz = players[0].get("prize") or players[0].get("prizes")
                    p1_prizes_remaining = len(pz) if isinstance(pz, list) else int(pz or 6)
                if isinstance(players[1], dict):
                    pz = players[1].get("prize") or players[1].get("prizes")
                    p2_prizes_remaining = len(pz) if isinstance(pz, list) else int(pz or 6)

    # Determine winner based on environment reward signals
    if (r1 or 0) > (r2 or 0):
        winner = p1_name
        p1_prizes_remaining = 0
    elif (r2 or 0) > (r1 or 0):
        winner = p2_name
        p2_prizes_remaining = 0

    if not winner:
        if p1_prizes_remaining < p2_prizes_remaining:
            winner = p1_name
        elif p2_prizes_remaining < p1_prizes_remaining:
            winner = p2_name
        else:
            winner = "Tie"

    # Calculate actual prizes taken (out of 6)
    p1_prizes_taken = max(0, min(6, 6 - p1_prizes_remaining))
    p2_prizes_taken = max(0, min(6, 6 - p2_prizes_remaining))

    # Save replay JSON
    try:
        replay_path = os.path.join(replays_dir, f"{match_name}.json")
        with open(replay_path, 'w', encoding='utf-8') as f:
            json.dump(env.toJSON(), f)
    except Exception: pass

    html = env.render(mode='html')
    replay_path = os.path.join(replays_dir, f'{match_name}.html')
    with open(replay_path, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f'  -> Winner: {winner} | {p1_name} Prizes: {p1_prizes_taken}/6 | {p2_name} Prizes: {p2_prizes_taken}/6 (Steps: {len(steps)})', flush=True)
    return winner, p1_prizes_taken, p2_prizes_taken

def main():
    env = make('cabt', debug=False)
    results = {}
    
    print(f'Starting Meta Gauntlet evaluations for {primary_name}...', flush=True)
    
    num_trials = 10
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        num_trials = int(sys.argv[1])
    elif "TRIALS_PER_OPPONENT" in os.environ:
        try: num_trials = int(os.environ["TRIALS_PER_OPPONENT"])
        except: pass

    total_my_prizes = 0
    total_opp_prizes = 0

    for opp_name, opp_agent in opponents.items():
        results[opp_name] = {'win': 0, 'loss': 0, 'tie': 0, 'my_prizes': 0, 'opp_prizes': 0}
        for i in range(num_trials):
            clean_name = opp_name.replace(' ', '').replace('(', '').replace(')', '')
            
            if i % 2 == 0:
                winner, my_pz, opp_pz = play_match(env, primary_name, primary_agent, opp_name, opp_agent, f'{primary_name}_vs_{clean_name}_{i+1}')
            else:
                winner, opp_pz, my_pz = play_match(env, opp_name, opp_agent, primary_name, primary_agent, f'{clean_name}_vs_{primary_name}_{i+1}')
                
            results[opp_name]['my_prizes'] += my_pz
            results[opp_name]['opp_prizes'] += opp_pz
            total_my_prizes += my_pz
            total_opp_prizes += opp_pz

            if winner == primary_name:
                results[opp_name]['win'] += 1
            elif winner == opp_name:
                results[opp_name]['loss'] += 1
            else:
                results[opp_name]['tie'] += 1
            
    print('\n=== FINAL V10 META GAUNTLET EVALUATION RESULTS ===', flush=True)
    total_wins = 0
    total_losses = 0
    total_ties = 0

    for opp_name, stats in results.items():
        n_games = stats['win'] + stats['loss'] + stats['tie']
        avg_my_pz = stats['my_prizes'] / max(1, n_games)
        avg_opp_pz = stats['opp_prizes'] / max(1, n_games)
        diff = avg_my_pz - avg_opp_pz
        print(f"vs {opp_name}: {stats['win']} Wins, {stats['loss']} Losses, {stats['tie']} Ties | Avg Prizes ({primary_name}: {avg_my_pz:.2f}, Opp: {avg_opp_pz:.2f}, Diff: {diff:+.2f})", flush=True)
        total_wins += stats['win']
        total_losses += stats['loss']
        total_ties += stats['tie']

    total_games = total_wins + total_losses + total_ties
    win_rate = (total_wins / max(1, total_wins + total_losses)) * 100
    overall_avg_my_pz = total_my_prizes / max(1, total_games)
    overall_avg_opp_pz = total_opp_prizes / max(1, total_games)
    overall_prize_diff = overall_avg_my_pz - overall_avg_opp_pz

    print(f"\n[Meta Gauntlet Summary]", flush=True)
    print(f"  Total Games Evaluated: {total_games}", flush=True)
    print(f"  Overall Win Rate:      {win_rate:.1f}%", flush=True)
    print(f"  Avg Prizes Taken (Us): {overall_avg_my_pz:.2f} / 6.00", flush=True)
    print(f"  Avg Prizes Conceded:   {overall_avg_opp_pz:.2f} / 6.00", flush=True)
    print(f"  Prize Differential:    {overall_prize_diff:+.2f}", flush=True)

if __name__ == '__main__':
    main()

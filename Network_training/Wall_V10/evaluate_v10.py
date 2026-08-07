"""
evaluate_v10.py — Evaluation Harness for Wall_V10 Replay-Adapted Agent
========================================================================
Runs matches of Wall_V10 against Meta Gauntlet, Alakazam ex V21, and baseline versions.
Calculates overall Win Rate % and saves HTML battle replays.
"""

import os
import sys
import json
import importlib

# Ensure parent directory and current directory are in sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
cur_dir = os.path.abspath(os.path.dirname(__file__))
if cur_dir not in sys.path:
    sys.path.insert(0, cur_dir)

from kaggle_environments import make

# ── Patch Kaggle Environment to use local C++ DLL with full card database ────
try:
    import cg.game as local_game
    import cg.sim as local_sim
    import kaggle_environments.envs.cabt.cabt as cabt_mod
    cabt_mod.battle_start = local_game.battle_start
    cabt_mod.battle_select = local_game.battle_select
    cabt_mod.battle_finish = local_game.battle_finish
    cabt_mod.visualize_data = local_game.visualize_data
    cabt_mod.Battle = local_sim.Battle
except Exception:
    pass

# Path setup for opponents directory (check both local and parent)
opp_parent = os.path.abspath(os.path.join(parent_dir, 'opponents'))
if opp_parent not in sys.path:
    sys.path.insert(0, opp_parent)
opp_local = os.path.abspath(os.path.join(os.path.dirname(__file__), 'opponents'))
if opp_local not in sys.path:
    sys.path.insert(0, opp_local)

import Wall_V10.main as v10_module
primary_agent = v10_module.agent
primary_name = "Wall_V10"

import lucario_agent
import iono_agent
import dragapult_agent
import abomasnow_agent
import mcts_lucario_agent
import archaludon_cinderace_agent

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
    opponents['Alakazam ex V21'] = alakazam_agent.agent
except ImportError:
    pass

try:
    import Wall_V1.main as v1_module
    opponents['Wall_V1 (Baseline)'] = v1_module.agent
except Exception: pass

try:
    import Wall_V6.main as v6_module
    opponents['Wall_V6 (Previous)'] = v6_module.agent
except Exception: pass

replays_dir = os.path.join(os.path.dirname(__file__), 'replays')
os.makedirs(replays_dir, exist_ok=True)

def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    print(f'Match: {p1_name} vs {p2_name} ({match_name})', flush=True)
    steps = env.run([p1_agent, p2_agent])
    last_step = steps[-1]
    
    r1 = last_step[0].get("reward", 0) if isinstance(last_step[0], dict) else 0
    r2 = last_step[1].get("reward", 0) if (len(last_step) > 1 and isinstance(last_step[1], dict)) else 0
    
    winner = None

    # 1. Check reward
    if (r1 or 0) > (r2 or 0):
        winner = p1_name
    elif (r2 or 0) > (r1 or 0):
        winner = p2_name

    # 2. Check logs & prizes if tie
    if not winner:
        p1_prizes = 6
        p2_prizes = 6
        for agent_step in last_step:
            if isinstance(agent_step, dict):
                obs = agent_step.get("observation") or {}
                logs = obs.get("logs") or []
                for log in logs:
                    log_s = str(log).lower()
                    if "won" in log_s or "winner" in log_s or "victory" in log_s:
                        if "player 0" in log_s or "p0" in log_s:
                            winner = p1_name
                        elif "player 1" in log_s or "p1" in log_s:
                            winner = p2_name

                curr = obs.get("current") or {}
                players = curr.get("players") or []
                if len(players) >= 2:
                    if isinstance(players[0], dict):
                        p1_prizes = players[0].get("prizes", 6)
                    if isinstance(players[1], dict):
                        p2_prizes = players[1].get("prizes", 6)

        if not winner:
            if p1_prizes < p2_prizes:
                winner = p1_name
            elif p2_prizes < p1_prizes:
                winner = p2_name
            else:
                winner = "Tie"

    # Save replay JSON for user inspection
    try:
        replay_path = os.path.join(replays_dir, f"{match_name}.json")
        with open(replay_path, 'w', encoding='utf-8') as f:
            json.dump(env.toJSON(), f)
    except Exception as e:
        print(f"Could not save replay {match_name}: {e}")

    html = env.render(mode='html')
    replay_path = os.path.join(replays_dir, f'{match_name}.html')
    with open(replay_path, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f'  -> Winner: {winner} (Steps: {len(steps)})', flush=True)
    return winner

def main():
    env = make('cabt', debug=False)
    results = {}
    
    print(f'Starting evaluations for {primary_name} (Replay-Adapted AI)...', flush=True)
    
    for opp_name, opp_agent in opponents.items():
        results[opp_name] = {'win': 0, 'loss': 0, 'tie': 0}
        for i in range(10):
            clean_name = opp_name.replace(' ', '').replace('(', '').replace(')', '')
            
            if i % 2 == 0:
                winner = play_match(env, primary_name, primary_agent, opp_name, opp_agent, f'{primary_name}_vs_{clean_name}_{i+1}')
            else:
                winner = play_match(env, opp_name, opp_agent, primary_name, primary_agent, f'{clean_name}_vs_{primary_name}_{i+1}')
                
            if winner == primary_name:
                results[opp_name]['win'] += 1
            elif winner == opp_name:
                results[opp_name]['loss'] += 1
            else:
                results[opp_name]['tie'] += 1
            
    print('\n=== FINAL V10 EVALUATION RESULTS ===', flush=True)
    total_wins = 0
    total_losses = 0
    total_ties = 0

    for opp_name, stats in results.items():
        print(f"vs {opp_name}: {stats['win']} Wins, {stats['loss']} Losses, {stats['tie']} Ties", flush=True)
        total_wins += stats['win']
        total_losses += stats['loss']
        total_ties += stats['tie']

    total_games = total_wins + total_losses + total_ties
    win_rate = (total_wins / max(1, total_wins + total_losses)) * 100
    print(f"\n[Summary] Total Games: {total_games} | Overall Win Rate: {win_rate:.1f}%", flush=True)

if __name__ == '__main__':
    main()

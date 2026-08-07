import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), 'opponents'))
from kaggle_environments import make

import alakazam_agent
primary_agent = alakazam_agent.agent
primary_name = "Alakazam_ex_V21"

import lucario_agent
import iono_agent
import dragapult_agent
import abomasnow_agent
import mcts_lucario_agent
import archaludon_cinderace_agent
import Wall_V5.main as v5_module
import Wall_V6.main as v6_module
import Wall_V7.main as v7_module

opponents = {
    'Lucario ex': lucario_agent.agent,
    'Iono Deck': iono_agent.agent,
    'Dragapult ex': dragapult_agent.agent,
    'Abomasnow ex': abomasnow_agent.agent,
    'MCTS Lucario': mcts_lucario_agent.agent,
    'Archaludon Cinderace': archaludon_cinderace_agent.agent,
    'Wall_V7': v7_module.agent,
    'Wall_V6': v6_module.agent,
    'Wall_V5': v5_module.agent,
}

if not os.path.exists('replays'):
    os.makedirs('replays')

def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    print(f'Match: {p1_name} vs {p2_name} ({match_name})', flush=True)
    steps = env.run([p1_agent, p2_agent])
    r1 = steps[-1][0].reward
    r2 = steps[-1][1].reward
    
    if r1 == 1:
        winner = p1_name
    elif r2 == 1:
        winner = p2_name
    else:
        winner = 'Tie'
        
    print(f'Winner: {winner}', flush=True)
    return winner

def main():
    env = make('cabt', debug=False)
    results = {}
    
    print(f'Starting evaluations for {primary_name} against full meta gauntlet and Wall V5/V6/V7...', flush=True)
    
    for opp_name, opp_agent in opponents.items():
        results[opp_name] = {'win': 0, 'loss': 0, 'tie': 0}
        for i in range(10):
            clean_name = opp_name.replace(' ', '')
            
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
            
    print('\n=== ALAKAZAM EX V21 GAUNTLET RESULTS ===', flush=True)
    total_wins = 0
    total_losses = 0
    for opp_name, stats in results.items():
        print(f"vs {opp_name}: {stats['win']} Wins, {stats['loss']} Losses, {stats['tie']} Ties", flush=True)
        total_wins += stats['win']
        total_losses += stats['loss']
        
    print(f"\nOverall Win Rate: {(total_wins / max(1, total_wins + total_losses)) * 100:.1f}%")

if __name__ == '__main__':
    main()

import json
import os
import sys
import importlib.util

def load_agent(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

sys.path.append(os.path.join(os.path.dirname(__file__), 'opponents'))
from kaggle_environments import make

try:
    import Wall_V3.main as my_agent
    with open('Wall_V3/optimized_weights.json') as f:
         data = json.load(f)
         my_agent.W = data
except ImportError:
    import main as my_agent

ENV_NAME = "cabt"

wall_v1_agent = load_agent('main_backup_pre_training.py', 'wall_v1')
with open('optimized_weights_backup_pre_training.json') as f:
    wall_v1_agent.W = json.load(f)

wall_v2_agent = load_agent('Wall_V2/main.py', 'wall_v2')
with open('Wall_V2/optimized_weights.json') as f:
    wall_v2_agent.W = json.load(f)

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

if not os.path.exists('replays'):
    os.makedirs('replays')

def play_match(env, p1_name, p1_agent, p2_name, p2_agent, match_name):
    print(f'Match: {p1_name} vs {p2_name} ({match_name})', flush=True)
    steps = env.run([p1_agent, p2_agent])
    last_step = steps[-1]
    
    r1 = last_step[0].get("reward", 0) if isinstance(last_step[0], dict) else 0
    r2 = last_step[1].get("reward", 0) if (len(last_step) > 1 and isinstance(last_step[1], dict)) else 0
    
    html = env.render(mode='html')
    with open(f'replays/{match_name}.html', 'w', encoding='utf-8') as f:
        f.write(html)
        
    if (r1 or 0) > (r2 or 0):
        winner = p1_name
    elif (r2 or 0) > (r1 or 0):
        winner = p2_name
    else:
        winner = 'Tie'
        
    print(f'  -> Winner: {winner}', flush=True)
    return winner

def main():
    env = make('cabt', debug=False)
    results = {}
    
    print('Starting evaluations against Meta Gauntlet...', flush=True)
    for opp_name, opp_agent in opponents.items():
        results[opp_name] = {'win': 0, 'loss': 0, 'tie': 0}
        for i in range(2):
            clean_name = opp_name.replace(' ', '')
            winner = play_match(env, 'Wall_V1', wall_v1_agent.agent, opp_name, opp_agent, f'WallV1_vs_{clean_name}_{i+1}')
            if winner == 'Wall_V1':
                results[opp_name]['win'] += 1
            elif winner == opp_name:
                results[opp_name]['loss'] += 1
            else:
                results[opp_name]['tie'] += 1

    try:
        import Wall_V3.main as v3_module
        v3 = v3_module.agent
    except:
        v3 = my_agent.agent
        
    try:
        import Wall_V10.main as v10_module
        v10 = v10_module.agent
    except:
        v10 = my_agent.agent

    for v_name, v_agent in [('Wall_V2', wall_v2_agent.agent), ('Wall_V3', v3), ('Wall_V4', v4), ('Wall_V10', v10)]:
        print(f'\nStarting showdown against {v_name}...', flush=True)
        results[v_name] = {'win': 0, 'loss': 0, 'tie': 0}
        for i in range(3):
            if i % 2 == 0:
                winner = play_match(env, 'Wall_V1', wall_v1_agent.agent, v_name, v_agent, f'WallV1_vs_{v_name}_{i+1}')
            else:
                winner = play_match(env, v_name, v_agent, 'Wall_V1', wall_v1_agent.agent, f'{v_name}_vs_WallV1_{i+1}')
                
            if winner == 'Wall_V1':
                results[v_name]['win'] += 1
            elif winner == v_name:
                results[v_name]['loss'] += 1
            else:
                results[v_name]['tie'] += 1
            
    print('\n=== FINAL RESULTS ===', flush=True)
    for opp_name, stats in results.items():
        print(f"vs {opp_name}: {stats['win']} Wins, {stats['loss']} Losses, {stats['tie']} Ties", flush=True)

if __name__ == '__main__':
    main()

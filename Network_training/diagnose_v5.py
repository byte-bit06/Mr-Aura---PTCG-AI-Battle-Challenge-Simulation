import sys, os
sys.path.append('opponents')
from kaggle_environments import make
import Wall_V5.main as v5
import iono_agent
import abomasnow_agent
import Wall_V1.main as v1_module

opponents = {
    'Iono Deck': iono_agent.agent,
    'Abomasnow ex': abomasnow_agent.agent,
    'Wall_V1': v1_module.agent
}

env = make('cabt', debug=False)

for name, opp in opponents.items():
    print(f'=== Deep Diagnosis: Wall_V5 vs {name} ===')
    steps = env.run([v5.agent, opp])
    
    last_step = steps[-1]
    p0_res = last_step[0]
    p1_res = last_step[1]
    
    obs = p0_res.get('observation', {})
    current = obs.get('current', {})
    
    if current and current.get('players'):
        p0 = current['players'][0]
        p1 = current['players'][1]
        
        p0_prizes = len(p0.get('prize', []))
        p1_prizes = len(p1.get('prize', []))
        p0_active = p0.get('active', [{}])[0].get('id') if (p0.get('active') and p0['active'][0]) else None
        p1_active = p1.get('active', [{}])[0].get('id') if (p1.get('active') and p1['active'][0]) else None
        
        p0_bench_cnt = len([b for b in p0.get('bench', []) if b])
        p1_bench_cnt = len([b for b in p1.get('bench', []) if b])
        
        print(f"Outcome: V5 Reward={p0_res.get('reward')}, Opp Reward={p1_res.get('reward')}")
        print(f"Prizes Left: V5={p0_prizes}, Opponent={p1_prizes}")
        print(f"Active Card ID: V5={p0_active}, Opponent={p1_active}")
        print(f"Bench Count: V5={p0_bench_cnt}, Opponent={p1_bench_cnt}")
        print(f"Total Steps in match: {len(steps)}")
        print("-" * 50)

import sys
sys.path.insert(0, '.')
from kaggle_environments import make
import main

print('Running 1 test game...')
env = make('cabt')
try:
    env.run([main.agent, main.agent])
    r0 = env.state[0].reward
    r1 = env.state[1].reward
    s0 = env.state[0].status
    s1 = env.state[1].status
    print(f'Player 0: status={s0}, reward={r0}')
    print(f'Player 1: status={s1}, reward={r1}')
    if r0 > r1:   print('=> Player 0 wins!')
    elif r1 > r0: print('=> Player 1 wins!')
    else:         print('=> Draw/No result')
    print(f'Total steps: {len(env.steps)}')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback; traceback.print_exc()

"""
Get card names by running a game with main.py (which uses cg card db),
then printing every unique card it sees.
"""
import sys, json
sys.path.insert(0, '.')
sys.path.insert(0, 'C:/Users/Shaur/AppData/Local/Programs/Python/Python312/Lib/site-packages/kaggle_environments/envs/cabt')
from cg.game import battle_start, battle_finish, battle_select, _get_battle_data
from cg.sim import Battle

new_deck = [673,673,674,674,675,675,676,676,676,677,677,677,678,678,678,
            121,121,72,72,76,76,76,77,77,77,
            1102,1102,1102,1102,1123,1123,1141,1142,1142,1142,1142,
            1152,1152,1152,1152,1159,1182,1182,1192,1192,
            1227,1227,1227,1227,1252,1252,
            6,6,6,6,6,6,6,6,6]

ids_wanted = {72, 76, 77, 121}
found = {}

obs, start = battle_start(new_deck, new_deck)

# Step through setup phase - just pick first option always
for step in range(200):
    if not obs or not obs.get('select'):
        break
    result = obs['current'].get('result', -1)
    if result >= 0:
        break

    # Scan obs for our target cards
    for player in obs['current'].get('players', []):
        for zone in ['hand', 'active', 'bench', 'discard']:
            for card in (player.get(zone) or []):
                if card and card.get('id') in ids_wanted:
                    cid = card['id']
                    found[cid] = {
                        'name': card.get('name', '?'),
                        'hp': card.get('hp', '?'),
                        'cardType': card.get('cardType', '?'),
                        'stage1': card.get('stage1', False),
                        'stage2': card.get('stage2', False),
                        'ex': card.get('ex', False),
                        'megaEx': card.get('megaEx', False),
                        'weakness': card.get('weakness', '?'),
                    }

    sel = obs.get('select', {})
    opts = sel.get('option', []) if sel else []
    mc = sel.get('maxCount', 1) if sel else 1
    if not opts:
        break
    try:
        obs = battle_select(list(range(mc)))
    except Exception as e:
        break

    if all(cid in found for cid in ids_wanted):
        break

battle_finish()

print('=== New card IDs identified ===')
for cid in sorted(ids_wanted):
    if cid in found:
        info = found[cid]
        print(f'  id={cid:5d}  {info}')
    else:
        print(f'  id={cid:5d}  NOT SEEN (card may not appear in setup turns)')

print('\n=== Known cards (for reference) ===')
known = {673:'Makuhita', 674:'Hariyama', 675:'Lunatone', 676:'Solrock',
         677:'Riolu', 678:'Mega Lucario ex'}
for cid, name in known.items():
    print(f'  id={cid:5d}  {name}')

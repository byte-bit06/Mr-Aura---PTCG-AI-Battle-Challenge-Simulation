import sys, json
sys.path.insert(0, 'C:/Users/Shaur/AppData/Local/Programs/Python/Python312/Lib/site-packages/kaggle_environments/envs/cabt')
from cg.game import battle_start, battle_finish

text_deck = """
2 Lunatone ASC 105
1 Mega Lucario ex MEG 179
1 Meowth ex POR 121
3 Riolu MEP 10
1 Makuhita MEP 68
3 Solrock ASC 106
2 Mega Lucario ex MEG 188
1 Makuhita MEG 72
2 Hariyama MEG 73
2 Boss's Orders PAL 265
1 Black Belt's Training ASC 255
4 Fighting Gong MEG 168
4 Premium Power Pro MEG 174
2 Gravity Mountain SSP 250
4 Ultra Ball BRS 186
3 Air Balloon SSH 213
2 Judge SIT-TG 25
1 Special Red Card CRI 113
1 Unfair Stamp TWM 165
1 Team Rocket's Petrel DRI 226
4 Poké Pad POR 113
4 Lillie's Determination MEG 184
1 Wally's Compassion MEG 186
2 Basic {F} Energy CRE 233
7 Basic {F} Energy GRI 169
1 Rocky {F} Energy POR 87
"""

deck = []
for line in text_deck.strip().split('\n'):
    if not line.strip(): continue
    parts = line.split()
    count = int(parts[0])
    card_id = int(parts[-1])
    for _ in range(count):
        deck.append(card_id)

print('Extracted deck length:', len(deck))
print(deck)

try:
    obs, start = battle_start(deck, deck)
    if start.errorPlayer != -1:
        print("Error player:", start.errorPlayer)
    else:
        print("Battle started successfully!")
    battle_finish()
except Exception as e:
    print("Exception starting battle:", e)

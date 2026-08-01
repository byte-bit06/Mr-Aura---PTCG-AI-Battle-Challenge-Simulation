import pandas as pd
import sys

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

# The CSV has no header if we look closely, or maybe it does? 
# The snippet showed "111,Sandygast,TWM,91,..."
# Let's read the CSV and find the header
with open('EN_Card_Data.csv', 'r', encoding='utf-8') as f:
    header = f.readline().strip().split(',')
    print("Header:", header)

# If no header, we can define the columns based on the first few we care about:
# 0: ID, 1: Name, 2: Set, 3: Number
df = pd.read_csv('EN_Card_Data.csv')
df.columns = ['ID', 'Name', 'Set', 'Num'] + list(df.columns[4:])

deck_ids = []
for line in text_deck.strip().split('\n'):
    if not line.strip(): continue
    parts = line.split()
    count = int(parts[0])
    
    # E.g., "2 Lunatone ASC 105"
    num = parts[-1]
    set_name = parts[-2]
    
    # Handle weird cases like {F} Energy which has spaces, but we just need Set and Num
    match = df[(df['Set'] == set_name) & (df['Num'].astype(str) == num)]
    if len(match) == 0:
        print(f"Warning: Could not find {line}")
        continue
    
    card_id = match['ID'].values[0]
    for _ in range(count):
        deck_ids.append(card_id)

print(f"Extracted {len(deck_ids)} cards")
with open('deck_candidate.csv', 'w') as f:
    for cid in deck_ids:
        f.write(f"{cid}\n")
print("Saved to deck_candidate.csv")

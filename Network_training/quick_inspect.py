import os
import glob
import json

json_dir = "Wall_V5/replay/*.json"
files = glob.glob(json_dir)

print(f"Found {len(files)} JSON replays for Wall_V5:")
for f in sorted(files):
    with open(f, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
        steps = data if isinstance(data, list) else data.get("steps", [])
        if steps:
            last = steps[-1]
            if isinstance(last, list) and len(last) >= 2:
                r0 = last[0].get("reward")
                r1 = last[1].get("reward")
                obs = last[0].get("observation", {}).get("current", {})
                players = obs.get("players", [])
                p0_prizes = len(players[0].get("prize", [])) if len(players) > 0 else "?"
                p1_prizes = len(players[1].get("prize", [])) if len(players) > 1 else "?"
                p0_active = players[0].get("active", [{}])[0].get("id", "?") if (len(players) > 0 and players[0].get("active")) else "?"
                p1_active = players[1].get("active", [{}])[0].get("id", "?") if (len(players) > 1 and players[1].get("active")) else "?"
                p0_bench = len([b for b in players[0].get("bench", []) if b]) if len(players) > 0 else "?"
                p1_bench = len([b for b in players[1].get("bench", []) if b]) if len(players) > 1 else "?"
                print(f"File: {os.path.basename(f)} | Result: {r0} vs {r1} | Steps: {len(steps)} | Prizes: {p0_prizes} vs {p1_prizes} | Active: {p0_active} vs {p1_active} | Bench: {p0_bench} vs {p1_bench}")

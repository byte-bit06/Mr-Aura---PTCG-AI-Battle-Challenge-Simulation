"""
Replay Analyzer for Wall_V5
Reads all HTML replay files and extracts game outcome + final board state info.
Also reads JSON replays from Wall_V5/replay/ folder.
"""
import os
import re
import json
from pathlib import Path
from collections import defaultdict

REPLAY_DIR = Path("replays")
JSON_REPLAY_DIR = Path("Wall_V5/replay")

# ── Parse HTML replays (evaluate_v5.py output) ────────────────────────────────
def parse_html_replays():
    results = defaultdict(lambda: {"wins": [], "losses": []})
    
    for f in sorted(REPLAY_DIR.glob("*.html")):
        name = f.stem
        # Determine opponent and who was P1
        if "Wall_V5_vs_" in name:
            opp = name.split("Wall_V5_vs_")[1].rsplit("_", 1)[0]
            v5_is_p1 = True
        elif "_vs_Wall_V5" in name:
            opp = name.split("_vs_Wall_V5")[0]
            v5_is_p1 = False
        else:
            continue
        
        # Read file (large — just scan for key markers)
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        
        # Look for winner in the HTML
        # The kaggle env embeds reward data as JSON in the HTML
        reward_matches = re.findall(r'"reward":\s*([0-9\-\.]+)', content)
        if len(reward_matches) >= 2:
            r1 = float(reward_matches[0])
            r2 = float(reward_matches[1])
            v5_reward = r1 if v5_is_p1 else r2
            
            if v5_reward == 1.0:
                results[opp]["wins"].append(name)
            elif v5_reward == -1.0:
                results[opp]["losses"].append(name)
    
    return results

# ── Parse JSON replays (Kaggle submission replays) ──────────────────────────────
def parse_json_replays():
    json_results = []
    
    for f in sorted(JSON_REPLAY_DIR.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except:
            continue
        
        # Kaggle replay format: list of steps, each step has player states
        steps = data if isinstance(data, list) else data.get("steps", [])
        if not steps:
            continue
        
        last_step = steps[-1] if steps else None
        if not last_step:
            continue
        
        # Try to extract rewards from last step
        if isinstance(last_step, list) and len(last_step) >= 2:
            r0 = last_step[0].get("reward") if isinstance(last_step[0], dict) else None
            r1 = last_step[1].get("reward") if isinstance(last_step[1], dict) else None
            
            # Try to get prize counts from observation
            obs = last_step[0].get("observation", {}) if isinstance(last_step[0], dict) else {}
            current = obs.get("current", {})
            players = current.get("players", [])
            
            p0_prizes = len(players[0].get("prize", [])) if len(players) > 0 else "?"
            p1_prizes = len(players[1].get("prize", [])) if len(players) > 1 else "?"
            p0_active = players[0].get("active", [{}])[0].get("id", "?") if (len(players) > 0 and players[0].get("active")) else "?"
            p1_active = players[1].get("active", [{}])[0].get("id", "?") if (len(players) > 1 and players[1].get("active")) else "?"
            p0_bench = len([b for b in players[0].get("bench", []) if b]) if len(players) > 0 else "?"
            p1_bench = len([b for b in players[1].get("bench", []) if b]) if len(players) > 1 else "?"
            
            json_results.append({
                "file": f.name,
                "steps": len(steps),
                "p0_reward": r0,
                "p1_reward": r1,
                "p0_prizes_left": p0_prizes,
                "p1_prizes_left": p1_prizes,
                "p0_active_id": p0_active,
                "p1_active_id": p1_active,
                "p0_bench_count": p0_bench,
                "p1_bench_count": p1_bench,
            })
    
    return json_results

# ── Run ────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("WALL_V5 REPLAY ANALYSIS")
print("=" * 70)

html_results = parse_html_replays()
json_results = parse_json_replays()

print(f"\n{'Opponent':<30} {'Wins':>6} {'Losses':>8} {'WinRate':>10}")
print("-" * 60)

total_wins = total_losses = 0
for opp, r in sorted(html_results.items()):
    w, l = len(r["wins"]), len(r["losses"])
    total = w + l
    wr = f"{w/total*100:.0f}%" if total else "?"
    total_wins += w
    total_losses += l
    print(f"{opp:<30} {w:>6} {l:>8} {wr:>10}")
    if r["losses"]:
        for lf in r["losses"][:3]:
            print(f"  LOSS: {lf}")

print("-" * 60)
total = total_wins + total_losses
print(f"{'TOTAL':<30} {total_wins:>6} {total_losses:>8} {total_wins/max(1,total)*100:>9.0f}%")

print(f"\n\n{'=' * 70}")
print("JSON REPLAY DETAILS (Kaggle Submission Replays)")
print("=" * 70)
for r in json_results:
    outcome = "WIN" if r["p0_reward"] == 1 else ("LOSS" if r["p0_reward"] == -1 else "TIE/UNK")
    print(f"\n{r['file']}  [{outcome}]  Steps={r['steps']}")
    print(f"  P0 (us):  reward={r['p0_reward']}  prizes_left={r['p0_prizes_left']}  active={r['p0_active_id']}  bench={r['p0_bench_count']}")
    print(f"  P1 (opp): reward={r['p1_reward']}  prizes_left={r['p1_prizes_left']}  active={r['p1_active_id']}  bench={r['p1_bench_count']}")

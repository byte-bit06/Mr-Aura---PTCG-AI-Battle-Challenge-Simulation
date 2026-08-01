import json

with open('Wall_V3/89268010.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

steps = data.get('steps', [])
all_logs = []

for step in steps:
    obs = step[0].get('observation', {})
    logs = obs.get('logs', [])
    for l in logs:
        all_logs.append(l)

print(f"Total logs: {len(all_logs)}")
print("Last 20 logs of the entire game:")
for log in all_logs[-20:]:
    print(log)

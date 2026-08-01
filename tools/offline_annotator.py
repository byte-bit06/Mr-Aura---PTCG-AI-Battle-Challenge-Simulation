import os
import glob
import json
import csv
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# --- Load Card Dictionary ---
CARD_DICT = {}
try:
    # Handle potentially dirty encodings
    _data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "EN_Card_Data.csv")
    with open(_data_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0 or len(row) < 2: continue
            card_id = row[0].strip()
            card_name = row[1].strip()
            try:
                CARD_DICT[int(card_id)] = card_name
            except ValueError:
                pass
except Exception as e:
    print("Warning: Could not load EN_Card_Data.csv", e)

# Hardcode some just in case they aren't in CSV
CARD_DICT.update({
    673: 'Makuhita', 674: 'Hariyama', 675: 'Lunatone', 676: 'Solrock',
    677: 'Riolu', 678: 'Mega Lucario ex'
})

def get_card_name(card_id):
    if not card_id: return "Unknown Card"
    return CARD_DICT.get(int(card_id), f"Unknown Card (ID {card_id})")

def translate_action(opt, obs_dict):
    """Translate raw Kaggle action to beautiful English"""
    t = str(opt.get("type", "UNKNOWN"))
    
    us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
    
    if t == "PLAY" or t == "1" or t == "3":
        idx = opt.get("index", 0)
        try:
            cid = us['hand'][idx].get("id")
            return f"PLAY CARD: {get_card_name(cid)}"
        except:
            return f"PLAY Card from Hand (Index {idx})"
            
    elif t == "ATTACK" or t == "5":
        attack_id = opt.get("attackId", "?")
        return f"ATTACK with Active (Attack Index {attack_id})"
        
    elif t == "ATTACH" or t == "4":
        idx = opt.get("index", 0)
        try:
            cid = us['hand'][idx].get("id")
            return f"ATTACH ENERGY: {get_card_name(cid)}"
        except:
            return f"ATTACH Energy from Hand (Index {idx})"
            
    elif t == "RETREAT" or t == "6":
        try:
            cid = us['active'][0].get('id')
            return f"RETREAT ACTIVE: {get_card_name(cid)}"
        except:
            return "RETREAT ACTIVE"
            
    elif t == "ABILITY" or t == "2":
        return "USE ABILITY"
        
    elif t == "14":
        return "END TURN / DONE"
        
    elif t == "12":
        return "CANCEL / PASS"
        
    elif t == "7":
        idx = opt.get('index')
        try:
            if idx == 0:
                cid = us['active'][0]['id']
                return f"SELECT ACTIVE POKEMON: {get_card_name(cid)}"
            else:
                cid = us['bench'][idx - 1]['id']
                return f"SELECT BENCH POKEMON: {get_card_name(cid)}"
        except:
            return f"SELECT POKEMON (Index {idx})"
            
    elif t == "8":
        area = opt.get('area')
        idx = opt.get('index')
        in_play_area = opt.get('inPlayArea')
        in_play_idx = opt.get('inPlayIndex')
        
        src_name = "Card"
        if area == 2:
            try: src_name = get_card_name(us['hand'][idx]['id'])
            except: src_name = f"Hand Card {idx}"
            
        target_name = "Target"
        if in_play_area == 4:
            try: target_name = get_card_name(us['active'][0]['id'])
            except: target_name = "Active Pokemon"
        elif in_play_area == 5:
            try: target_name = get_card_name(us['bench'][in_play_idx]['id'])
            except: target_name = f"Bench Pokemon {in_play_idx}"
            
        return f"SELECT TARGET: {src_name} -> {target_name}"
        
    else:
        # Fallback to showing the raw dictionary so we can inspect it
        import json
        return f"ACTION TYPE {t}: {json.dumps(opt)}"

def build_english_board(obs_dict):
    us = obs_dict["current"]["players"][obs_dict["current"]["yourIndex"]]
    opp = obs_dict["current"]["players"][1 - obs_dict["current"]["yourIndex"]]
    
    def get_names(lst):
        if not lst: return []
        return [get_card_name(c.get('id')) for c in lst if c]
        
    my_active_names = get_names(us.get("active", []))
    opp_active_names = get_names(opp.get("active", []))
        
    return {
        "my_active": my_active_names[0] if my_active_names else "None",
        "my_bench": get_names(us.get("bench", [])),
        "my_hand": get_names(us.get("hand", [])),
        "my_prizes": len(us.get("prize", []) or []),
        "opp_active": opp_active_names[0] if opp_active_names else "None",
        "opp_bench": get_names(opp.get("bench", [])),
        "opp_prizes": len(opp.get("prize", []) or [])
    }

# --- Routes ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Offline DAgger Annotator</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; background: #f4f4f9; padding: 20px; color: #333; }
        .container { max-width: 900px; margin: 0 auto; }
        .turn-card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .board-state { background: #e0f2fe; padding: 15px; border-radius: 5px; margin-bottom: 15px; font-family: monospace; font-size: 14px; }
        .options { margin-bottom: 15px; }
        .options label { display: block; padding: 8px; background: #f8fafc; margin-bottom: 5px; border: 1px solid #cbd5e1; border-radius: 4px; cursor: pointer; }
        .options label:hover { background: #e2e8f0; }
        .ai-choice { color: #b91c1c; font-weight: bold; margin-bottom: 15px; }
        .reasoning-box { width: 100%; height: 60px; margin-bottom: 10px; padding: 8px; box-sizing: border-box; }
        .btn { background: #2563eb; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .btn:hover { background: #1d4ed8; }
        .success-msg { color: #16a34a; font-weight: bold; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Offline DAgger Annotator</h2>
        <p>Reviewing Replay: <strong>{{ replay_id }}</strong></p>
        
        {% for idx, item in enumerate(decisions) %}
        <div class="turn-card" id="turn-{{ idx }}">
            <h3>Decision #{{ idx + 1 }}</h3>
            
            <div class="board-state">
                <strong>[YOUR BOARD]</strong><br>
                Active: {{ item.board.my_active }}<br>
                Bench: {{ ', '.join(item.board.my_bench) if item.board.my_bench else 'Empty' }}<br>
                Hand: {{ ', '.join(item.board.my_hand) if item.board.my_hand else 'Empty' }}<br>
                Prizes Remaining: {{ item.board.my_prizes }}<br>
                <br>
                <strong>[OPPONENT BOARD]</strong><br>
                Active: {{ item.board.opp_active }}<br>
                Bench: {{ ', '.join(item.board.opp_bench) if item.board.opp_bench else 'Empty' }}<br>
                Prizes Remaining: {{ item.board.opp_prizes }}
            </div>
            
            <div class="ai-choice">
                🤖 AI Actually Chose: {{ item.ai_choice_text }}
            </div>
            
            <form onsubmit="submitAnnotation(event, {{ idx }})">
                <div class="options">
                    <strong>What WOULD you play?</strong><br>
                    {% for opt_idx, opt_text in enumerate(item.english_options) %}
                        <label>
                            <input type="radio" name="choice_{{ idx }}" value="{{ opt_idx }}" required> 
                            {{ opt_text }}
                        </label>
                    {% endfor %}
                </div>
                
                <textarea id="reasoning-{{ idx }}" class="reasoning-box" placeholder="Why? (Reasoning...)"></textarea>
                <br>
                <button type="submit" class="btn">Save Correction</button>
                <span id="success-{{ idx }}" class="success-msg">Saved! ✓</span>
            </form>
        </div>
        {% endfor %}
    </div>

    <script>
        function submitAnnotation(e, idx) {
            e.preventDefault();
            const form = e.target;
            const choice = form.querySelector('input[name="choice_' + idx + '"]:checked').value;
            const reasoning = document.getElementById('reasoning-' + idx).value;
            
            fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    replay_id: '{{ replay_id }}',
                    decision_idx: idx,
                    human_choice: parseInt(choice),
                    reasoning: reasoning
                })
            }).then(r => r.json()).then(data => {
                if(data.success) {
                    document.getElementById('success-' + idx).style.display = 'inline';
                    setTimeout(() => { document.getElementById('success-' + idx).style.display = 'none'; }, 2000);
                }
            });
        }
    </script>
</body>
</html>
"""

# Global memory of decisions so we can save the raw obs when they submit
LOADED_REPLAY_DATA = {}

@app.route("/")
def index():
    _replays_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "replays", "*_meta.json")
    meta_files = glob.glob(_replays_path)
    if not meta_files:
        return "No replays found. Run generate_replays.py first."
        
    # Get the latest replay
    meta_files.sort(key=os.path.getmtime, reverse=True)
    latest = meta_files[0]
    replay_id = os.path.basename(latest).replace("_meta.json", "")
    
    with open(latest, "r") as f:
        data = json.load(f)
        
    LOADED_REPLAY_DATA[replay_id] = data
    
    ui_decisions = []
    for item in data:
        raw_obs = item.get("raw_obs", {})
        
        # Build board state
        board = build_english_board(raw_obs)
        
        # Build english options from Kaggle's select dict
        select_data = raw_obs.get("select", {})
        raw_options = select_data.get("option", [])
        
        english_options = []
        for opt in raw_options:
            english_options.append(translate_action(opt, raw_obs))
            
        # Determine what AI chose (heuristic choice)
        hc = item.get("heuristic_choice", [0])
        hc_idx = hc[0] if isinstance(hc, list) and hc else 0
        ai_choice_text = english_options[hc_idx] if 0 <= hc_idx < len(english_options) else "Unknown"
        
        ui_decisions.append({
            "board": board,
            "english_options": english_options,
            "ai_choice_text": ai_choice_text
        })
        
    return render_template_string(HTML_TEMPLATE, replay_id=replay_id, decisions=ui_decisions, enumerate=enumerate)

@app.route("/save", methods=["POST"])
def save():
    data = request.json
    replay_id = data["replay_id"]
    decision_idx = data["decision_idx"]
    human_choice_idx = data["human_choice"]
    reasoning = data["reasoning"]
    
    if replay_id in LOADED_REPLAY_DATA:
        item = LOADED_REPLAY_DATA[replay_id][decision_idx]
        
        # Reconstruct choice array
        raw_obs = item["raw_obs"]
        select_data = raw_obs.get("select", {})
        max_count = select_data.get("maxCount", 1)
        human_choice = [human_choice_idx] * max_count
        
        datum = {
            "obs": item.get("obs"),
            "heuristic_choice": item.get("heuristic_choice"),
            "human_choice": human_choice,
            "reasoning": reasoning
        }
        
        # Save to local file
        _jsonl_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "dagger_dataset.jsonl")
        with open(_jsonl_path, "a") as f:
            f.write(json.dumps(datum) + "\n")
            
        return jsonify({"success": True})
    return jsonify({"success": False})

if __name__ == "__main__":
    print("Starting Offline Annotator...")
    app.run(host="0.0.0.0", port=5001, debug=False)

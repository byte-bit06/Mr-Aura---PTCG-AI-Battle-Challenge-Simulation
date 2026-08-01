import os
import json
import glob
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS so the bookmarklet on ptcgvis.heroz.jp can fetch our metadata and post to our backend!
CORS(app, resources={r"/*": {"origins": "*"}})

DATASET_FILE = "dagger_dataset.jsonl"

BOOKMARKLET_JS = """
(function() {
    // Inject the DAgger Annotator Panel into the current page (e.g., ptcgvis.heroz.jp)
    if (document.getElementById('dagger-panel')) {
        document.getElementById('dagger-panel').remove();
    }
    
    const panel = document.createElement('div');
    panel.id = 'dagger-panel';
    panel.innerHTML = `
    <style>
        #dagger-panel {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 320px;
            background: rgba(30, 41, 59, 0.95);
            color: white;
            border: 2px solid #3b82f6;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            z-index: 9999999;
            font-family: 'Inter', sans-serif;
            text-align: left;
        }
        #dagger-panel h3 { margin-top: 0; color: #60a5fa; }
        .nav-btn { background: #334155; color: white; border: none; padding: 5px 10px; cursor: pointer; border-radius:4px; }
        .nav-btn:hover { background: #475569; }
        
        .opt-label { display: block; margin: 8px 0; background: #0f172a; padding: 8px; border-radius: 4px; cursor: pointer; border: 1px solid #334155; }
        .opt-label:hover { border-color: #3b82f6; }
        
        #dagger-panel textarea { width: 100%; height: 60px; background: #000; color: white; border: 1px solid #334155; margin-top: 10px; padding: 5px; box-sizing:border-box;}
        #submit-btn { width: 100%; padding: 10px; background: #3b82f6; color: white; border: none; margin-top: 10px; border-radius:4px; cursor: pointer; font-weight: bold;}
        #submit-btn:hover { background: #2563eb; }
        
        .ai-badge { background: #10b981; color: black; font-size: 10px; padding: 2px 5px; border-radius: 10px; margin-left: 5px; font-weight: bold;}
        
        #replay-select { width: 100%; padding: 5px; margin-bottom: 15px; background: #0f172a; color: white; border: 1px solid #334155; border-radius: 4px; }
    </style>
    
    <h3>DAgger Annotator</h3>
    
    <select id="replay-select">
        <option value="">Loading replays...</option>
    </select>

    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 15px;">
        <button class="nav-btn" onclick="window.prevDec()">&laquo; Prev</button>
        <span style="font-size:14px; font-weight:bold;">Decision <span id="dec-idx">0</span> / <span id="dec-total">0</span></span>
        <button class="nav-btn" onclick="window.nextDec()">Next &raquo;</button>
    </div>
    
    <div style="background:#0f172a; padding: 10px; border-radius: 4px; border: 1px solid #f59e0b; color: #fbbf24; margin-bottom: 15px; font-size: 13px;">
        <strong>Step: <span id="env-step">0</span></strong><br>
        Scrub the replay slider to this step!
    </div>

    <div id="options-list"></div>
    
    <textarea id="reasoning" placeholder="Reasoning (Optional)"></textarea>
    <button id="submit-btn" onclick="window.submitAnnotation()">Submit Annotation</button>
    <button onclick="document.getElementById('dagger-panel').remove()" style="margin-top:5px; width:100%; padding:5px; background: #ef4444; color:white; border:none; border-radius:4px; cursor:pointer;">Close</button>
    `;
    
    document.body.appendChild(panel);
    
    // Globals for the bookmarklet
    window.daggerMetadata = [];
    window.currIdx = 0;
    
    window.renderDecision = function() {
        if (window.daggerMetadata.length === 0) {
            document.getElementById('options-list').innerHTML = '<em>No decisions in this game.</em>';
            return;
        }
        
        const dec = window.daggerMetadata[window.currIdx];
        document.getElementById('dec-idx').innerText = window.currIdx + 1;
        document.getElementById('dec-total').innerText = window.daggerMetadata.length;
        document.getElementById('env-step').innerText = dec.step;
        document.getElementById('reasoning').value = '';
        
        const container = document.getElementById('options-list');
        container.innerHTML = '';
        
        dec.options.forEach(opt => {
            container.innerHTML += `
                <label class="opt-label">
                    <input type="radio" name="opt" value="${opt.id}">
                    ${opt.text} ${opt.is_heuristic ? '<span class="ai-badge">AI Pick</span>' : ''}
                </label>
            `;
        });
    };
    
    window.prevDec = function() { if(window.currIdx > 0) { window.currIdx--; window.renderDecision(); } };
    window.nextDec = function() { if(window.currIdx < window.daggerMetadata.length - 1) { window.currIdx++; window.renderDecision(); } };
    
    window.submitAnnotation = async function() {
        const selected = document.querySelector('input[name="opt"]:checked');
        if (!selected) { alert('Please select an option first!'); return; }
        
        const dec = window.daggerMetadata[window.currIdx];
        const actionIdx = parseInt(selected.value);
        const reasoning = document.getElementById('reasoning').value;
        const maxCount = dec.raw_obs.select.maxCount || 1;
        const finalChoice = Array(maxCount).fill(actionIdx);
        
        document.getElementById('submit-btn').innerText = 'Saving...';
        
        try {
            await fetch('http://localhost:5000/action', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    replay_id: document.getElementById('replay-select').value,
                    decision_index: window.currIdx,
                    obs: dec.raw_obs,
                    heuristic_choice: dec.raw_heuristic,
                    human_choice: finalChoice,
                    reasoning: reasoning
                })
            });
            document.getElementById('submit-btn').innerText = 'Submit Annotation';
            window.nextDec();
        } catch(e) {
            alert("Error saving! Make sure localhost:5000 is running.");
            document.getElementById('submit-btn').innerText = 'Submit Annotation';
        }
    };
    
    // Fetch available replays
    fetch('http://localhost:5000/api/replays')
        .then(res => res.json())
        .then(replays => {
            const select = document.getElementById('replay-select');
            select.innerHTML = '';
            if(replays.length === 0) {
                select.innerHTML = '<option value="">No replays found</option>';
                return;
            }
            replays.forEach(r => {
                const opt = document.createElement('option');
                opt.value = r;
                opt.innerText = r;
                select.appendChild(opt);
            });
            
            // Load the first one by default
            window.loadReplayMetadata(replays[0]);
            
            select.onchange = (e) => {
                window.loadReplayMetadata(e.target.value);
            };
        });
        
    window.loadReplayMetadata = function(replayId) {
        if(!replayId) return;
        fetch(`http://localhost:5000/api/replay/${replayId}`)
            .then(res => res.json())
            .then(data => {
                window.daggerMetadata = data;
                window.currIdx = 0;
                window.renderDecision();
            });
    };
})();
"""

@app.route("/")
def index():
    replays = [os.path.basename(r).replace("_meta.json", "") for r in glob.glob("replays/*_meta.json")]
    
    # We provide a simple page with instructions on how to use the bookmarklet
    return f"""
    <html>
    <body style="font-family: sans-serif; padding: 40px; line-height: 1.6; max-width: 800px; margin: 0 auto;">
    <h2>Proper Replay DAgger Setup</h2>
    <p>Because the Kaggle local HTML visualizer for CABT is fundamentally broken (blank screen), you need to use the official Heroz visualizer.</p>
    
    <h3>Step 1: Get the Replay JSON</h3>
    <p>I have generated a replay for you. Upload it to the official visualizer:</p>
    <ul>
    {"".join([f'<li><a href="/download/{r}" download="replay_{r}.json">Download {r} JSON</a></li>' for r in replays])}
    </ul>
    <p>Upload the downloaded JSON to <a href="https://ptcgvis.heroz.jp/Visualizer/Replay/0" target="_blank">https://ptcgvis.heroz.jp/Visualizer/Replay/0</a></p>

    <h3>Step 2: Inject the Annotator</h3>
    <p>To inject the DAgger Annotator directly onto the Heroz visualizer, drag the following button to your bookmarks bar, then click it while you are on the Heroz website!</p>
    
    <a href="javascript:(function(){{var s=document.createElement('script');s.src='http://localhost:5000/bookmarklet.js?t='+Date.now();document.body.appendChild(s);}})();" 
       style="display:inline-block; padding: 10px 20px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
       Inject DAgger Annotator
    </a>
    
    <br><br>
    <p><em>(Alternatively, open the Dev Console (F12) on the Heroz website and paste this code:)</em></p>
    <pre style="background: #f1f5f9; padding: 10px; border-radius: 5px; overflow-x: auto;">
var s=document.createElement('script');
s.src='http://localhost:5000/bookmarklet.js?t='+Date.now();
document.body.appendChild(s);
    </pre>
    
    </body></html>
    """

from flask import send_file

@app.route("/download/<replay_id>")
def download_json(replay_id):
    filepath = os.path.abspath(f"replays/{replay_id}.json")
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return "Not found", 404

@app.route("/bookmarklet.js")
def bookmarklet():
    return BOOKMARKLET_JS, 200, {'Content-Type': 'application/javascript'}

@app.route("/api/replays")
def api_replays():
    replays = [os.path.basename(r).replace("_meta.json", "") for r in glob.glob("replays/*_meta.json")]
    return jsonify(replays)

@app.route("/api/replay/<replay_id>")
def api_replay(replay_id):
    with open(f"replays/{replay_id}_meta.json", "r", encoding="utf-8") as f:
        return f.read(), 200, {'Content-Type': 'application/json'}

@app.route("/action", methods=["POST", "OPTIONS"])
def submit_action():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    data = request.json
    record = {
        "obs": data["obs"],
        "heuristic_choice": data["heuristic_choice"],
        "human_choice": data["human_choice"],
        "reasoning": data["reasoning"],
        "replay_id": data["replay_id"],
        "decision_index": data["decision_index"]
    }
    with open(DATASET_FILE, "a") as f:
        f.write(json.dumps(record) + "\\n")
    return jsonify({"success": True})

if __name__ == "__main__":
    print("="*60)
    print("Bookmarklet Server Running at http://localhost:5000")
    print("="*60)
    app.run(host="0.0.0.0", port=5000)

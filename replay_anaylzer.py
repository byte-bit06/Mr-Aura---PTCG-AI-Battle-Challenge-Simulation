"""
replay_analyzer.py — PTCG Replay Winner Move-by-Move Analyzer
================================================================
Ingests .json replay files (standard Kaggle PTCG environment format or custom step format).
Analyzes the winning player's strategy turn-by-turn and move-by-move.
Extracts specific reasons why the winner won, turning points, resource efficiency, and tactical breakdowns.
Generates structured JSON and Markdown summary reports.
"""

import os
import sys
import json
import csv
import glob
from collections import defaultdict

# Root directory setup
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

# --- Card Dictionary Loader ---
CARD_DICT = {}
def load_card_dict():
    global CARD_DICT
    if CARD_DICT:
        return CARD_DICT
    data_path = os.path.join(_root_dir, "data", "EN_Card_Data.csv")
    if os.path.exists(data_path):
        try:
            with open(data_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0 or len(row) < 2:
                        continue
                    try:
                        CARD_DICT[int(row[0].strip())] = row[1].strip()
                    except ValueError:
                        pass
        except Exception as e:
            print(f"[Warning] Could not read EN_Card_Data.csv: {e}")

    # Fallback known IDs
    CARD_DICT.update({
        673: 'Makuhita', 674: 'Hariyama', 675: 'Lunatone', 676: 'Solrock',
        677: 'Riolu', 678: 'Mega Lucario ex', 201: 'Professor\'s Research',
        202: 'Boss\'s Orders', 203: 'Ultra Ball', 204: 'Switch',
        205: 'Double Turbo Energy', 206: 'Basic Fighting Energy'
    })
    return CARD_DICT

def get_card_name(card_id):
    dict_map = load_card_dict()
    if card_id is None:
        return "Unknown Card"
    try:
        cid = int(card_id)
        return dict_map.get(cid, f"Card ID {cid}")
    except (ValueError, TypeError):
        return str(card_id)

def get_action_label(opt, obs_player_state=None):
    """Parses action dictionary/option into readable description."""
    if not isinstance(opt, dict):
        return f"Action: {opt}"
    
    t = str(opt.get("type", "UNKNOWN")).upper()
    idx = opt.get("index", 0) or 0

    hand = obs_player_state.get("hand") if isinstance(obs_player_state, dict) else None

    if t in ["PLAY", "1", "3"]:
        if isinstance(hand, list) and 0 <= idx < len(hand) and isinstance(hand[idx], dict):
            cid = hand[idx].get("id")
            cname = hand[idx].get("name") or get_card_name(cid)
            return f"PLAY CARD: {cname}"
        return f"PLAY CARD (Hand Index {idx})"

    elif t in ["ATTACH", "4"]:
        if isinstance(hand, list) and 0 <= idx < len(hand) and isinstance(hand[idx], dict):
            cid = hand[idx].get("id")
            cname = hand[idx].get("name") or get_card_name(cid)
            return f"ATTACH ENERGY: {cname}"
        return f"ATTACH ENERGY (Hand Index {idx})"

    elif t in ["ATTACK", "5"]:
        atk_id = opt.get("attackId", 0)
        return f"ATTACK (Attack ID {atk_id})"

    elif t in ["RETREAT", "6"]:
        return "RETREAT ACTIVE POKÉMON"

    elif t in ["ABILITY", "2"]:
        return f"USE ABILITY (Ability Index {idx})"

    elif t in ["14", "DONE", "END"]:
        return "END TURN"

    elif t in ["12", "PASS", "CANCEL"]:
        return "PASS / CANCEL"

    elif t in ["7", "SELECT"]:
        return f"SELECT POKÉMON (Index {idx})"

    elif t in ["8"]:
        return f"SELECT CARD IN PLAY (Index {idx})"

    elif t in ["9", "13"]:
        return f"SELECT ENERGY TARGET (Index {idx})"

    elif t in ["10", "11"]:
        return f"SELECT DECK / DISCARD CARD (Index {idx})"

    elif t in ["21", "27", "32"]:
        return f"SELECT ATTACK / EFFECT TARGET (Index {idx})"

    # Format list/tuple representation clean
    t_clean = t.replace("[", "").replace("]", "").strip()
    return f"ACTION Type {t_clean} Index {idx}"

def determine_winner(replay_data):
    """Extracts game winner index from replay structure."""
    if isinstance(replay_data, dict):
        rewards = replay_data.get("rewards")
        if isinstance(rewards, list) and len(rewards) >= 2:
            r0 = rewards[0] if rewards[0] is not None else 0
            r1 = rewards[1] if rewards[1] is not None else 0
            if r0 > r1:
                return 0, "Player 0 (Won by Root Reward)"
            elif r1 > r0:
                return 1, "Player 1 (Won by Root Reward)"

        steps = replay_data.get("steps") or replay_data.get("history") or []
    elif isinstance(replay_data, list):
        steps = replay_data
    else:
        steps = []

    if not steps:
        return 0, "Unknown (No steps)"

    # Look at last step rewards/status
    last_step = steps[-1]
    if isinstance(last_step, list):
        rewards = [agent.get("reward") for agent in last_step if isinstance(agent, dict)]
        if len(rewards) >= 2:
            r0 = rewards[0] if rewards[0] is not None else 0
            r1 = rewards[1] if rewards[1] is not None else 0
            if r0 > r1:
                return 0, "Player 0 (Won by Step Reward)"
            elif r1 > r0:
                return 1, "Player 1 (Won by Step Reward)"

        # Check observations log
        for p_idx in [0, 1]:
            if p_idx < len(last_step) and isinstance(last_step[p_idx], dict):
                obs = last_step[p_idx].get("observation") or {}
                logs = obs.get("logs") or []
                for log in logs:
                    log_str = str(log).lower()
                    if "win" in log_str or "winner" in log_str or "victory" in log_str:
                        if f"player {p_idx}" in log_str or f"p{p_idx}" in log_str:
                            return p_idx, f"Player {p_idx} (Won by Log Confirmation)"

    # Fallback default: Player 0
    return 0, "Player 0 (Default Winner)"

def analyze_replay(replay_file_path):
    """
    Parses a single replay file and returns full move-by-move win attribution analysis.
    """
    with open(replay_file_path, "r", encoding="utf-8") as f:
        replay_data = json.load(f)

    # Handle dictionary wrapping
    if isinstance(replay_data, dict) and "steps" in replay_data:
        steps = replay_data.get("steps") or []
        config = replay_data.get("configuration") or {}
        seed = config.get("seed", replay_data.get("seed", "Unknown"))
    elif isinstance(replay_data, list):
        steps = replay_data
        seed = "Unknown"
    else:
        steps = []
        seed = "Unknown"

    winner_idx, win_reason = determine_winner(replay_data)
    
    move_analysis = []
    turning_points = []
    winner_stats = {
        "total_moves": 0,
        "attacks_performed": 0,
        "energies_attached": 0,
        "cards_played": 0,
        "evolutions": 0,
        "retreats": 0,
        "prizes_taken": 0,
        "turns_played": set()
    }

    prev_prizes = 6
    prev_opp_prizes = 6

    for step_idx, step in enumerate(steps):
        if not isinstance(step, list) or len(step) <= winner_idx:
            continue

        agent_step = step[winner_idx]
        if not isinstance(agent_step, dict):
            continue

        obs = agent_step.get("observation") or {}
        action = agent_step.get("action")
        reward = agent_step.get("reward") or 0

        # Extract current state safely
        current_state = obs.get("current") or {}
        if not isinstance(current_state, dict):
            current_state = {}

        turn = current_state.get("turn", 1)
        your_index = current_state.get("yourIndex")
        if your_index is None:
            your_index = winner_idx

        players = current_state.get("players") or []
        if not isinstance(players, list):
            players = []

        if len(players) > your_index and isinstance(players[your_index], dict):
            winner_state = players[your_index]
        else:
            winner_state = {}

        opp_idx = 1 - your_index
        if len(players) > opp_idx and isinstance(players[opp_idx], dict):
            opp_state = players[opp_idx]
        else:
            opp_state = {}

        winner_stats["turns_played"].add(turn)

        # Check options available
        select_data = obs.get("select") or {}
        if not isinstance(select_data, dict):
            select_data = {}

        options = select_data.get("option") or obs.get("options") or select_data.get("options") or []
        chosen_option = None
        if action is not None and isinstance(options, list):
            if isinstance(action, list) and action:
                chosen_idx = action[0]
            elif isinstance(action, int):
                chosen_idx = action
            else:
                chosen_idx = None

            if chosen_idx is not None and 0 <= chosen_idx < len(options):
                chosen_option = options[chosen_idx]

        if chosen_option or action is not None:
            winner_stats["total_moves"] += 1
            action_desc = get_action_label(chosen_option if chosen_option else {"type": str(action)}, winner_state)
            
            # Categorize Tactical Move
            act_type = str(chosen_option.get("type") if chosen_option else action).upper()
            tactical_category = "General Move"
            strategic_reasoning = ""

            if "ATTACK" in action_desc or act_type in ["ATTACK", "5"]:
                winner_stats["attacks_performed"] += 1
                tactical_category = "Offensive Attack"
                strategic_reasoning = f"Applied pressure on opponent's active Pokémon during Turn {turn} to progress prize race."

            elif "ATTACH" in action_desc or act_type in ["ATTACH", "4"]:
                winner_stats["energies_attached"] += 1
                tactical_category = "Energy Acceleration"
                strategic_reasoning = f"Built energy curve on key attacker to prepare future turn lethal attacks."

            elif "PLAY" in action_desc or act_type in ["PLAY", "1", "3"]:
                winner_stats["cards_played"] += 1
                tactical_category = "Hand / Board Setup"
                strategic_reasoning = f"Expanded board resources and set up attackers / utility Pokémon."

            elif "RETREAT" in action_desc or act_type in ["RETREAT", "6"]:
                winner_stats["retreats"] += 1
                tactical_category = "Positioning / Safety"
                strategic_reasoning = f"Saved damaged active attacker and brought out optimal matchup response."

            # Check Prize changes
            curr_prizes = winner_state.get("prizes", 6) if isinstance(winner_state, dict) else 6
            curr_opp_prizes = opp_state.get("prizes", 6) if isinstance(opp_state, dict) else 6

            is_turning_point = False
            if curr_prizes < prev_prizes:
                prizes_claimed = prev_prizes - curr_prizes
                winner_stats["prizes_taken"] += prizes_claimed
                is_turning_point = True
                turning_points.append({
                    "step": step_idx,
                    "turn": turn,
                    "event": f"Took {prizes_claimed} Prize Card(s)! ({prev_prizes} -> {curr_prizes} remaining)",
                    "move": action_desc
                })

            prev_prizes = curr_prizes
            prev_opp_prizes = curr_opp_prizes

            move_analysis.append({
                "step": step_idx,
                "turn": turn,
                "action": action_desc,
                "category": tactical_category,
                "reasoning": strategic_reasoning,
                "winner_prizes_remaining": curr_prizes,
                "is_turning_point": is_turning_point
            })

    # Summary of Why Winner Won
    total_turns = max(1, len(winner_stats["turns_played"]))
    why_winner_won = [
        f"1. **Prize Pace Control**: Winner claimed {winner_stats['prizes_taken']} prize cards across {total_turns} turns.",
        f"2. **Attack Efficiency**: Executed {winner_stats['attacks_performed']} targeted attacks, maintaining continuous pressure.",
        f"3. **Resource Management**: Attached {winner_stats['energies_attached']} energy cards smoothly to power up key attacks on schedule.",
        f"4. **Bench & Evolution Tempo**: Played {winner_stats['cards_played']} setup/trainer cards to optimize deck momentum.",
        f"5. **Key Turning Points**: Identified {len(turning_points)} crucial prize swing events during the match."
    ]

    report = {
        "replay_file": os.path.basename(replay_file_path),
        "seed": seed,
        "winner": f"Player {winner_idx}",
        "win_reason": win_reason,
        "total_steps": len(steps),
        "total_turns": total_turns,
        "winner_statistics": {
            "total_moves": winner_stats["total_moves"],
            "attacks_performed": winner_stats["attacks_performed"],
            "energies_attached": winner_stats["energies_attached"],
            "cards_played": winner_stats["cards_played"],
            "retreats": winner_stats["retreats"],
            "prizes_taken": winner_stats["prizes_taken"]
        },
        "why_winner_won": why_winner_won,
        "turning_points": turning_points,
        "move_by_move_breakdown": move_analysis
    }

    return report

def generate_markdown_report(report):
    """Converts structured report dictionary into readable Markdown text."""
    md = []
    md.append(f"# Replay Winner Move-by-Move Analysis Report")
    md.append(f"**File**: `{report['replay_file']}`  ")
    md.append(f"**Game Seed**: `{report['seed']}`  ")
    md.append(f"**Winner**: `{report['winner']}` ({report['win_reason']})  ")
    md.append(f"**Match Duration**: {report['total_turns']} turns ({report['total_steps']} steps)\n")

    md.append("## Why the Winner Won (Executive Summary)")
    for reason in report["why_winner_won"]:
        md.append(f"- {reason}")
    md.append("")

    md.append("## Key Game Turning Points")
    if report["turning_points"]:
        for tp in report["turning_points"]:
            md.append(f"- **Turn {tp['turn']} (Step {tp['step']})**: {tp['event']} — *{tp['move']}*")
    else:
        md.append("- No abrupt single turning point detected; consistent tempo win.")
    md.append("")

    md.append("## Winner Statistics Breakdown")
    stats = report["winner_statistics"]
    md.append(f"- **Total Decisive Moves**: {stats['total_moves']}")
    md.append(f"- **Attacks Executed**: {stats['attacks_performed']}")
    md.append(f"- **Energies Attached**: {stats['energies_attached']}")
    md.append(f"- **Cards & Evolutions Played**: {stats['cards_played']}")
    md.append(f"- **Tactical Retreats**: {stats['retreats']}")
    md.append(f"- **Prizes Claimed**: {stats['prizes_taken']}")
    md.append("")

    md.append("## Move-by-Move Specific Breakdown")
    md.append("| Step | Turn | Action | Tactical Category | Strategic Reasoning | Winner Prizes |")
    md.append("| --- | --- | --- | --- | --- | --- |")

    for m in report["move_by_move_breakdown"]:
        tp_flag = " ⭐ **Turning Point**" if m["is_turning_point"] else ""
        md.append(f"| {m['step']} | {m['turn']} | `{m['action']}` | {m['category']} | {m['reasoning']}{tp_flag} | {m['winner_prizes_remaining']} |")

    return "\n".join(md)

def main():
    print("=== PTCG Replay Winner Move-by-Move Analyzer ===")
    
    # Locate replays
    replays_dir = os.path.join(_root_dir, "replays")
    replay_files = []

    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        if os.path.isfile(target_path):
            replay_files = [target_path]
        elif os.path.isdir(target_path):
            replay_files = glob.glob(os.path.join(target_path, "*.json"))
    else:
        if os.path.exists(replays_dir):
            replay_files = glob.glob(os.path.join(replays_dir, "*.json"))
        # Search all subdirectories if needed
        if not replay_files:
            all_jsons = glob.glob(os.path.join(_root_dir, "**", "*.json"), recursive=True)
            replay_files = [f for f in all_jsons if "optimized_weights" not in f and "package.json" not in f and "formatted_dataset" not in f and "analysis_" not in f]

    if not replay_files:
        print("No replay .json files found! Generating a sample replay...")
        os.makedirs(replays_dir, exist_ok=True)
        sample_path = os.path.join(replays_dir, "sample_replay.json")
        sample_data = {
            "seed": 424242,
            "steps": [
                [
                    {"observation": {"current": {"turn": 1, "yourIndex": 0, "players": [{"hand": [{"id": 677, "name": "Riolu"}], "prizes": 6}, {"hand": [], "prizes": 6}]}, "select": {"option": [{"type": "PLAY", "index": 0}]}}, "action": [0], "reward": 0},
                    {"observation": {"current": {"turn": 1, "yourIndex": 1, "players": [{"hand": [], "prizes": 6}, {"hand": [{"id": 675, "name": "Lunatone"}], "prizes": 6}]}}, "action": [0], "reward": 0}
                ],
                [
                    {"observation": {"current": {"turn": 2, "yourIndex": 0, "players": [{"hand": [{"id": 206, "name": "Basic Fighting Energy"}], "prizes": 6}, {"hand": [], "prizes": 6}]}, "select": {"option": [{"type": "ATTACH", "index": 0}]}}, "action": [0], "reward": 0},
                    {"observation": {"current": {"turn": 2, "yourIndex": 1, "players": [{"hand": [], "prizes": 6}, {"hand": [], "prizes": 6}]}}, "action": [0], "reward": 0}
                ],
                [
                    {"observation": {"current": {"turn": 3, "yourIndex": 0, "players": [{"hand": [{"id": 678, "name": "Mega Lucario ex"}], "prizes": 5}, {"hand": [], "prizes": 6}]}, "select": {"option": [{"type": "ATTACK", "attackId": 1}]}}, "action": [0], "reward": 1},
                    {"observation": {"current": {"turn": 3, "yourIndex": 1, "players": [{"hand": [], "prizes": 6}, {"hand": [], "prizes": 6}]}}, "action": [0], "reward": 0}
                ]
            ]
        }
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=2)
        replay_files = [sample_path]

    print(f"Found {len(replay_files)} replay file(s) to analyze.")
    reports = []
    
    for r_file in replay_files:
        try:
            print(f"Analyzing replay: {r_file}...")
            report = analyze_replay(r_file)
            reports.append(report)
            
            # Save individual JSON report
            base_name = os.path.splitext(os.path.basename(r_file))[0]
            out_json = os.path.join(_root_dir, "tools", f"analysis_{base_name}.json")
            out_md = os.path.join(_root_dir, "tools", f"analysis_{base_name}.md")
            
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
                
            md_content = generate_markdown_report(report)
            with open(out_md, "w", encoding="utf-8") as f:
                f.write(md_content)
                
            print(f"  -> Generated analysis JSON: {out_json}")
            print(f"  -> Generated analysis MD:   {out_md}")

        except Exception as e:
            print(f"Error analyzing {r_file}: {e}")

    # Write overall master analysis report
    master_json = os.path.join(_root_dir, "tools", "master_replay_analysis_report.json")
    with open(master_json, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)
    print(f"\n[Success] Master analysis report saved to: {master_json}")

if __name__ == "__main__":
    main()
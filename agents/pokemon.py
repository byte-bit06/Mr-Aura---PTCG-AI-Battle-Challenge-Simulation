"""
pokemon.py — Run a single game (evolved agent vs original baseline) and view the replay.

Usage:
    python pokemon.py

Steps this script performs:
    1. Runs one full game: evolved agent (optimized_weights.json) vs original baseline
    2. Saves the HTML replay to replays/<timestamp>_evolved_vs_baseline.html
    3. Starts a local HTTP server on port 8000
    4. Opens the replay in your default browser automatically
"""

import os
import sys
import datetime
import webbrowser
import threading
import http.server
import socketserver

sys.path.insert(0, ".")
from kaggle_environments import make
import main as evolved_agent
import baseline_agent as original_agent

REPLAYS_DIR = "replays"


def run_game_and_save_replay() -> str:
    """
    Runs evolved agent (P0) vs original baseline (P1).
    Saves the HTML replay to replays/ and returns the file path.
    """
    os.makedirs(REPLAYS_DIR, exist_ok=True)

    print(f"Deck: {len(evolved_agent.my_deck)} cards")
    print("\nPlayer 1 (P0) : Evolved agent  (optimized_weights.json)")
    print("Player 2 (P1) : Original baseline (hardcoded constants)")
    print("\nStarting game...")

    env = make("cabt")
    env.run([evolved_agent.agent, original_agent.agent])

    # ── Result ────────────────────────────────────────────────────────────────
    r0 = env.state[0].reward
    r1 = env.state[1].reward
    print(f"\nGame over after {len(env.steps)} steps")
    print(f"  P0 Evolved   reward={r0}")
    print(f"  P1 Baseline  reward={r1}")
    if r0 > r1:
        outcome = "WIN"
        print("  => Evolved agent WINS")
    elif r1 > r0:
        outcome = "LOSS"
        print("  => Original baseline WINS")
    else:
        outcome = "DRAW"
        print("  => Draw")

    # ── Save replay ───────────────────────────────────────────────────────────
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_evolved_vs_baseline_{outcome}.html"
    path = os.path.join(REPLAYS_DIR, name)

    html = env.render(mode="html")
    csp  = '<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">'
    html = html.replace("<head>", f"<head>\n{csp}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nReplay saved -> {os.path.abspath(path)}")
    return path


def serve_and_open(replay_path: str, port: int = 8000) -> None:
    """Serve the project root over HTTP and open the replay in the browser."""

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    # Use a port that isn't already taken by the existing server
    while True:
        try:
            server = socketserver.TCPServer(("", port), QuietHandler)
            break
        except OSError:
            port += 1

    rel_path = os.path.relpath(replay_path).replace("\\", "/")
    url = f"http://localhost:{port}/{rel_path}"

    def _serve():
        with server:
            server.serve_forever()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    print(f"\nHTTP server: http://localhost:{port}")
    print(f"Opening   : {url}")
    webbrowser.open(url)
    print("\nPress Ctrl+C to stop.")
    try:
        t.join()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    replay_path = run_game_and_save_replay()
    serve_and_open(replay_path)
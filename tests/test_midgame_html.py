import sys, os, json
sys.path.insert(0, '.')
from kaggle_environments import make
from kaggle_environments.envs.cabt.cg.game import visualize_data
from kaggle_environments.envs.cabt.cabt import html_renderer

def save_midgame_html(env, filename="midgame.html"):
    vis = json.loads(visualize_data())
    # The visualizer expects env.steps[0][0]["visualize"] to contain `vis`
    # We can create a fake steps array to pass to the template
    fake_steps = [[{"visualize": vis}]]
    html = html_renderer()
    
    # We need to wrap it similar to core.py render
    # kaggle_environments/core.py does something like:
    # html = html.replace("{{ steps }}", json.dumps(steps))
    # Actually, Kaggle environments injects it via a specific JS payload.
    # Let's just use the built-in env.render() but temporarily mutate env.steps!
    
    original_vis = env.steps[0][0].get("visualize")
    env.steps[0][0]["visualize"] = vis
    try:
        out_html = env.render(mode="html")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(out_html)
    finally:
        if original_vis is not None:
            env.steps[0][0]["visualize"] = original_vis
        else:
            del env.steps[0][0]["visualize"]

global_env = None
turn_count = 0

def agent(obs):
    global turn_count
    turn_count += 1
    if turn_count == 3:
        save_midgame_html(global_env, "midgame_test.html")
        print("Saved midgame_test.html!")
        # force exit
        sys.exit(0)
    return []

if __name__ == "__main__":
    global_env = make("cabt")
    global_env.run([agent, agent])

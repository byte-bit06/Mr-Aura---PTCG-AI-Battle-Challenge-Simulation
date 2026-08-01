import sys
sys.path.insert(0, '.')
from kaggle_environments import make

global_env = None

def agent(obs):
    if global_env:
        try:
            html = global_env.render(mode='html')
            with open("test_midgame.html", "w") as f:
                f.write(html)
            print("Wrote test_midgame.html!")
        except Exception as e:
            print("Failed to render:", e)
    return []

if __name__ == "__main__":
    global_env = make("cabt")
    global_env.run([agent, agent])

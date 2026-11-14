# Mr Aura: Pokémon TCG AI Battle Challenge agent

**Best rank: Top 300** of 7,000 teams in the PTCG AI Battle Challenge.

Pokémon TCG is a hard game for AI: you can't see your opponent's hand or deck, the draws are random, and one turn can contain dozens of chained decisions. This repo has our agent and all the tooling we built to train, test and improve it. It holds 148+ commits across 12+ agent versions.

**Team of three:** [@byte-bit06](https://github.com/byte-bit06), [@OmBhatt15](https://github.com/OmBhatt15) and [@Bhatman00](https://github.com/Bhatman00). The deck-specific experiments live on branches (`Shaurya-Alakazam`, `Shaurya-Dragpult`, and others).

## How the agent decides

| Layer | What it does |
|---|---|
| **Heuristic evaluator** | Scores a board using about 48 weighted features: prize race, damage reach, energy attachment, HP ratios, comeback scaling, matchup-specific rules |
| **Search** | A heuristic-guided **Monte Carlo Tree Search**. It **samples the hidden information** (opponent hand and deck) to handle imperfect information, then runs a **2-ply minimax** over candidate turns |
| **Time management** | A strict per-turn time budget (1.2 s) with a deadline-aware greedy fallback, so the agent never times out |
| **Matchup awareness** | Infers the opponent's archetype from visible cards and switches its leaf-evaluation heuristics (e.g. against Dragapult, Grimmsnarl or Crustle) |

## How it was trained and tuned

- **Genetic algorithm** (`training/train_genetic.py`): each generation mutates the champion's weights with Gaussian noise, plays candidates against a baseline and keeps the winner.
- **Bayesian optimisation** (`Network_training/train_bayesian.py`) for the 48-variable heuristic weights.
- **DAgger imitation learning** (`training/dagger_loop.py`, `training/train_dagger.py`): collects expert-corrected state-action pairs and fits weights to them.
- **LLM fine-tuning pipeline** (`llm_training/`): formats winning replays into instruction data and fine-tunes Llama 3.1 8B with **LoRA (Unsloth)**.
- **Benchmarking** against the top-20 meta decks (`Network_training/opponents/`), with win/loss tracked per version in `model_version_history.md`.

## Tooling

- `replay_anaylzer.py`: parses replays into readable move logs and Markdown reports
- `tools/adaptive_learning.py`: turns replay analysis into weight updates, imitation data and a strategy guide
- `tools/launch_visualizer.py`: a browser-based replay visualiser

## Repo layout

```
main.py                 competition agent (Kaggle entry point)
agents/                 baseline + reference agents
training/               genetic, DAgger and supervised training loops
Network_training/       agent versions (Wall V1-V12, Alakazam, Dragapult) and evaluations
llm_training/           LoRA fine-tuning pipeline
tools/                  replay analysis, deck building, visualiser
ptcg_engine/            competition-provided C++ game engine (competition-use licence)
```

## Run

```bash
pip install kaggle-environments numpy
python main.py              # local self-play
python training/train_genetic.py
```

*The game engine in `ptcg_engine/` and `cg/` is supplied by the competition under its own licence. The agent, training and tooling code is ours.*

# PTCG Agent Version History: Crustle Wall Deck

This document outlines the architectural changes, heuristic weight updates, and performance metrics across the different iterations of the Crustle Wall rule-based agent.

---

## **Wall_V1 (Base Pre-Training Model)**
This was the baseline model configured with the initial heuristic weights.

### **Core Heuristics**
- **Static Play Priorities**: Actions like evolving, playing support cards, and attaching energies were given static base scores (`~80,000` for evolving, `~60,000` for playing, `~40,000` for attaching).
- **Basic Lethal Check**: The bot only recognized a knockout opportunity if the opponent's active Pokémon had `<= 50 HP`.
- **Walling Focus**: Prioritized switching to Crustle when facing an EX Pokémon and Ogerpon when facing Ability-heavy Pokémon.

### **Known Weaknesses**
- Missed knockouts because the 50 HP threshold ignored high-damage attacks from Crustle (130 dmg) and Ogerpon (140 dmg).
- Frequently retreated or stalled with Boss's Orders instead of taking free prize cards.
- Could easily over-saturate energy attachments on a single Pokémon (attaching 5+ energies to a single wall).
- Played Kangaskhan ex onto the bench in the late game, opening itself up to a 2-prize Boss's Orders loss.

---

## **Wall_V2 (Optimized & Bug-Fixed)**
This version incorporates the results of a 50,000-game genetic algorithm training loop against a 6-deck Meta Gauntlet, alongside critical heuristic bug fixes to ensure it reliably takes prize cards.

### **Major Changes & Bug Fixes**
1. **Dynamic Lethal Thresholds**
   - The agent now calculates lethal based on its active Pokémon: **Crustle (130 HP)** and **Ogerpon (140 HP)**. 
   - If the opponent is within this range, the agent recognizes the knockout opportunity.

2. **Bench-Out Win Prioritization**
   - If the agent has a knockout on the opponent's active Pokémon and the opponent has **0 benched Pokémon**, it applies a massive `+200,000` score bonus to `ATTACK`.
   - This overrides all other `PLAY`, `ATTACH`, and `HEAL` actions to instantly secure the bench-out victory without risking decking out or misplaying.

3. **Anti-Stall Boss's Orders Guardrail**
   - If the agent can already knock out the opponent's active Pokémon, it applies a `-50,000` penalty to Boss's Orders and Switch.
   - This physically prevents the bot from ruining its own knockout by dragging up a fresh Pokémon to "stall". 
   - However, if the opponent has a 2-prize EX Pokémon on the bench that is within lethal range, Boss's Orders is heavily prioritized to secure the snipe.

4. **Energy Saturation Guardrail**
   - Prevents the agent from attaching more than 3 energies to Crustle/Ogerpon or 4 to Kangaskhan, applying a `-50,000` penalty for over-saturating.

5. **Kangaskhan Late-Game Ban**
   - When our remaining prize cards are `<= 3`, the bot applies a massive penalty to playing Kangaskhan ex from the hand to the bench, preventing the opponent from exploiting a free 2-prize target (unless we desperately need damage against a high HP threat).

### **Performance Evaluation (Showdown against Meta)**
*Evaluation run via `evaluate_model.py` (2 games per opponent).*

| Opponent | Win | Loss | Tie |
| :--- | :--- | :--- | :--- |
| **Lucario ex** | 1 | 1 | 0 |
| **Iono Deck** | 0 | 2 | 0 |
| **Dragapult ex** | 0 | 2 | 0 |
| **Abomasnow ex** | 0 | 2 | 0 |
| **MCTS Lucario** | 0 | 2 | 0 |
| **Archaludon Cinderace** | 0 | 2 | 0 |
| **Wall_V1 (Self-Play)** | 1 | 2 | 0 |

> [!WARNING]
> **Performance Note:** 
> The initial evaluation for Wall_V2 was run *before* the critical lethal and Boss's Orders logic was fixed. Because it was heavily prioritizing retreating over attacking (due to `ATTACK` scoring lower than `RETREAT`), its win rate dropped severely. 
> 
> **Next Steps:** With the new heuristic patches active in `Wall_V2`, running another evaluation will likely yield vastly improved win rates as it will finally take the prize cards it was missing.

## **Wall_V3 (Wall Fixes, Immunity Pivot & Energy Lock)**
This version fixes several critical heuristics: misallocation of wall Pokémon, blindly attacking into immune Pokémon, and energy hoarding.

### **Major Changes**
1. **EX Targeting**: If the opponent is an EX Pokémon, the agent will now strictly deploy Crustle. Dwebble (which lacks immunity) was removed from this priority list.
2. **Ogerpon Specificity**: Ogerpon is now only deployed if the opponent has an Ability AND is a non-EX Pokémon. Previously, it would improperly deploy against EX Pokémon with abilities, resulting in taking full damage.
3. **Immunity Detection**: The agent actively cross-references the opponent's Effect Explanation (checking for Ability or EX damage prevention) against our Active Pokémon's traits.
4. **Pivot Incentives**: If our attack is nullified, the agent will heavily penalize ATTACK (-100k) and heavily boost the scores for playing Switch or Boss's Orders (+20k) to immediately pivot out of the bad matchup.
5. **Strict Energy Saturation**: Once a primary attacker (Kangaskhan, Crustle, Ogerpon) reaches 3 energy cards, the agent locks its attachment priority score below zero, completely cutting off further energy waste and forcing all future attachments onto the bench.

6. **Boss's Orders Aggression**: Fixed passive/aimless target dragging. Boss's Orders is now strictly restricted to Walls for evasion stalling. If Kangaskhan is active, it will exclusively use Boss's Orders for aggressive sniping. Target selection now actively calculates HP and prioritizes dragging up the weakest benched Pokémon for instant prize clean-up.
7. **Active Swapping Priority**: When a Pokémon is knocked out, the agent now calculates the total energy on every benched Pokémon and aggressively forces the most-energized attacker into the active spot, preventing it from stranding a dead-weight unenergized Kangaskhan out front.

8. **Anti-Bricking Supporter Priority**: Implemented a hard exponential scaling trigger: whenever the agent's hand size falls below 4, the scoring weights for hand-refresh supporters (Lillie's Determination, Team Rocket's Petrel) are massively boosted (+50,000). This prevents the agent from slowly playing out low-impact items while starving itself of resources.

## Wall_V3_Bayesian (In Progress)
- **Architecture Shift**: Replaced primitive linear/percentage-based Genetic Evolution loop with **Bayesian Optimization (Optuna/TPE)** to efficiently navigate the high-dimensional 48-variable heuristic space.
- **Parametrization**: Successfully extracted all 48 core decision heuristics (draw engines, active swapping, boss snipes, attach saturation limits) into _WEIGHT_DEFAULTS to allow mathematical modeling by the Bayesian engine.

## Wall_V4 (Heuristic-Guided MCTS)
- **Architecture Shift**: Shifted from pure heuristics to Monte Carlo Tree Search (MCTS).
- **Leaf Node Evaluator**: Integrated the perfectly tuned 48-variable Bayesian heuristic weights as the state evaluator at the MCTS search depth, allowing Wall_V4 to tactically foresee and perfectly evaluate board states 3-5 turns in the future.

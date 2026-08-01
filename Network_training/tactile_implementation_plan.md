# Tactile Logic Integration Plan

To make the AI actually pilot the **Crustle Wall Deck** according to your strategy, we need to convert the human-readable text from `tactile_documentation.txt` into hard math inside `main.py`. 

Because you want this agent to be optimized by the Genetic Algorithm, we will externalize the value of these strategic decisions into `optimized_weights.json`.

## Proposed Changes

### `Network_training/optimized_weights.json`
We will add new tunable weights based directly on your document:
*   `"play_poffin_dwebble_bonus"` (Goal: Setup Dwebbles early)
*   `"heal_jumbo_ice_cream_bonus"` (Goal: Heal Kangaskhan/Ogerpon from big hits)
*   `"play_lillie_draw_bonus"` (Goal: Prioritize Lillie as the primary draw engine)
*   `"play_factory_petrel_combo_bonus"` (Goal: Synergize Factory and Petrel)
*   `"play_boss_orders_disrupt_bonus"` (Goal: Disrupt or target weak bench)
*   `"play_xerosic_disrupt_bonus"` (Goal: Slow down opponent tempo)

### `Network_training/train_genetic.py`
*   [MODIFY] I will update the fallback `load_base_weights()` function so it perfectly matches our new expanded JSON file (and fix the `kangaskhan_active` name you noticed!).

### `Network_training/main.py`
We will expand the `agent(obs_dict)` function to actively look for these combos in the Kaggle Observation dictionary:
*   **Healing Logic:** When evaluating the `PLAY` option for *Jumbo Ice Cream*, check if the active Kangaskhan or Ogerpon has taken damage. If so, apply the massive healing bonus.
*   **Setup Logic:** When evaluating the `PLAY` option for *Buddy-Buddy Poffin*, heavily reward it if we don't have Dwebbles on the bench yet.
*   **Synergy Logic:** When choosing a Supporter, if *Team Rocket's Factory* is the active Stadium, multiply the score of playing *Team Rocket's Petrel*.
*   **Draw Priority:** Ensure *Lillie's Determination* inherently scores higher than *Morty's Conviction* unless the hand is empty.


# Wall V5: Replay Loss Analysis & Tactical Rule Development

---

## Executive Summary

An empirical audit of **Wall V5** replay logs (both local gauntlet matches and Kaggle online submission replays `89287503.json` – `89301635.json`) revealed **4 core failure modes** that cause V5 to lose games despite having a strong wall core:

1. **Alakazam ex One-Shots (Powerful Hand 240+ Damage)**: Opponents using Alakazam ex build 12–14 card hands via Dudunsparce. Their attack hits for **240–280 damage**, which one-shots Crustle even with Hero's Cape attached.
2. **Un-Evolved Dwebble Stranding in Active**: Dwebble (60 HP) gets stranded in the Active position without evolving or switching, allowing opponents to take easy 1-turn KOs.
3. **Ogerpon ex Matchup Mis-Placement**: Ogerpon ex (117) gets fielded into Active against non-Ability attackers (e.g. Crustle 345 or non-EX hitters) where its immunity does not apply, giving away 2 prize cards.
4. **Bench-Out Elimination**: When V5's Active wall falls, V5 occasionally has 0 benched Pokémon remaining, triggering an instant automatic defeat.

---

## Detailed Replay Loss Breakdown

| Replay File | Opponent | Loss Cause | Exact Game State at Defeat |
|:---|:---|:---|:---|
| `89292393.json` | **Alakazam ex** | Active Dwebble Stranding | Un-evolved **Dwebble (344)** in Active at Step 108. Alakazam hit for 180+ damage. |
| `89300546.json` | **Alakazam ex** | 240+ Damage One-Shot | **Crustle (345)** in Active at Step 170. Opponent had 12 cards in hand (240 damage), bypassing Crustle's HP pool. |
| `89289687.json` | **Crustle Wall** | Ogerpon Mis-Placement | **Ogerpon ex (117)** fielded into Active against opponent Crustle. Crustle has no Ability, so Ogerpon took full damage and lost. |
| `89290783.json` | **Iono / Midrange** | Bench-Out Loss | Active KO'd at Step 188 with **0 benched Pokémon** remaining. |
| `89295667.json` | **Abomasnow ex** | Bench-Out Loss | Active KO'd at Step 113 with **0 benched Pokémon** remaining. |
| `89301635.json` | **Grimmsnarl ex** | Bench Snipe / Special Discard | **Ogerpon ex** active without Mist Energy protection; opponent bench-sniped backup basic Dwebbles. |

---

## 5 New Tactical Rules to Develop (Wall V6 Roadmap)

### Rule 1: Anti-Alakazam Hand Disruption Protocol (Iono Emergency)
* **Problem**: Alakazam ex scales damage by hand size (20x cards). At 12 cards in hand, it deals 240 damage and 1-shots our highest-HP wall.
* **New Rule**: If `opponent_hand_size >= 6`, playing **Iono (1182)** gets **EMERGENCY PRIORITY (`score = 1,500,000.0`)**.
* **Effect**: Forces the opponent to shuffle their 12-card hand back into their deck and redraw down to their prize count (1–6 cards), instantly reducing Alakazam's damage output from 240+ down to **20–120 damage**!

---

### Rule 2: Active Pivot & Lead Guard (No Stranded Dwebbles)
* **Problem**: Dwebble (60 HP) gets stuck in Active on Turn 2+ if Crustle isn't drawn yet, becoming a free prize target.
* **New Rule**:
  1. If Active is Dwebble and `turn >= 2`, playing **Switch (14)** or evolving into **Crustle (345)** is rated **`score = 1,450,000.0`**.
  2. If Dwebble cannot evolve and no Switch is in hand, energy attachment prioritizes retreat cost over attacking.

---

### Rule 3: Strict Immunity Validation for Ogerpon ex
* **Problem**: Ogerpon ex is currently fielded against non-Ability Pokemon where it receives full damage while offering 2 prize cards on KO.
* **New Rule**:
  ```python
  # Only promote or switch to Ogerpon ex if:
  # 1. Opponent Active HAS an Ability AND is NOT an EX
  # 2. OR Opponent Active relies exclusively on Ability-based damage
  if opp_has_ability and not opp_is_ex:
      optimal_active = Ogerpon
  else:
      optimal_active = Crustle  # Crustle is ALWAYS safer vs non-ability & EX hitters
  ```

---

### Rule 4: Triple-Bench Safety Net (Bench-Out Protection)
* **Problem**: Dropping to 0 bench cards results in an automatic loss the moment the Active wall is KO'd.
* **New Rule**:
  - `bench_count == 0`: **EMERGENCY SCORE = 1,600,000.0** (Highest priority in game, above attacks!)
  - `bench_count == 1`: **HIGH SCORE = 600,000.0** (Bench a backup Dwebble or Ogerpon before taking secondary actions)

---

### Rule 5: Special Energy Re-Attachment & Hammer Protection
* **Problem**: Enhanced Hammer discards our Mist Energy (11), leaving Crustle vulnerable to status/attack effects.
* **New Rule**:
  - Track discarded Mist Energies. If opponent has Enhanced Hammer capability, prioritize playing **Earthen Vessel (1227)** or **Night Stretcher (1097)** to recover and re-attach Grass/Mist Energy immediately.

---

## Action Plan for V6 Implementation

```
1. Add Iono Hand Disruption check (if opp_hand >= 6 -> Iono score = 1.5M)
2. Add Active Dwebble Emergency Switch rule (if active == Dwebble and turn >= 2 -> Switch score = 1.45M)
3. Refine Ogerpon ex promotion condition to strictly require non-EX Ability targets
4. Re-package V6 submission and run 10-game evaluation gauntlet
```

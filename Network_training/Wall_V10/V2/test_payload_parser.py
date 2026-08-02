"""
test_payload_parser.py — Interactive Payload Parser & AI Decision Inspector
=============================================================================
Allows you to paste any raw game state JSON payload and see exactly:
  1. How all data fields (board state, active/bench, energies, hand, opponent bench) are extracted.
  2. How resolve_card_id maps each option to Card IDs and Names from EN_Card_Data copy.csv.
  3. How the AI evaluates each IF-statement rule branch and chooses the winning action.

Usage:
  python test_payload_parser.py
  (Or pass a JSON file path: python test_payload_parser.py sample_payload.json)
"""

import os
import sys
import json
import csv

_this_dir = os.path.dirname(os.path.abspath(__file__))
_network_training_dir = os.path.abspath(os.path.join(_this_dir, '..', '..'))
if _network_training_dir not in sys.path:
    sys.path.insert(0, _network_training_dir)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import Wall_V10.V2.main as v2_main

# Sample Payload provided by User
SAMPLE_PAYLOAD_JSON = """{
  "current": {
    "energyAttached": false,
    "firstPlayer": 0,
    "looking": null,
    "players": [
      {
        "active": [
          {
            "appearThisTurn": true,
            "energies": [],
            "energyCards": [],
            "hp": 80,
            "id": 742,
            "maxHp": 80,
            "playerIndex": 0,
            "preEvolution": [
              {
                "id": 741,
                "playerIndex": 0,
                "serial": 18
              }
            ],
            "serial": 21,
            "tools": []
          }
        ],
        "asleep": false,
        "bench": [
          {
            "appearThisTurn": true,
            "energies": [],
            "energyCards": [],
            "hp": 80,
            "id": 742,
            "maxHp": 80,
            "playerIndex": 0,
            "preEvolution": [
              {
                "id": 741,
                "playerIndex": 0,
                "serial": 20
              }
            ],
            "serial": 24,
            "tools": []
          },
          {
            "appearThisTurn": false,
            "energies": [],
            "energyCards": [],
            "hp": 70,
            "id": 305,
            "maxHp": 70,
            "playerIndex": 0,
            "preEvolution": [],
            "serial": 14,
            "tools": []
          }
        ],
        "benchMax": 5,
        "burned": false,
        "confused": false,
        "deckCount": 34,
        "discard": [
          {
            "id": 1086,
            "playerIndex": 0,
            "serial": 37
          }
        ],
        "hand": [
          {
            "id": 19,
            "playerIndex": 0,
            "serial": 6
          },
          {
            "id": 1079,
            "playerIndex": 0,
            "serial": 29
          },
          {
            "id": 1081,
            "playerIndex": 0,
            "serial": 34
          },
          {
            "id": 1225,
            "playerIndex": 0,
            "serial": 54
          },
          {
            "id": 1197,
            "playerIndex": 0,
            "serial": 50
          },
          {
            "id": 743,
            "playerIndex": 0,
            "serial": 26
          },
          {
            "id": 743,
            "playerIndex": 0,
            "serial": 27
          },
          {
            "id": 1129,
            "playerIndex": 0,
            "serial": 41
          },
          {
            "id": 19,
            "playerIndex": 0,
            "serial": 7
          },
          {
            "id": 5,
            "playerIndex": 0,
            "serial": 3
          },
          {
            "id": 1266,
            "playerIndex": 0,
            "serial": 62
          },
          {
            "id": 1231,
            "playerIndex": 0,
            "serial": 58
          },
          {
            "id": 741,
            "playerIndex": 0,
            "serial": 17
          },
          {
            "id": 1152,
            "playerIndex": 0,
            "serial": 43
          }
        ],
        "handCount": 14,
        "paralyzed": false,
        "poisoned": false,
        "prize": [
          null,
          null,
          null,
          null,
          null,
          null
        ]
      },
      {
        "active": [
          {
            "appearThisTurn": false,
            "energies": [
              0
            ],
            "energyCards": [
              {
                "id": 11,
                "playerIndex": 1,
                "serial": 110
              }
            ],
            "hp": 150,
            "id": 345,
            "maxHp": 150,
            "playerIndex": 1,
            "preEvolution": [
              {
                "id": 344,
                "playerIndex": 1,
                "serial": 63
              }
            ],
            "serial": 68,
            "tools": []
          }
        ],
        "asleep": false,
        "bench": [
          {
            "appearThisTurn": false,
            "energies": [],
            "energyCards": [],
            "hp": 70,
            "id": 344,
            "maxHp": 70,
            "playerIndex": 1,
            "preEvolution": [],
            "serial": 66,
            "tools": []
          }
        ],
        "benchMax": 5,
        "burned": false,
        "confused": false,
        "deckCount": 41,
        "discard": [
          {
            "id": 1122,
            "playerIndex": 1,
            "serial": 92
          },
          {
            "id": 1227,
            "playerIndex": 1,
            "serial": 74
          },
          {
            "id": 1086,
            "playerIndex": 1,
            "serial": 104
          }
        ],
        "hand": null,
        "handCount": 6,
        "paralyzed": false,
        "poisoned": false,
        "prize": [
          null,
          null,
          null,
          null,
          null,
          null
        ]
      }
    ],
    "result": -1,
    "retreated": false,
    "stadium": [],
    "stadiumPlayed": false,
    "supporterPlayed": false,
    "turn": 3,
    "turnActionCount": 7,
    "yourIndex": 0
  },
  "logs": [
    {
      "cardId": 1231,
      "playerIndex": 0,
      "serial": 58,
      "type": 4
    },
    {
      "cardId": 741,
      "playerIndex": 0,
      "serial": 17,
      "type": 4
    },
    {
      "cardId": 1152,
      "playerIndex": 0,
      "serial": 43,
      "type": 4
    },
    {
      "cardId": 66,
      "fromArea": 5,
      "playerIndex": 0,
      "serial": 11,
      "toArea": 1,
      "type": 6
    },
    {
      "cardId": 305,
      "fromArea": 10,
      "playerIndex": 0,
      "serial": 13,
      "toArea": 1,
      "type": 6
    },
    {
      "playerIndex": 0,
      "type": 0
    }
  ],
  "remainingOverageTime": 599.3217420000001,
  "select": {
    "context": 0,
    "contextCard": null,
    "deck": null,
    "effect": null,
    "maxCount": 1,
    "minCount": 1,
    "option": [
      {
        "area": 2,
        "inPlayArea": 4,
        "inPlayIndex": 0,
        "index": 0,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 5,
        "inPlayIndex": 0,
        "index": 0,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 5,
        "inPlayIndex": 1,
        "index": 0,
        "type": 8
      },
      {
        "index": 2,
        "type": 7
      },
      {
        "index": 3,
        "type": 7
      },
      {
        "index": 4,
        "type": 7
      },
      {
        "area": 2,
        "inPlayArea": 4,
        "inPlayIndex": 0,
        "index": 8,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 5,
        "inPlayIndex": 0,
        "index": 8,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 5,
        "inPlayIndex": 1,
        "index": 8,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 4,
        "inPlayIndex": 0,
        "index": 9,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 5,
        "inPlayIndex": 0,
        "index": 9,
        "type": 8
      },
      {
        "area": 2,
        "inPlayArea": 5,
        "inPlayIndex": 1,
        "index": 9,
        "type": 8
      },
      {
        "index": 10,
        "type": 7
      },
      {
        "index": 11,
        "type": 7
      },
      {
        "index": 12,
        "type": 7
      },
      {
        "index": 13,
        "type": 7
      },
      {
        "type": 14
      }
    ],
    "remainDamageCounter": 0,
    "remainEnergyCost": 0,
    "type": 0
  },
  "step": 23
}"""

def inspect_payload(payload_data):
    if isinstance(payload_data, str):
        obs = json.loads(payload_data)
    else:
        obs = payload_data

    current = obs.get("current", {})
    select_data = obs.get("select", {})
    
    my_idx = current.get("yourIndex", 0)
    opp_idx = 1 - my_idx
    players = current.get("players", [])

    print("=" * 80)
    print("=== 1. PLAYER ROLE & GAME STATE EXTRACTION ===")
    print("=" * 80)
    print(f"  Your Player Index:    Player {my_idx} (US)")
    print(f"  Opponent Index:       Player {opp_idx} (OPPONENT)")
    print(f"  Turn Number:          Turn {current.get('turn', 1)}")
    print(f"  Supporter Played:     {current.get('supporterPlayed', False)}")
    print(f"  Energy Attached:      {current.get('energyAttached', False)}")
    print(f"  Stadium Played:       {current.get('stadiumPlayed', False)}")
    print(f"  Retreated:            {current.get('retreated', False)}")

    info = v2_main.extract_board_info(obs)

    print("\n" + "=" * 80)
    print("=== 2. OUR BOARD STATE EXTRACTION (PLAYER INDEX = {}) ===".format(my_idx))
    print("=" * 80)
    my_act = info.get("my_active")
    if my_act:
        act_id = info.get("my_active_id")
        print(f"  Active Pokemon:      {v2_main.get_card_name(act_id)} (Card ID #{act_id})")
        print(f"    HP:                {info.get('my_active_hp')}/{info.get('my_active_max_hp')} HP")
        print(f"    Energy Attached:   {info.get('my_active_energy')} energy card(s)")
        print(f"    Tools:             {my_act.get('tools', [])}")
        print(f"    Pre-Evolutions:    {my_act.get('preEvolution', [])}")
    else:
        print("  Active Pokemon:      None")

    my_b = info.get("my_bench", [])
    print(f"  Bench Pokemon ({len(my_b)}/5):")
    for idx, b in enumerate(my_b):
        b_id = v2_main._get_val(b, "id")
        b_hp = v2_main._get_val(b, "hp", 0)
        b_max = v2_main._get_val(b, "maxHp", 0)
        b_e = len(v2_main._get_val(b, "energies") or [])
        print(f"    Bench [{idx}]:         {v2_main.get_card_name(b_id)} (Card ID #{b_id}) | HP: {b_hp}/{b_max} | Energy: {b_e}")

    hand = info.get("hand", [])
    print(f"  Hand Cards ({len(hand)} cards):")
    for idx, cid in enumerate(hand):
        print(f"    Hand [{idx}]:          {v2_main.get_card_name(cid)} (Card ID #{cid})")

    print("\n" + "=" * 80)
    print("=== 3. OPPONENT BOARD STATE EXTRACTION (PLAYER INDEX = {}) ===".format(opp_idx))
    print("=" * 80)
    opp_act = info.get("opp_active")
    if opp_act:
        act_id = info.get("opp_active_id")
        print(f"  Active Pokemon:      {v2_main.get_card_name(act_id)} (Card ID #{act_id})")
        print(f"    HP:                {info.get('opp_active_hp')}/{opp_act.get('maxHp', 0)} HP")
        print(f"    Energy Attached:   {info.get('opp_active_energy')} energy card(s)")
        print(f"    Is EX:             {info.get('opp_is_ex')}")
        print(f"    Has Ability:       {info.get('opp_has_ability')}")
    else:
        print("  Active Pokemon:      None")

    opp_b = info.get("opp_bench", [])
    print(f"  Bench Pokemon ({len(opp_b)} benched):")
    for idx, b in enumerate(opp_b):
        b_id = v2_main._get_val(b, "id")
        b_hp = v2_main._get_val(b, "hp", 0)
        b_max = v2_main._get_val(b, "maxHp", 0)
        b_e = len(v2_main._get_val(b, "energies") or [])
        b_p_idx = v2_main._get_val(b, "playerIndex", opp_idx)
        print(f"    Bench [{idx}]:         {v2_main.get_card_name(b_id)} (Card ID #{b_id}) | HP: {b_hp}/{b_max} | Energy: {b_e} | PlayerIndex: {b_p_idx}")

    print("\n" + "=" * 80)
    print("=== 4. OPTIONS RESOLUTION & AI EVALUATION ===")
    print("=" * 80)
    options = select_data.get("option", [])
    for idx, o in enumerate(options):
        cid = v2_main.resolve_card_id(o, info, current, select_data)
        c_name = v2_main.get_card_name(cid)
        o_type = o.get("type")
        area = o.get("area")
        in_idx = o.get("index")
        in_play_area = o.get("inPlayArea")
        in_play_idx = o.get("inPlayIndex")

        type_desc = {
            1: "Play Basic Pokemon to Bench",
            3: "Play Supporter / Trainer Item",
            4: "Evolve Benched Pokemon",
            7: "Play Supporter / Trainer Item",
            8: "Attach Energy Card",
            9: "Attach Tool Card",
            10: "Play Stadium Card",
            13: "Use Attack",
            14: "System Action / End Turn"
        }.get(o_type, f"Action Type {o_type}")

        print(f"  Option [{idx}]: {type_desc}")
        print(f"    Resolved Card ID:  {cid} ({c_name})")
        print(f"    Raw Option Payload: {o}")

    action = v2_main.agent(obs)

    print("\n" + "=" * 80)
    print("=== 5. AI FINAL CHOSEN MOVE ===")
    print("=" * 80)
    print(f"  Action Payload Returned: {action}")
    if isinstance(action, dict) and "index" in action:
        chosen_indices = action["index"]
        print(f"  Selected Option Index:   {chosen_indices}")
        for c_idx in chosen_indices:
            if 0 <= c_idx < len(options):
                chosen_o = options[c_idx]
                chosen_cid = v2_main.resolve_card_id(chosen_o, info, current, select_data)
                print(f"  Chosen Action Detail:    Option {c_idx} -> {v2_main.get_card_name(chosen_cid)} (Card ID #{chosen_cid})")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            payload = json.load(f)
        inspect_payload(payload)
    else:
        print("Parsing Sample User Payload:\n")
        inspect_payload(SAMPLE_PAYLOAD_JSON)

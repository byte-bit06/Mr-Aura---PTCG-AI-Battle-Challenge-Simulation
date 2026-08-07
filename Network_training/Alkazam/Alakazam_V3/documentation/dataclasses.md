Data Classes
classapi.Card(id, serial, playerIndex)
Represents a basic card entity with ID, serial number, and owning player.

id: int
CardData ID.

playerIndex: int
Represents which player’s card.

serial: int
Serial Number. A unique value assigned to each card in the match.

classapi.Pokemon(id, serial, hp, maxHp, appearThisTurn, energies, energyCards, tools, preEvolution)
Detailed Pokémon state including HP, energy, tools, and evolution info.

appearThisTurn: bool
True if played this turn.

energies: list[EnergyType]
Energies Array

energyCards: list[Card]
Attached Energy Card Array

hp: int
Current HP.

id: int
CardData ID.

maxHp: int
Current Max HP.

preEvolution: list[Card]
Pre-evolution Card Array

serial: int
Serial Number. A unique value assigned to each card in the match.

tools: list[Card]
Attached Pokémon Tool Array

classapi.PlayerState(active, bench, benchMax, deckCount, discard, prize, handCount, hand, poisoned, burned, asleep, paralyzed, confused)
Current in-game state of an individual player.

active: list[Pokemon | None]
Active Pokémon (None if the card is facedown). The array size is either 0 or 1.

asleep: bool
Active Pokémon is Asleep.

bench: list[Pokemon]
Bench Pokémon.

benchMax: int
Maximum Bench Count.

burned: bool
Active Pokémon is Burned.

confused: bool
Active Pokémon is Confused.

deckCount: int
Remaining Cards in Deck.

discard: list[Card]
Discard pile Card Array.

hand: list[Card] | None
Hand Card Array. None for the opponent.

handCount: int
Number of Cards in Hand.

paralyzed: bool
Active Pokémon is Paralyzed.

poisoned: bool
Active Pokémon is Poisoned.

prize: list[Card | None]
Prize cards (None if the card is facedown). The first element is the bottom of the prize, and the last element is the top.

classapi.State(turn, turnActionCount, yourIndex, firstPlayer, supporterPlayed, stadiumPlayed, energyAttached, retreated, result, stadium, looking, players)
Current game state including turn count, player indices, and stadium card.

energyAttached: bool
True if the manual Energy attachment for this turn has already been used.

firstPlayer: int
Starting Player Index. When the starting player has not been determined, the value is -1.

looking: list[Card | None] | None
Looking cards (None if the card is facedown). None if not looking cards.

players: list[PlayerState]
An array of player states. The number of elements is 2.

result: int
Win player index. -1 if not battle finished.

retreated: bool
True if retreated this turn.

stadium: list[Card]
Stadium Card. The array size is either 0 or 1.

stadiumPlayed: bool
True if a stadium has already been used this turn.

supporterPlayed: bool
True if a supporter has already been used this turn.

turn: int
Turn Count. 1 indicates the first turn for the starting player. 2 indicates the first turn for the second player. 3 indicates the second turn for the starting player. 0 denotes a time before the starting player’s first turn.

turnActionCount: int
Number of Actions Taken This Turn.

yourIndex: int
Which player is making the selection? (Your Player Index.) 0 or 1.

classapi.Option(type, number=None, area=None, index=None, playerIndex=None, toolIndex=None, energyIndex=None, count=None, inPlayArea=None, inPlayIndex=None, attackId=None, cardId=None, serial=None, specialConditionType=None)
A single selectable option shown to the agent or player.

area: AreaType | None= None
Area where the card is located.

attackId: int | None= None
ID of the attack.

cardId: int | None= None
ID of the card.

count: int | None= None
How many energy units does it correspond to.

energyIndex: int | None= None
Index within the energy card.

inPlayArea: AreaType | None= None
Area where the card is in play.

inPlayIndex: int | None= None
Index within the play area.

index: int | None= None
Index within the area.

number: int | None= None
Selected number

playerIndex: int | None= None
The owning player of the card.

serial: int | None= None
Serial number of the card.

specialConditionType: SpecialConditionType | None= None
Type of the special condition.

toolIndex: int | None= None
Index within the tool.

type: OptionType
Use this parameter to determine which option it is.

classapi.SelectData(type, context, minCount, maxCount, remainDamageCounter, remainEnergyCost, option, deck, contextCard, effect)
Data for the selection process, including type, context, and available options.

context: SelectContext
What is being selected?

contextCard: Card | None
Which card is the selection concerning? This is sent when the context is “Activate”; otherwise, it is null.

deck: list[Card] | None
An array of cards; None unless selecting cards from the deck.

effect: Card | None
The card that is activating the effect currently being processed.

maxCount: int
Maximum number of selections.

minCount: int
Minimum number of selections. It can also be 0.

option: list[Option]
Array of options.

remainDamageCounter: int
Remaining number of damage counters that can be placed.

remainEnergyCost: int
Used when the type is Energy. The remaining required energy count.

type: SelectType
Selection type.

classapi.Log(type, playerIndex=None, hasBasicPokemon=None, cardId=None, serial=None, fromArea=None, toArea=None, cardIdActive=None, serialActive=None, cardIdBench=None, serialBench=None, cardIdBefore=None, serialBefore=None, cardIdAfter=None, serialAfter=None, cardIdTarget=None, serialTarget=None, attackId=None, value=None, putDamageCounter=None, isRecover=None, head=None, result=None, reason=None)
A single log entry representing an event that occurred during the match.

type: LogType
Use this parameter to determine which log it is.

classapi.Observation(select, logs, current, search_begin_input=None)
Current state and available choices presented to the agent.

current: State | None
Current state. At the time of the initial deck selection, it will be None.

logs: list[Log]
Events that have occurred since the last selection.

search_begin_input: str | None= None
Input to the search_begin function.

select: SelectData | None
Selection information. At the time of the initial deck selection, it will be None.

classapi.SearchState(observation, searchId)
State of the search process, including the current observation and search ID.

observation: Observation
New observation. search_begin_input is None.

searchId: int
Search state ID.

classapi.ApiResult(state, error)
Result of the API call, including the search state and any error codes.

error: int
Error if not 0.

state: SearchState | None
Search state.

classapi.Skill(name, text)
Represents a skill or ability of a card.

name: str
Skill name.

text: str
Explanation.

classapi.CardData(cardId, name, cardType, retreatCost, hp, weakness, resistance, energyType, basic, stage1, stage2, ex, megaEx, tera, aceSpec, evolvesFrom, skills, attacks)
Detailed information about a card, including its type, attributes, and abilities.

aceSpec: bool
True if ACE SPEC.

attacks: list[int]
IDs of usable attacks.

basic: bool
True if Basic Pokémon.

cardId: int
Card ID.

cardType: CardType
Card type

energyType: EnergyType
Pokémon or Basic Energy type.

evolvesFrom: str | None
If the Pokémon has evolved, then the name of its pre-evolution. Otherwise, None.

ex: bool
True if Pokémon ex (including Mega Evolution Pokémon ex).

hp: int
Pokémon HP.

megaEx: bool
True if Mega Evolution Pokémon ex.

name: str
Card name.

resistance: EnergyType | None
Pokémon resistance.

retreatCost: int
Energy cost required to retreat.

skills: list[Skill]
The skills that the card has.

stage1: bool
True if Stage1 Pokémon.

stage2: bool
True if Stage2 Pokémon.

tera: bool
True if Tera Pokémon.

weakness: EnergyType | None
Pokémon weakness.

classapi.Attack(attackId, name, text, damage, energies)
Detailed information about an attack, including its ID, name, text, damage, and required energies.

attackId: int
Attack ID.

damage: int
Attack damage

energies: list[EnergyType]
Energy required to use.

name: str
Attack name.

text: str
Explanation.

Functions
api.all_card_data()
Retrieve all available card metadata.

Returns
:
A list of all cards defined in the game, including their stats, energy type, evolution state, and more.

Return type
:
list[CardData]

api.all_attack()
Return all attacks.

Return type
:
list[Attack]

api.to_observation_class(obs)
Convert a dictionary to Observation class.

Returns
:
Observation dataclass instance.

Return type
:
Observation

api.search_begin(agent_observation, your_deck, your_prize, opponent_deck, opponent_prize, opponent_hand, opponent_active, manual_coin=False)
Start a search for the next action based on the current game state and agent observation.

Parameters
:
agent_observation (Observation) – You must input the observation argument passed to your agent function exactly as is.

your_deck (list[int]) – Predicted Card ID your Deck. It must have the same number of cards as your deck. If Observation.select.deck != None, ignored this.

your_prize (list[int]) – Predicted Card ID your Prize cards. It must have the same number of cards as your prize.

opponent_deck (list[int]) – Predicted Card ID opponent’s deck. It must have the same number of cards as opponent’s deck. At setup, at least one Basic Pokémon card is required.

opponent_prize (list[int]) – Predicted Card ID opponent’s prize cards. It must have the same number of cards as opponent’s prize.

opponent_hand (list[int]) – Predicted Card ID opponent’s hand. It must have the same number of cards as opponent’s hand.

opponent_active (list[int]) – Predicted Card ID opponent’s Active Pokémon. Only if there is a face-down Pokémon in your opponent’s Active Spot. This ID must be a Pokémon card ID.

manual_coin (bool) – If True, the coin’s heads or tails can be chosen.

Returns
:
Root search state.

Return type
:
SearchState

api.search_step(search_id, select)
Perform a step in the search process by selecting options based on the current state.

Parameters
:
search_id (int) – Search ID.

select (list[int]) – Chosen option index.

Returns
:
State for the next selection.

Return type
:
SearchSate

api.search_end()
Terminate the search. Memory used during the search will be reused in the next search.

Return type
:
None

api.search_release(search_id)
Delete the state with the specified ID and make the memory available for reuse.

Parameters
:
search_id (int) – Search ID.

Return type
:
None
from typing import List, Dict

from pilgram.globals import ContentMeta


WORLD = ContentMeta.get('world.name')
MONEY = ContentMeta.get("money.name")
TOWN = ContentMeta.get("world.city.name")
MAX_TAX = ContentMeta.get("guilds.max_tax")


class Strings:
    """
    class that contains all the interface-related strings that will be sent to the players.
    """

    # character creation
    character_already_created = "You already have a character! Their name is {name} and they are very sad now :("
    character_creation_get_name = "Ok, let's start by naming your character. Send me a name (4 - 20 characters)."
    character_creation_get_description = "Ok now send me your character's description (10 - 300 characters)."
    welcome_to_the_world = f"Your character has been created! Welcome to the world of {WORLD}!"

    # guild creation
    guild_already_created = "You already created a guild! You can't create another guild, you can only modify your current guild or join another."
    guild_creation_get_name = "Ok, let's start by naming your guild. Send me a name (2 - 30 characters)."
    guild_creation_get_description = "Ok now send me your guild's description (10 - 300 characters)."
    guild_creation_success = "Your guild '{name}' has been created!"
    invalid_tax = f"Tax must be lower or equal to {MAX_TAX}%"
    insert_tax = f"Insert the percent you want to tax your member's quest {MONEY} rewards. (max {MAX_TAX}%)"

    # joining guilds
    guild_join_success = "You successfully joined guild '{guild}'!"
    player_joined_your_guild = "Player {player} joined your guild ({guild})!"
    guild_is_full = "The guild is full! Tell the owner to upgrade it or make your own."

    # quests
    check_board = "You check the quest board, you see there are quests available in the following zones:\n\n"
    already_on_a_quest = "You already are on a quest!"
    embark_underleveled = "You can still choose zones for which you are under-leveled, but you will be more likely to fail quests. Make sure to upgrade your gear!"
    embark_underleveled_confirm = "Are you sure you want go to {zone}? You should be at least level {lv} for this zone.\n\nWrite 'y' or 'n' (yes or no)"
    embark_underleveled_cancel = "Good riddance."
    not_on_a_quest = "You are not on a quest!"
    quest_embark = "You have embarked on the quest:\n\n{quest}\n\nGood luck!"
    quest_success = "\n\nYou have completed the quest '*{name}*'!"
    quest_fail = f"\n\nYou have failed to complete the quest '*{{name}}*'. An higher power lets you reappear at {TOWN}, the Ouroboros contract remains unbroken."
    quest_roll = "(You rolled {roll}, Value to beat: {target})"

    # rank
    rank_guilds = "Here are the top guilds:\n\n*guild name | prestige*"
    rank_players = "Here are the top players:\n\n*name | renown*"
    rank_tourney = "Here are the top guilds (only the top 3 will win):\n\n*guild name | score*"

    # guilds
    here_are_your_mates = "You have {num} guild mates:\n\n"
    show_guild_members = "Guild '{name}' has {num} members:\n\n"
    not_in_a_guild = "You are not in a guild!"
    guild_not_owned = "You don't own a guild!"
    no_guild_yet = "You haven't created a guild yet!"
    tax_gain = f"You gained {{amount}} {MONEY} from guild taxes on {{name}} completing a quest."

    # messages
    write_your_message = "Write the message you want to send"
    message_sent = "Your message has been sent."
    no_self_message = "You can't send a message to yourself. Weirdo."

    # upgrade
    you_paid = f"you paid {{paid}} {MONEY}."
    upgrade_object_confirmation = f"Are you sure you want to upgrade your {{obj}}? It will cost you {{price}} {MONEY}"
    not_enough_money = f"You don't have enough {MONEY}. You need {{amount}} more."
    upgrade_successful = "The upgrade to your {obj} was successful, " + you_paid
    upgrade_cancelled = "The upgrade was cancelled."

    # modify
    cannot_modify_on_quest = "You can't modify your character while on a quest."
    obj_attr_modified = f"{{obj}} {{attr}} has been modified correctly. You paid {ContentMeta.get('modify_cost')}"
    obj_modified = f"Your {{obj}} has been modified correctly. You paid {ContentMeta.get('modify_cost')} {MONEY}"

    # kick
    player_not_in_own_guild = "player '{name}' is not in your guild."
    player_kicked_successfully = "player '{name}' has been successfully kicked from guild '{guild}'. Note that guild members may take some time to update."
    you_have_been_kicked = "You have been kicked from guild {guild}."

    # donations
    donation_received = f"{{donor}} just donated you {{amm}} {MONEY}!"
    donation_successful = f"You successfully sent {{amm}} {MONEY} to {{rec}}. They are certainly going to be happy :)"
    invalid_money_amount = "The specified amount must be greater than zero!"

    # retiring
    you_retired = "You retire from adventuring for a year."
    you_came_back = f"You ended your retirement, resuming your adventures in the world of {WORLD}."

    # player meeting
    players_meet_in_town = "While in town you meet {name} and you"
    players_meet_on_a_quest = "You stumble upon {name} and you"
    town_actions: List[str] = ContentMeta.get("meeting events.town")
    quest_actions: List[str] = ContentMeta.get("meeting events.zones")
    xp_gain = "You gain {xp} xp"

    # minigames
    how_much_do_you_bet = f"How much {MONEY} do you want to bet? (min: {{min}}, max: {{max}})"
    money_pot_too_low = f"You didn't bet enough money, the minimum buy in is {{amount}} {MONEY}"
    money_pot_too_high = f"You bet too much {MONEY}, the maximum buy in is {{amount}} {MONEY}"
    money_pot_ok = f"You bet {{amount}} {MONEY}, the game can begin."
    invalid_bet = "Invalid bet, try again."
    start_hands_minigame = "A mysterious stranger approaches you, he asks if you want to play 'Hands'. You say yes."
    start_fate_minigame = "A Pilgrim approaches you, making you understand he wants to play Pilgrim's fate. You accept."
    hands_minigame_bet = "What value are you betting? (3 - 18, 10 & 5 excluded)."
    fate_minigame_lose = f"The Pilgrim walks away with your {MONEY}, not making a sound."
    fate_minigame_win = "The Pilgrim just walks away, not making a sound."
    you_win = "You win."
    you_lose = "You lose."
    minigame_played_too_recently = "You played this minigame too recently, wait {seconds} seconds and try again."

    # explain
    invalid_minigame_name = "Minigame name is not valid."

    # artifacts
    piece_found = "\n\nYou find a piece of a mysterious artifact."
    not_enough_pieces = "You don't have enough artifact pieces, you need {amount} more."
    craft_successful = "You crated the artifact '{name}'. You feel powerful."

    # spells
    spell_name_validation_error = "Invalid spell name."
    not_enough_power = "You don't have enough eldritch power to cast this spell. Wait for your abilities to recharge."
    not_enough_args = "Not enough arguments, this spell requires {num} args."

    # quick time events
    no_qte_active = "You don't have any currently active quick time event!"
    invalid_option = "The chosen option is invalid!"
    qte_failed = "You failed the QTE!"

    # cults
    choose_cult = "Send the number of the cult you want to join."
    cult_does_not_exist = "The specfified cult does not exist, only cults {start} to {end} exist.}"
    list_cults = "Here are all the existing cults:\n\n"
    modifier_names: Dict[str, str] = {
        "general_xp_mult": "General XP",
        "general_money_mult": "General BA",
        "quest_xp_mult": "Quest XP",
        "quest_money_mult": "Quest BA",
        "event_xp_mult": "Event XP",
        "event_money_mult": "Event BA",
        "can_meet_players": "Can meet others",
        "power_bonus": "Base Power",
        "roll_bonus": "Player Roll Bonus",
        "quest_time_multiplier": "Quest Duration",
        "eldritch_resist": "Spell immunity",
        "artifact_drop_bonus": "Artifact Drop Bonus",
        "upgrade_cost_multiplier": "Upgrade Cost",
        "xp_mult_per_player_in_cult": "XP x player in cult",
        "money_mult_per_player_in_cult": "BA x player in cult",
        "randomizer_delay": "Randomize following every {hr} hours",
        "stats_to_randomize": "Affected stats",
        "power_bonus_per_zone_visited": "Eldritch power x zones visited",
        "qte_frequency_bonus": "QTE frequency bonus",
        "minigame_xp_mult": "Minigame XP",
        "minigame_money_mult": "Minigame BA",
        "hp_mult": "HP",
        "hp_bonus": "HP bonus",
        "damage": "Damage x level",
        "resistance": "Resist x level",
    }

    # items
    effect_names: Dict[str, str] = {
        "hp_restored": "HP restored",
        "hp_percent_restored": "HP % restored",
        "revive": "Revives you",
        "buffs": "Damage buffs (2x)"
    }
    satchel_position_out_of_range = "The given satchel position is not valid, you have {num} items in your satchel."

    # tourney
    tourney_ends_in_x_days = "The tourney ends in {x} days"
    tourney_ends_tomorrow = "The tourney ends tomorrow"
    tourney_ends_today = "The tourney ends today"

    # errors
    no_character_yet = "You haven't made a character yet!"
    named_object_not_exist = "{obj} with name {name} does not exist."
    name_object_already_exists = "{obj} with name {name} already exists, give your {obj} a different name (names are case sensitive)"
    __must_not_contain = "must not contain new lines & the following characters: \\_, \\*, \\`, \\[, ], ~"
    player_name_validation_error = "Player names must only be 4 to 20 characters long, must not contain spaces and " + __must_not_contain
    guild_name_validation_error = "Guild names must only be 2 to 30 characters long, must not contain spaces and " + __must_not_contain
    description_validation_error = "Descriptions must only be 10 to 300 characters long and " + __must_not_contain
    obj_number_error = "{obj} must be a positive integer number."
    obj_does_not_exist = "The {obj} does not exist!"
    yes_no_error = "You must send only either 'y' (yes) or 'n' (no)!"
    positive_integer_error = "You must enter a positive integer (>= 0)."
    obj_reached_max_level = "Your {obj} is already at max level."

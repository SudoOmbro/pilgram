
from pilgram.globals import ContentMeta, Slots

WORLD = ContentMeta.get('world.name')
MONEY = ContentMeta.get("money.name")
TOWN = ContentMeta.get("world.city.name")
MAX_TAX = ContentMeta.get("guilds.max_tax")
ASCENSION_COST: int = ContentMeta.get("ascension.cost")


def rewards_string(xp: int, money: int, renown: int, tax: float = 0) -> str:
    renown_str = "" if renown == 0 else f"\n\nYou gain {renown} renown"
    rewards: list[str] = []
    if xp:
        rewards.append(f"{xp} xp")
    if money:
        tax_str = "" if tax == 0 else f" (taxed {int(tax * 100)}% by your guild)"
        rewards.append(f"{money} {MONEY}{tax_str}")
    return f"\n\n_You gain {" & ".join(rewards)}{renown_str}_\n"


class Strings:
    """
    class that contains all the interface-related strings that will be sent to the players.
    """

    # quests
    quest_canceled = "You abandon the quest, you'll be back in town in a few hours"
    explore_text = "You look around for something interesting..."

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
    switched_too_recently = "You switched Guild/Vocation too recently! Wait another {hours} hours."

    # quests
    check_board = "You check the quest board, you see there are quests available in the following zones:\n\n"
    already_on_a_quest = "You already are on a quest!"
    embark_underleveled = "You can still choose zones for which you are under-leveled, but you will be more likely to fail quests. Make sure to upgrade your gear!"
    embark_underleveled_confirm = "Are you sure you want go to {zone}? You should be at least level {lv} for this zone.\n\nWrite 'y' or 'n' (yes or no)"
    embark_underleveled_cancel = "Good riddance."
    not_on_a_quest = "You are not on a quest."
    quest_embark = "You have embarked on the quest:\n\n{quest}\n\nGood luck!"
    quest_success = "\n\nYou have completed the quest '*{name}*'!"
    reappear = f"An higher power lets you reappear at {TOWN}, the Ouroboros contract remains unbroken."
    quest_fail = "\n\nYou have failed to complete the quest '*{name}*'. " + reappear
    lose_money = f"\n\nYou lose {{money}} {MONEY}"
    quest_roll = "(You rolled {roll}, Value to beat: {target})"
    quest_abandoned = "You are back in town after abandoning the quest."

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
    bank_not_enough_money = "Your guild's bank doesn't have enough money"
    withdrawal_successful = f"You successfully withdrew {{amm}} {MONEY} from the bank."
    no_logs = "Your guild has no transactions recorded"

    # messages
    write_your_message = "Write the message you want to send"
    message_sent = "Your message has been sent."
    no_self_message = "You can't send a message to yourself. Weirdo."
    no_self_gift = "You can't send a gift to yourself. Weirdo."

    # upgrade
    you_paid = f"you paid {{paid}} {MONEY}."
    upgrade_object_confirmation = f"Are you sure you want to upgrade your {{obj}}? It will cost you {{price}} {MONEY}"
    not_enough_money = f"You don't have enough {MONEY}. You need {{amount}} more."
    upgrade_successful = "The upgrade to your {obj} was successful, " + you_paid
    upgrade_cancelled = "The upgrade was cancelled."

    # modify
    cannot_modify_on_quest = "You can't modify your character while on a quest."
    cannot_change_vocation_on_quest = "You can't change your vocation while on a quest."
    obj_attr_modified = f"{{obj}} {{attr}} has been modified correctly. You paid {ContentMeta.get('modify_cost')}"
    obj_modified = f"Your {{obj}} has been modified correctly. You paid {ContentMeta.get('modify_cost')} {MONEY}"

    # kick
    player_not_in_own_guild = "player '{name}' is not in your guild."
    player_kicked_successfully = "player '{name}' has been successfully kicked from guild '{guild}'. Note that guild members may take some time to update."
    cant_kick_yourself = "You can't kick yourself!"
    you_have_been_kicked = "You have been kicked from guild {guild}."

    # delete guild
    are_you_sure_action = "Are you sure you want to {action}? (y/n)"
    guild_deleted = "Your guild has been successfully deleted."

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
    town_actions: list[str] = ContentMeta.get("meeting events.town")
    quest_actions: list[str] = ContentMeta.get("meeting events.zones")
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
    trap_minigame_lose = "You got hit by an arrow! You manage to escape with just a bruise, but no treasure."
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
    ascension_too_low = "Your ascension level is too low for this spell."

    # quick time events
    no_qte_active = "You don't have any currently active quick time event!"
    invalid_option = "The chosen option is invalid!"
    qte_failed = "You failed the QTE!"

    # vocations
    modifier_names: dict[str, str] = {
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
        "power_bonus_per_zone_visited": "Eldritch power x zones visited",
        "qte_frequency_bonus": "QTE frequency bonus",
        "minigame_xp_mult": "Minigame XP",
        "minigame_money_mult": "Minigame BA",
        "hp_mult": "HP",
        "hp_bonus": "HP bonus",
        "damage": "Damage x level",
        "resist": "Resist x level",
        "discovery_bonus": "Item discovery bonus",
        "lick_wounds": "Animal instincts",
        "passive_regeneration": "Passive HP regeneration",
        "combat_rewards_multiplier": "Combat rewards",
        "quest_fail_rewards_multiplier": "Quest failure rewards",
        "gain_money_on_player_meet": "Gain money on meet",
        "can_buy_on_a_quest": "Can buy on a quest",
        "can_craft_on_a_quest": "Can craft on a quest",
        "revive_chance": "Revive Chance",
        "reroll_cost_multiplier": "Reroll cost",
        "xp_on_reroll": "Reroll XP (x Item lv.)",
        "reroll_stats_bonus": "Reroll stats bonus",
        "perk_rarity_bonus": "Reroll perk bonus",
        "hunt_sanity_loss": "Hunt sanity loss",
        "combat_frequency": "Combat frequency",
        "money_loss_on_death": "BA loss on death"
    }

    # items
    enchant_symbol = "⭐"
    effect_names: dict[str, str] = {
        "hp_restored": "HP restored",
        "hp_percent_restored": "HP % restored",
        "revive": "Revives you",
        "buffs": "Damage buffs (2x)",
        "sanity_restored": "Sanity restored",
        "bait_power": "Bait power"
    }
    satchel_position_out_of_range = "The given satchel position is not valid, you have {num} items in your satchel."
    used_item = "{verb} the {item}"
    rarities = (
        "Common",
        "Odd",
        "Strange",
        "Eldritch"
    )
    weapon_modifiers: dict[str, tuple[str, ...]] = {
        "slash": ("Sharp", "-Slashing", "Barbed", "Keen", "Edged", "Serrated", "Slicing", "-Chopping"),
        "pierce": ("Piercing", "-Thrusting", "Pointed", "Tipped", "-the Phalanx"),
        "blunt": ("Heavy", "-Crushing", "Devastating", "Denting", "Big", "Bonking"),
        "occult": ("Occult", "Eldritch", "Hexed", "Runic", "-the Old Ones", "Heretical", "Unholy"),
        "fire": ("Flaming", "-Flame", "Draconic", "-Fire", "Blazing", "-Wildfire", "Flaring", "Hot"),
        "acid": ("-Acid", "Melting", "Corroding", "Oozing", "-Rot", "Rotten", "Caustic"),
        "freeze": ("-Ice", "Freezing", "Chilling", "-Frostbite", "Hailing", "-the Glacier", "Cold"),
        "electric": ("Electric", "Lightning", "-Thunder", "-the Abyssal Eel", "Voltaic", "Crackling")
    }
    armor_modifiers: dict[str, tuple[str, ...]] = {
        "slash": ("Plated", "-the Bulwark", "Meshed", "Rounded", "Smooth"),
        "pierce": ("Reinforced", "-the Cataphract", "Shielding", "Thick", "Hardened"),
        "blunt": ("Heavy", "Stable", "Well-built", "Sturdy", "-the Bulwark"),
        "occult": ("Occult", "Eldritch", "Warded", "Runic", "-the Inquisitor"),
        "fire": ("Flame retardant", "-the Drake slayer", "Fireproof", "Heat-resistant", "Cool", "Asbestos"),
        "acid": ("-the Blackmarsh", "Unmelting", "Corrosion-resistant", "Basic"),
        "freeze": ("Insulated", "Warm", "-the Crags", "Fur-lined", "Cozy"),
        "electric": ("-Thunder", "Grounded", "Rubber-lined", "-Faraday", "Resistive")
    }
    slots: list[str] = [
        "Head",
        "Chest",
        "Legs",
        "Arms",
        "Primary",
        "Secondary",
        "Relic"
    ]
    no_items_yet = "You don't have any items yet"
    invalid_item = "Invalid item."
    item_sell_confirm = f"Are you sure you want to sell {{item}}? (y/n)"
    sell_all_confirm = "Are you sure you want to sell all your items? (y/n)"
    item_sold = f"You sold '*{{item}}*' for *{{money}} {MONEY}*."
    item_bought = f"You bought '*{{item}}*' for *{{money}} {MONEY}*."
    item_equipped = "You equipped '{item}' in the {slot} slot."
    unequip_all = "Unequipped all items."
    cannot_sell_equipped_item = "You can't sell an equipped item!"
    cannot_gift_equipped_item = "You can't gift an equipped item!"
    cannot_shop_on_a_quest = "You cannot shop while on a quest!"
    item_reroll_confirm = f"Are you sure you want to reroll {{item}}? It will cost you {{price}} {MONEY}. (y/n)"
    item_rerolled = f"You paid {{amount}} {MONEY} to reroll {{old_name}} into:"
    item_enchant_confirm = "Are you sure you want to enchant {item}? It will cost you an artifact piece. (y/n)"
    item_enchanted = "You used 1 artifact piece to enchant:"
    no_ap_to_enchant = "You don't have any artifact pieces to enchant with."
    max_enchants_reached = "You have reached the maximum amount of perks on this item."
    action_canceled = "{action} canceled."
    enchant_ascension_required = "You must be at least ascension level 1 to enchant items."
    item_temper_confirm = f"Are you sure you want to temper {{item}}? It will cost you {{price}} {MONEY}. (y/n)"
    item_tempered = f"You paid {{amount}} {MONEY} to temper {{item}}, increasing it's level by one."

    # pets
    no_pets_yet = "You don't have any pets yet"
    invalid_pet = "Invalid pet."
    pet_equipped = "You took {name} ({race}) with you."
    max_pets_reached = "You have reached the maximum amount of pets."
    already_catching = "You are already trying to catch a pet."
    cannot_sell_equipped_pet = "You can't sell your currently selected pet!"
    pet_catch_start = "You lay some bait, hopefully you'll catch a monster..."
    pet_caught = "You successfully caught a {name}\n\nUse the `rename` command to give it a new name."
    pet_escaped = "You couldn't catch the {name}, it escaped."
    pet_start_rename = "Write a new name for {name}"
    pet_renamed = "Successfully renamed {oldname} into {newname}\n\nyou paid {amount}."

    # auctions
    no_auctions_yet = "No auctions yet"
    auction_created = "Auction for item {item} created successfully."
    bid_placed = f"You placed a bid of {{amount}} {MONEY} on item {{item}}."
    auction_already_exists = "Auction for item {item} exists."
    cannot_equip_auctioned_item = "You cannot equip an auctioned item."
    cannot_equip_higher_level_item = "You cannot equip an item that is higher level than you."
    cannot_sell_auctioned_item = "You cannot sell an auctioned item."
    cannot_enchant_auctioned_item = "You cannot enchant an auctioned item."
    bid_too_low = "You bid is too low! the minimum is "
    auction_is_expired = "You can't bid anymore, the auction is expired."
    cant_bid_on_own_auction = "You cannot bid on your own auction."

    # tourney
    tourney_ends_in_x_days = "The tourney ends in {x} days"
    tourney_ends_tomorrow = "The tourney ends tomorrow"
    tourney_ends_today = "The tourney ends today"

    # bestiary
    bestiary_string = "Here's what you can find in {zone}:"
    no_enemies_yet = "Nothing is known about {zone} yet..."
    no_monsters_in_town = f"There ar eno monsters in {TOWN}."

    # combat
    invalid_stance = "Invalid stance, here are the available stances (you can write just the first letter):\n"
    stances = {
        "b": ("Balanced", "A good balance between aggression & defence."),
        "r": ("Reckless", "All-in on attacks & heavy attacks."),
        "s": ("Safe", "Be defensive, try to keep your hp high"),
        "a": ("Automaton", "Just attack. Nothing else.")
    }
    stance_switch = "Stance switched to "
    force_combat = "You hunt for something strong to kill..."
    sanity_too_low = "Your sanity is too low to hunt now..."
    shade_win = "The shade crumbles and dissolves into nothingness."
    shade_loss = "The shade absorbs you into it's mass."
    post_combat_revive = "\n\nBy the grace of the God Emperor you are revived & continue your quest."
    insanity_meet_yourself = "Your mind goes blank, overwhelmed by insanity. You find yourself face to face with a distorted version of you."

    # duels
    no_self_duel = "You can't duel yourself. Weirdo."
    duel_invite_sent = "You have successfully sent a duel invite to {name}."
    you_must_be_in_town = "You must be in town to duel!"
    opponent_must_be_in_town = "Your opponent must be in town to duel!"
    not_invited_to_duel = "You were not invited to duel by {name}"
    duel_invite_reject_notification = "{name} rejected your duel invite."
    duel_invite_reject = "You rejected {name}'s duel invite."

    # artifacts
    max_number_of_artifacts_reached = "You reached the maximum amount of artifacts you can have ({num}). Upgrade your home to hold more."

    # crypt
    crypt_quest_name = "Crypt Exploration"
    no_crypt_while_questing = "You can't explore the crypt while you are on a quest!"
    already_in_crypt = "You are already exploring the crypt!"
    entered_crypt = f"You enter the crpyt below {TOWN}..."
    exit_crypt = f"You emerge from the crpyt below {TOWN}..."
    no_quest_while_in_crypt = "You can't embark on a quest while in the crypt!"
    in_crypt = "You are currently exploring the Crypt..."

    # raids
    raid_guild_required = "You have to own a guild to start a raid!"
    raid_on_quest = "You can't start a raid while on a quest!"
    raid_not_enough_players = "A minimum of 3 players are required to start a raid!"
    raid_cancel = "Raid canceled."
    raid_description = "Raiding with your guild in {zone}."
    raid_started = "Raid in {zone} started. Godspeed."
    raid_win = "You manage to vanquish the group of enemies."
    raid_success = "You completed the raid successfully."
    raid_leader_died = "The leader of the raid died. Hope abandons you & you decide to go back to town."
    raid_finished = "You manage to dispatch the group of enemies & their legendary leader. The raid is finished."
    cannot_cancel_raid = "You can't cancel a Raid!"
    too_many_raids = "Your guild was on a raid too recently, wait {days} more days."

    no_deathwish_toggle_on_quest = "You cannot toggle Deathwish mode while on a quest."
    deathwish_enabled = "You enabled Deathwish mode!\n\nYou will earn double XP, double BA & double essences but if you die you will lose all of your levels, your BA and your essences (you won't lose your items).\n\nThe enemies you encounter will also be twice as strong."
    deathwish_disabled = "Deathwish mode disabled. you aren't into gambling, are you?"

    sanity_lines: dict[int, tuple[str, ...]] = {
        0: (
            "You see shadows move at the edge of your vision...",
            "You hear voices whisper unintelligibly...",
            "The smell of blood makes your mind go blank...",
            "The voices aren't always there, but they're better than the silence.",
            "The trees are watching you, they are! They watch, they watch, they watch from a far!"
        ),
        -125: (
            "There's a jester in your ear telling you to cause funny times.",
            "And you dance, dance. And you say you'll never die.",
            "You struggle to remember your name."
            "You know, I once dug a pit and filled it with clouds....or was it clowns.... it doesn't matter, it didn't slow him down. But it really began to smell! Must have been clowns. Clouds don't smell, they taste of butter. And tears.",
            "Your teeth itch.",
            "My eyes... I cannot see my eyes!",
            "Roses are red\nViolets are blue\nI’m a schizophrenic\nAnd so am I."
        ),
        -250: (
            "DO YOU THINK YOU ARE IN CONTROL?",
            "MAGNIFICENT SLAUGHTER",
            "AHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHAH",
            "I AM THE GREAT TOMATO MAN, RED RIPENED WITH ANGER!!!",
            "DO YOU SEE THEM TOO?"
        )
    }

    # ascension

    ascension_level_too_low = "You are too low level to ascend!"
    ascension_not_enough_artifacts = f"You don't have enough artifact pieces! ({ASCENSION_COST} needed)"
    ascension_confirm = f"Are you sure you want to spend {ASCENSION_COST} artifact pieces to ascend? This will reset your level, gear level, {MONEY} & destroy all your items (except for relics)."
    ascension_on_quest = "You can't ascend while you are on a quest!"
    ascension_success = "You consume all the essence you collected and your body morphs into a new inhuman form.\n\nYou are born anew.\n(reached ascension level {level})"

    # errors
    no_character_yet = "You haven't made a character yet!"
    named_object_not_exist = "{obj} with name {name} does not exist."
    name_object_already_exists = "{obj} with name {name} already exists, give your {obj} a different name (names are case sensitive)"
    __must_not_contain = "must not contain new lines & the following characters: \\_, \\*, \\`, \\[, ], ~"
    player_name_validation_error = "Player/pet names must only be 4 to 20 characters long, must not contain spaces and " + __must_not_contain
    guild_name_validation_error = "Guild names must only be 2 to 30 characters long, must not contain spaces and " + __must_not_contain
    description_validation_error = "Descriptions must only be 10 to 300 characters long and " + __must_not_contain
    obj_number_error = "{obj} must be a positive integer number."
    obj_does_not_exist = "The {obj} does not exist!"
    yes_no_error = "You must send only either 'y' (yes) or 'n' (no)!"
    positive_integer_error = "You must enter a positive integer (>= 0)."
    obj_reached_max_level = "Your {obj} is already at max level."
    invalid_page = "The specified manual page does not exist. Only pages 1 to {pl} exist."
    less_than_3_quests = "You tried less than 3 quests, you can't modify your character yet."
    multiple_matches_found = "Multiple {obj}s found for your input, use correct casing."
    already_hunting = "You are already hunting!"
    already_exploring = "You are already exploring!"

    @classmethod
    def get_item_icon(cls, item_slot: int) -> str:
        return {
            Slots.PRIMARY: "🗡️",
            Slots.SECONDARY: "🛡️",
            Slots.HEAD: "🪖",
            Slots.CHEST: "🧥",
            Slots.ARMS: "🧤",
            Slots.LEGS: "👖",
            Slots.RELIC: "💎"
        }.get(item_slot, "❓")

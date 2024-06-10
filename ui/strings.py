from pilgram.globals import ContentMeta


MONEY = ContentMeta.get("money.name")


class Strings:
    """
    class that contains all the interface-related strings that will be sent to the players.
    """

    # character creation
    character_already_created = "You already have a character! Their name is {name} and they are very sad now :("
    character_creation_get_name = "Ok, let's start by naming your character. Send me a name (4 - 20 characters)"
    character_creation_get_description = "Ok now send me your character's description (10 - 250 characters)"
    welcome_to_the_world = f"Your character has been created! Welcome to the world of {ContentMeta.get('world.name')}!"

    # guild creation
    guild_already_created = "You already created a guild! You can't create another guild, you can only modify your current guild or join another."
    guild_creation_get_name = "Ok, let's start by naming your guild. Send me a name (2 - 30 characters)"
    guild_creation_get_description = "Ok now send me your guild's description (10 - 250 characters)"
    guild_creation_success = "Your guild '{name}' has been created!"

    # joining guilds
    guild_join_success = "You successfully joined guild '{guild}'!"
    player_joined_your_guild = "Player {player} joined your guild ({guild})"
    guild_is_full = "The guild is full! Tell the owner to upgrade it or make your own."

    # quests
    check_board = "You check the quest board, you see there are quests available in the following zones:"
    already_on_a_quest = "You already are on a quest!"
    quest_embark = "You have embarked on the quest:\n\n*{name}*:\n{descr}\n\nGood luck!"
    quest_success = "You have completed the quest '*{name}*'!"
    quest_fail = "You have failed to complete the quest '*{name}*', you return to town sad, empty handed and a bit bruised."

    # upgrade
    upgrade_object_confirmation = "Are you sure you want to upgrade your {obj}? It will cost you {price}"
    not_enough_money = f"You don't have enough {MONEY}."
    upgrade_successful = f"The upgrade to your {{obj}} was successful, you paid {{paid}} {MONEY}."
    upgrade_cancelled = "The upgrade was cancelled."
    guild_already_maxed = "Your guild is already at the maximum level"

    # modify
    obj_attr_modified = f"{{obj}} {{attr}} has been modified correctly. You paid {ContentMeta.get('modify_cost')}"

    # kick
    player_not_in_own_guild = "player '{name}' is not in your guild"
    player_kicked_successfully = "player '{name} has been successfully kicked from guild {guild}'"
    you_have_been_kicked = "You have been kicked from guild {guild}."

    # donations
    donation_received = f"{{donor}} just donated you {{amm}} {MONEY}!"
    donation_successful = f"You successfully sent {{amm}} {MONEY} to {{rec}}. They are certainly going to be happy :)"
    invalid_money_amount = "The specified amount must be greater than zero!"

    # errors
    no_character_yet = "You haven't made a character yet!"
    no_guild_yet = "You haven't created a guild yet!"
    named_object_not_exist = "{obj} with name {name} does not exist"
    __must_only_contain = "must contain only letters, numbers and the following symbols: -,.!?;:()/+=\"'@#$%^&"
    player_name_validation_error = "Player names must only be 4 to 20 characters long and " + __must_only_contain
    guild_name_validation_error = "Player names must only be 2 to 30 characters long and " + __must_only_contain
    description_validation_error = "Player names must only be 10 to 250 characters long and " + __must_only_contain
    zone_id_error = "Zone number must be a positive integer number"
    zone_does_not_exist = "The zone does not exist!"
    not_in_a_guild = "You are not in a guild!"
    guild_not_owned = "You don't own a guild!"
    yes_no_error = "You must send only either 'yes' or 'no'!"

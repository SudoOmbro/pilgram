from pilgram.globals import ContentMeta


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

    # quests
    check_board = "You check the board, you see there are quests available in the following zones:"
    already_on_a_quest = "You already are on a quest!"
    quest_embark = "You have embarked on the quest:\n\n*{name}*:\n{descr}\n\nGood luck!"

    # errors
    no_character_yet = "You haven't made a character yet!"
    named_object_not_exist = "A {obj} with name {name} does not exist"
    player_name_validation_error = "Player names must only be 4 to 20 characters long and contain only letters, dashes & underscores."
    guild_name_validation_error = "Player names must only be 2 to 30 characters long and contain only letters, dashes & underscores."
    description_validation_error = "Player names must only be 10 to 250 characters long and contain only letters, dashes & underscores."
    zone_id_error = "Zone number must be a positive integer number"
    zone_does_not_exist = "The zone does not exist!"
    not_in_a_guild = "You are not a guild!"

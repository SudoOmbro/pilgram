import logging
from datetime import datetime, timedelta

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    DeferredForeignKey,
    FixedCharField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
)

DB_FILENAME: str = "pilgram_v14.db"  # yes, I'm encoding the DB version in the filename, problem? :)

db = SqliteDatabase(DB_FILENAME)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class BaseModel(Model):
    class Meta:
        database = db


class ZoneModel(BaseModel):
    """ Table that contains all info about Zones """
    id = AutoField(primary_key=True, unique=True)
    name = CharField()
    level = IntegerField()
    description = CharField()
    damage_json = CharField(null=False, default="{}")
    resist_json = CharField(null=False, default="{}")
    extra_data_json = CharField(null=False, default="{}")


class QuestModel(BaseModel):
    """ Table that contains all info about quests """
    id = AutoField(primary_key=True, unique=True)
    zone = ForeignKeyField(ZoneModel, backref="quests")
    number = IntegerField(default=0)  # the number of the quest in the quest order
    name = CharField(null=False)
    description = CharField(null=False)
    success_text = CharField(null=False)
    failure_text = CharField(null=False)

    def __int__(self):
        return int(self.id)


class PlayerModel(BaseModel):
    """ Table that holds all the characters main stats """
    id = IntegerField(primary_key=True, unique=True)
    name = CharField(null=False, unique=True, index=True, max_length=40)
    description = CharField(null=False, max_length=320)
    guild = DeferredForeignKey('GuildModel', backref="members", null=True, default=None)
    money = IntegerField(default=10)
    level = IntegerField(default=1)
    xp = IntegerField(default=0)
    gear_level = IntegerField(default=0)
    progress = CharField(null=True, default=None)  # progress is stored as a char string.
    home_level = IntegerField(default=0)
    last_spell_cast = DateTimeField(default=datetime.now)
    artifact_pieces = IntegerField(default=0)
    flags = IntegerField(default=0)
    renown = IntegerField(default=0)
    vocations = IntegerField(default=0)  # this stores the vocations, considering we use 1 byte per vocation we can have a maximum of 4 vocations per player
    hp_percent = FloatField(null=False, default=1.0)
    satchel = CharField(null=False, default="")  # consumable items are stored as a char string (a byte per item)
    equipped_items = CharField(null=False, default="")  # equipped items are stored as char string, 4 + 1 bytes per item (only store the id of the item & where the item is equipped)
    stance = FixedCharField(max_length=1, default="b")  # stance saved as a char
    completed_quests = IntegerField(default=0)
    last_guild_switch = DateTimeField(default=datetime.now() - timedelta(days=1))
    vocation_progress = CharField(null=False, default="")  # vocation progress is stored as a byte for profession id & a byte for progress
    sanity = IntegerField(default=100)
    ascension = IntegerField(default=0)
    vitality = IntegerField(default=1)
    strength = IntegerField(default=1)
    skill = IntegerField(default=1)
    toughness = IntegerField(default=1)
    attunement = IntegerField(default=1)
    mind = IntegerField(default=1)
    agility = IntegerField(default=1)
    essences = CharField(null=False, default="")  # essences are stored as a char string, 1 + 2 bytes per essence
    max_level_reached = IntegerField(default=0)
    max_money_reached = IntegerField(default=0)
    max_renown_reached = IntegerField(default=0)
    pet = DeferredForeignKey("PetModel", null=True, default=None)


class GuildModel(BaseModel):
    """ Table that holds all the main information about the guilds """
    id = AutoField(primary_key=True)
    name = CharField(null=False, unique=True, index=True, max_length=40)
    level = IntegerField(default=1)
    description = CharField(null=False, max_length=320)
    founder = ForeignKeyField(PlayerModel, backref='owned_guild')
    creation_date = DateTimeField(default=datetime.now)
    prestige = IntegerField(default=0)
    tourney_score = IntegerField(default=0)
    tax = IntegerField(default=5)
    bank = IntegerField(default=0)
    last_raid = DateTimeField(default=datetime.now)


class ZoneEventModel(BaseModel):
    """ Table that contains all the AI generated (or Admin written) Zone events """
    id = AutoField(primary_key=True)
    zone_id = ForeignKeyField(ZoneModel)
    event_text = CharField()


class QuestProgressModel(BaseModel):
    """ Table that tracks the progress of player quests & controls when to send events/finish the quest """
    player = ForeignKeyField(PlayerModel, unique=True, primary_key=True)
    quest = ForeignKeyField(QuestModel, null=True, default=None)
    end_time = DateTimeField(default=datetime.now)
    last_update = DateTimeField(default=datetime.now)

    def is_on_a_quest(self):
        return self.quest_id is not None


class ArtifactModel(BaseModel):
    """ Table that contains all info about artifacts. This table scales with the amount of players """
    id = AutoField(primary_key=True)
    name = CharField(null=False, unique=True)
    description = CharField(null=False)
    owner = ForeignKeyField(PlayerModel, backref="artifacts", index=True, null=True)


class EquipmentModel(BaseModel):
    """
    Table that contains all info about equipments.
    This table scales with the amount of players, it is pretty compressed tho.
    """
    id = AutoField(primary_key=True)
    name = CharField(null=False, max_length=50)
    level = IntegerField(default=1)
    equipment_type = IntegerField(null=False)
    owner = ForeignKeyField(PlayerModel, backref="items", index=True)
    damage_seed = FloatField(null=False)  # used to generate the damage value at load time
    modifiers = CharField(null=False, default="")  # modifiers are stored as a 16bit int for the modifier id + a 32bit int for the strength of the modifier
    rerolls = IntegerField(default=0)


class EnemyTypeModel(BaseModel):
    """ Table that contains all flavour information about enemies. """
    id = AutoField(primary_key=True)
    zone = ForeignKeyField(ZoneModel, backref="enemies", index=True, null=False)
    name = CharField(null=False, unique=True)
    description = CharField(null=False)
    win_text = CharField(null=False)
    lose_text = CharField(null=False)


class AuctionModel(BaseModel):
    """ Table that contains all auctions. """
    id = AutoField(primary_key=True)
    auctioneer = ForeignKeyField(PlayerModel, backref="auctions", index=True, null=False)
    item = ForeignKeyField(EquipmentModel, null=False)
    best_bidder = ForeignKeyField(PlayerModel, index=True, null=True, default=None)
    best_bid = IntegerField(null=False, default=0)
    creation_date = DateTimeField(default=datetime.now)


class PetModel(BaseModel):
    """ Table that contains all the pets, which can be multiple per player """
    id = AutoField(primary_key=True)
    name = CharField(null=True, unique=False, default=None)
    enemy_type = ForeignKeyField(EnemyTypeModel, null=False)
    owner = ForeignKeyField(PlayerModel, backref="pets", index=True, null=False)
    level = IntegerField(default=1)
    xp = IntegerField(default=0)
    hp_percent = FloatField(null=False, default=1.0)
    stats_seed = FloatField(null=False)
    modifiers = CharField(null=False, default="")  # modifiers are stored as a 16bit int for the modifier id + a 32bit int for the strength of the modifier


def db_connect():
    log.info("Connecting to database")
    db.connect(reuse_if_open=True)


def db_disconnect():
    log.info("Disconnecting from database")
    db.close()


def create_tables():
    log.info("creating all tables")
    db_connect()
    db.create_tables([
        ZoneModel,
        QuestModel,
        PlayerModel,
        GuildModel,
        ZoneEventModel,
        QuestProgressModel,
        ArtifactModel,
        EquipmentModel,
        EnemyTypeModel,
        AuctionModel
    ], safe=True)
    log.info("All tables created")
    db_disconnect()

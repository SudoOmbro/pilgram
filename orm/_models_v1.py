import logging
from datetime import datetime

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    DeferredForeignKey,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
)

DB_FILENAME: str = "pilgram_v1.db"  # yes, I'm encoding the DB version in the filename, problem? :)

db = SqliteDatabase(DB_FILENAME)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class BaseModel(Model):
    class Meta:
        database = db


class ZoneModel(BaseModel):
    id = AutoField(primary_key=True, unique=True)
    name = CharField()
    level = IntegerField()
    description = CharField()


class QuestModel(BaseModel):
    id = AutoField(primary_key=True, unique=True)
    zone_id = ForeignKeyField(ZoneModel, backref="quests")
    number = IntegerField(default=0)  # the number of the quest in the quest order
    name = CharField(null=False)
    description = CharField(null=False)
    success_text = CharField(null=False)
    failure_text = CharField(null=False)


class PlayerModel(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    name = CharField(null=False, unique=True, index=True)
    description = CharField(null=False)
    guild = DeferredForeignKey('GuildModel', backref="members", null=True, default=None)
    money = IntegerField(default=10)
    level = IntegerField(default=1)
    xp = IntegerField(default=0)
    gear_level = IntegerField(default=0)
    progress = CharField(null=True, default=None)  # progress is stored as a char string in the player table.
    home_level = IntegerField(default=0)
    last_spell_cast = DateTimeField(default=datetime.now)
    artifact_pieces = IntegerField(default=0)
    flags = IntegerField(default=0)


class GuildModel(BaseModel):
    id = AutoField(primary_key=True)
    name = CharField(null=False, unique=True, index=True)
    level = IntegerField(default=1)
    description = CharField(null=False)
    founder = ForeignKeyField(PlayerModel, backref='owned_guild')
    creation_date = DateTimeField(default=datetime.now)
    prestige = IntegerField(default=0)


class ZoneEventModel(BaseModel):
    id = AutoField(primary_key=True)
    zone_id = ForeignKeyField(ZoneModel)
    event_text = CharField()


class QuestProgressModel(BaseModel):
    """ Table that tracks the progress of player quests & controls when to send events/finish the quest """
    player_id = ForeignKeyField(PlayerModel, unique=True, primary_key=True)
    quest_id = ForeignKeyField(QuestModel, null=True, default=None)
    end_time = DateTimeField(default=datetime.now)
    last_update = DateTimeField(default=datetime.now)


class ArtifactModel(BaseModel):
    id = AutoField(primary_key=True)
    name = CharField(null=False, unique=True)
    description = CharField(null=False)
    owner = ForeignKeyField(PlayerModel, backref="artifacts", index=True, null=True)


def db_connect():
    log.info("Connecting to database")
    db.connect()


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
        ArtifactModel
    ], safe=True)
    db_disconnect()

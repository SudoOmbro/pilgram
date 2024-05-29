from datetime import datetime
from typing import Dict

from peewee import SqliteDatabase, Model, IntegerField, CharField, ForeignKeyField, CompositeKey, DateTimeField

from pilgram.classes import Player, Progress, Guild
from pilgram.generics import PilgramDatabase

db = SqliteDatabase("pilgram.db")


class BaseModel(Model):
    class Meta:
        database = db


class ZoneModel(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    name = CharField()
    level = IntegerField()
    description = CharField()


class QuestModel(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    zone_id = ForeignKeyField(ZoneModel, backref="quests")
    number = IntegerField(default=0)  # the number of the quest in the quest order
    name = CharField(null=False)
    description = CharField(null=False)
    success_text = CharField(null=False)
    failure_text = CharField(null=False)


class PlayerModel(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    name = CharField(null=False)
    description = CharField(null=False)
    guild_id = ForeignKeyField("Guild", backref="players", null=True, default=None)
    money = IntegerField(default=10)
    level = IntegerField(default=1)
    xp = IntegerField(default=0)
    gear_level = IntegerField(default=0)
    progress = CharField(null=True, default=None)  # progress is stored as a char string in the player table.


class GuildModel(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField(null=False)
    description = CharField(null=False)
    founder_id = ForeignKeyField(PlayerModel, backref='guilds')
    creation_date = DateTimeField(default=datetime.now)


class ZoneEventModel(BaseModel):
    id = IntegerField(primary_key=True)
    zone_id = ForeignKeyField(ZoneModel)
    event_text = CharField()


class QuestProgressModel(BaseModel):
    """ Table that tracks the progress of player quests & controls when to send events/finish the quest """
    player_id = ForeignKeyField(PlayerModel, unique=True)
    quest_id = ForeignKeyField(QuestModel, null=True, default=None)
    start_time = DateTimeField(default=datetime.now)
    end_time = DateTimeField(default=datetime.now)
    last_update = DateTimeField(default=datetime.now)

    class Meta:
        primary_key = False


def create_tables():
    db.connect()
    db.create_tables([ZoneModel, QuestModel, PlayerModel, GuildModel, ZoneEventModel, QuestProgressModel])
    db.close()


def decode_progress(data: str) -> Dict[int, int]:
    if not data:
        return {}
    # TODO


def encode_progress(data: Dict[int, int]) -> str:
    # TODO
    pass


class PilgramORMDatabase(PilgramDatabase):

    def __init__(self):
        super().__init__()

    def get_player_data(self, player_id) -> Player:
        pls = PlayerModel.get(PlayerModel.id == player_id)
        guild = self.get_guild(pls.guild_id)
        progress = Progress(pls.progress, decode_progress)
        return Player(
            pls.player_id,
            pls.name,
            pls.description,
            guild,
            pls.level,
            pls.xp,
            pls.money,
            progress,
            pls.gear_level
        )

    def update_player_data(self, player: Player):
        pls = PlayerModel.get(PlayerModel.id == player.player_id)
        pls.name = player.name,
        pls.description = player.description,
        pls.guild = player.guild,
        pls.level = player.level,
        pls.xp = player.xp,
        pls.money = player.money,
        pls.gear_level = player.gear_level
        pls.progress = encode_progress(player.progress.zone_progress)

    def create_player_data(self, player: Player):
        PlayerModel.create(
            id=player.player_id,
            name=player.name,
            description=player.description
        )

    def get_guild(self, guild_id: int) -> Guild:
        gs = GuildModel.get(GuildModel.id == guild_id)
        founder = self.get_player_data(gs.founder_id)
        return Guild(
            gs.id,
            gs.name,
            gs.description,
            founder,
            gs.creation_date,
        )

from datetime import datetime

from peewee import SqliteDatabase, Model, IntegerField, CharField, ForeignKeyField, CompositeKey, DateTimeField

from pilgram.generics import PilgramDatabase

db = SqliteDatabase("pilgram.db")


class BaseModel(Model):
    class Meta:
        database = db


class Zone(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    name = CharField()
    level = IntegerField()
    description = CharField()


class Quest(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    zone_id = ForeignKeyField(Zone, backref="quests")
    number = IntegerField(default=0)  # the number of the quest in the quest order
    name = CharField(null=False)
    description = CharField(null=False)
    success_text = CharField(null=False)
    failure_text = CharField(null=False)


class Player(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    name = CharField(null=False)
    description = CharField(null=False)
    guild = ForeignKeyField("Guild", backref="players")
    money = IntegerField()
    level = IntegerField()
    xp = IntegerField()
    gear_level = IntegerField()


class Guild(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField(null=False)
    description = CharField(null=False)
    founder = ForeignKeyField(Player, backref='guilds')


class Progress(BaseModel):
    player_id = ForeignKeyField(Player)
    zone_id = ForeignKeyField(Zone)
    progress = IntegerField()  # quantifies player progress in the zone

    class Meta:
        primary_key = CompositeKey('player_id', 'zone_id')
        indexes = (
            (('player_id', 'zone_id'), True)
        )


class ZoneEvent(BaseModel):
    id = IntegerField(primary_key=True)
    zone_id = ForeignKeyField(Zone)
    event_text = CharField()


class QuestProgress(BaseModel):
    """ Table that tracks the progress of player quests & controls when to send events/finish the quest """
    player_id = ForeignKeyField(Player, unique=True)
    quest_id = ForeignKeyField(Quest, null=True, default=None)
    start_time = DateTimeField(default=datetime.now)
    end_time = DateTimeField(default=datetime.now)
    last_update = DateTimeField(default=datetime.now)

    class Meta:
        primary_key = False


def create_tables():
    db.connect()
    db.create_tables([Zone, Quest, Player, Guild, Progress, ZoneEvent, QuestProgress])
    db.close()


class PilgramORMDatabase(PilgramDatabase):

    def __init__(self):
        super().__init__()


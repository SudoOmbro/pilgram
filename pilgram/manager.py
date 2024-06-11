import json
import os
from datetime import timedelta
from typing import List, Dict

from pilgram.classes import Quest, Player, AdventureContainer, Zone
from pilgram.generics import PilgramDatabase, PilgramNotifier, PilgramGenerator
from pilgram.globals import ContentMeta
from ui.strings import Strings


MONEY = ContentMeta.get("money.name")
QUEST_THRESHOLD = 5


def _gain(xp: int, money: int) -> str:
    return f"\n\nYou gain {xp} xp & {money} {MONEY}"


class _HighestQuests:
    """ records highest reached quest by players per zone, useful to the generator to see what it has to generate """
    FILENAME = "questprogressdata.json"

    def __init__(self, data: Dict[int, int]) -> None:
        self.__data = data

    @classmethod
    def load_from_file(cls):
        if os.path.isfile(cls.FILENAME):
            with open(cls.FILENAME, "r") as f:
                return _HighestQuests(json.load(f))
        return {}

    def save(self):
        with open(self.FILENAME, "w") as f:
            json.dump(self.__data, f)

    def update(self, zone_id: int, progress: int):
        if self.__data[zone_id] < progress:
            self.__data[zone_id] = progress
            self.save()

    def is_quest_number_too_low(self, zone: Zone, number_of_quests: int) -> bool:
        return number_of_quests < self.__data[zone.zone_id] + QUEST_THRESHOLD


class QuestManager:
    """ helper class to neatly manage zone events & quests """

    def __init__(self, database: PilgramDatabase, notifier: PilgramNotifier, update_interval: timedelta):
        self.database = database
        self.notifier = notifier
        self.update_interval = update_interval
        self.highest_quests = _HighestQuests.load_from_file()

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def _complete_quest(self, ac: AdventureContainer):
        quest: Quest = ac.quest
        player: Player = ac.player
        if quest.finish_quest(player):
            xp, money = quest.get_rewards(player)
            player.add_xp(xp)
            player.money += money
            self.db().update_player_data(player)
            if player.guild:
                player.guild.prestige += quest.get_prestige()
                self.db().update_guild(player.guild)
            self.notifier.notify(player, Strings.quest_success.format(name=quest.name) + _gain(xp, money))
        else:
            self.notifier.notify(player, Strings.quest_fail.format(name=quest.name))
        self.highest_quests.update(ac.zone().zone_id, ac.quest.number)  # zone() will return a zone and not None since player must be in a quest to reach this part of the code
        ac.quest = None
        self.db().update_quest_progress(ac)

    def _process_event(self, ac: AdventureContainer):
        zone = ac.zone()
        event = self.db().get_random_zone_event(zone)
        xp, money = event.get_rewards(ac.player)
        ac.player.add_xp(xp)
        ac.player.money += money
        self.db().update_player_data(ac.player)
        self.db().update_quest_progress(ac)
        text = f"{event.event_text}\n\n{_gain(xp, money)}"
        self.notifier.notify(ac.player, text)

    def process_update(self, ac: AdventureContainer):
        # TODO add interactions between players in same zone (post launch)
        if ac.is_on_a_quest() and ac.is_quest_finished():
            self._complete_quest(ac)
        else:
            self._process_event(ac)

    def get_updates(self) -> List[AdventureContainer]:
        return self.db().get_all_pending_updates(self.update_interval)


class GeneratorManager:
    """ helper class to manage the quest & zone event generator """

    def __init__(self, database: PilgramDatabase, generator: PilgramGenerator):
        self.database = database
        self.generator = generator

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def __get_all_zones(self) -> List[Zone]:
        return self.db().get_all_zones()

    def __get_zones_to_generate(self) -> List[Zone]:
        result: List[Zone] = []
        zones = self.__get_all_zones()
        hq = _HighestQuests.load_from_file()
        quest_counts = self.db().get_quests_counts()
        for zone, count in zip(zones, quest_counts):
            if hq.is_quest_number_too_low(zone, count):
                result.append(zone)
        return result

    def run(self):
        zones = self.__get_zones_to_generate()
        for zone in zones:
            quests = self.generator.generate_quests(zone)
            for quest in quests:
                self.db().add_quest(quest)
                zone_events = self.generator.generate_zone_events(zone)
                for zone_event in zone_events:
                    self.db().add_zone_event(zone_event)
import json
import logging
import os
from time import sleep
from datetime import timedelta
from typing import List, Dict, Tuple

from pilgram.classes import Quest, Player, AdventureContainer, Zone, TOWN_ZONE
from pilgram.generics import PilgramDatabase, PilgramNotifier, PilgramGenerator
from pilgram.globals import ContentMeta
from ui.strings import Strings


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


MONEY = ContentMeta.get("money.name")
QUEST_THRESHOLD = 3

MAX_QUESTS_FOR_EVENTS = 600  # * 25 = 3000
MAX_QUESTS_FOR_TOWN_EVENTS = MAX_QUESTS_FOR_EVENTS * 2


def _gain(xp: int, money: int) -> str:
    return f"\n\n_You gain {xp} xp & {money} {MONEY}_"


class _HighestQuests:
    """ records highest reached quest by players per zone, useful to the generator to see what it has to generate """
    FILENAME = "questprogressdata.json"

    def __init__(self, data: Dict[str, int]) -> None:
        self.__data: Dict[int, int] = {}
        for k, v in data.items():
            self.__data[int(k)] = v

    @classmethod
    def load_from_file(cls):
        if os.path.isfile(cls.FILENAME):
            with open(cls.FILENAME, "r") as f:
                return _HighestQuests(json.load(f))
        return _HighestQuests({})

    def save(self):
        with open(self.FILENAME, "w") as f:
            json.dump(self.__data, f)

    def update(self, zone_id: int, progress: int):
        if self.__data.get(zone_id - 1, 0) < progress:
            self.__data[zone_id - 1] = progress
            self.save()

    def is_quest_number_too_low(self, zone: Zone, number_of_quests: int) -> bool:
        return number_of_quests < (self.__data.get(zone.zone_id - 1, 0) + QUEST_THRESHOLD)


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
            if player.guild:
                player.guild.prestige += quest.get_prestige()
                self.db().update_guild(player.guild)
            self.notifier.notify(player, quest.success_text + Strings.quest_success.format(name=quest.name) + _gain(xp, money))
        else:
            self.notifier.notify(player, quest.failure_text + Strings.quest_fail.format(name=quest.name))
        self.highest_quests.update(ac.zone().zone_id, ac.quest.number + 1)  # zone() will return a zone and not None since player must be in a quest to reach this part of the code
        ac.quest = None
        self.db().update_quest_progress(ac)
        player.progress.set_zone_progress(quest.zone, quest.number + 1)
        self.db().update_player_data(player)

    def _process_event(self, ac: AdventureContainer):
        zone = ac.zone()
        event = self.db().get_random_zone_event(zone)
        xp, money = event.get_rewards(ac.player)
        ac.player.add_xp(xp)
        ac.player.money += money
        self.db().update_player_data(ac.player)
        self.db().update_quest_progress(ac)
        text = f"*{event.event_text}*{_gain(xp, money)}"
        self.notifier.notify(ac.player, text)

    def process_update(self, ac: AdventureContainer):
        # TODO add interactions between players in same zone (post launch) (maybe)
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

    def __get_zones_to_generate(self) -> Tuple[List[Zone], List[int]]:
        result: List[Zone] = []
        zones = self.db().get_all_zones()
        hq = _HighestQuests.load_from_file()
        quest_counts = self.db().get_quests_counts()
        for zone, count in zip(zones, quest_counts):
            if hq.is_quest_number_too_low(zone, count):
                result.append(zone)
        return result, quest_counts

    def run(self, timeout_between_ai_calls: float):
        zones, quest_numbers = self.__get_zones_to_generate()
        log.info(f"Found {len(zones)} zones to generate quests/events for")
        for zone in zones:
            try:
                log.info(f"generating quests for zone {zone.zone_id}")
                quests = self.generator.generate_quests(zone, quest_numbers)
                self.db().add_quests(quests)
                log.info(f"Quest generation done for zone {zone.zone_id}")
                sleep(timeout_between_ai_calls)
                if quest_numbers[zone.zone_id - 1] < MAX_QUESTS_FOR_EVENTS:
                    log.info(f"generating zone events for zone {zone.zone_id}")
                    # only generate zone events if there are less than MAX_QUESTS_FOR_EVENTS
                    zone_events = self.generator.generate_zone_events(zone)
                    self.db().add_zone_events(zone_events)
                    log.info(f"Zone event generation done for zone {zone.zone_id}")
            except Exception as e:
                log.error(f"Encountered an error while generating for zone {zone.zone_id}: {e}")
            finally:
                sleep(timeout_between_ai_calls)
        if len(zones) > 0:
            # generate town events only if there ia less than 6000 (600 * 2 * 5) of them
            if sum(quest_numbers) > MAX_QUESTS_FOR_TOWN_EVENTS:
                return
            # generate something for the town if you generated something for other zones
            try:
                log.info(f"generating zone events for town")
                town_events = self.generator.generate_zone_events(TOWN_ZONE)
                self.db().add_zone_events(town_events)
                log.info(f"Zone event generation done for town")
            except Exception as e:
                log.error(f"Encountered an error while generating for town zone: {e}")

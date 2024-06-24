import json
import logging
import os
import random
from time import sleep
from datetime import timedelta
from typing import List, Dict, Tuple

from pilgram.classes import Quest, Player, AdventureContainer, Zone, TOWN_ZONE
from pilgram.generics import PilgramDatabase, PilgramNotifier, PilgramGenerator
from pilgram.globals import ContentMeta
from pilgram.strings import Strings


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


MONEY = ContentMeta.get("money.name")
QUEST_THRESHOLD = 3
ARTIFACTS_THRESHOLD = 12

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


def add_to_zones_players_map(zones_player_map: Dict[int, List[Player]], adventure_container: AdventureContainer):
    """ add the player to a map that indicates which zone it is in. Used for meeting other players. """
    zone_id = adventure_container.zone().zone_id if adventure_container.zone() else 0
    if zone_id not in zones_player_map:
        zones_player_map[zone_id] = []
    zones_player_map[zone_id].append(adventure_container.player)


class QuestManager:
    """ helper class to neatly manage zone events & quests """

    def __init__(
            self,
            database: PilgramDatabase,
            notifier: PilgramNotifier,
            update_interval: timedelta,
            updates_per_second: int = 10
    ):
        """
        :param database: database adapter to use to get & set data
        :param notifier: notifier adapter to use to send notifications
        :param update_interval: the amount of time that has to pass since the last update before another update
        :param updates_per_second: the amount of time in seconds between notifications
        """
        self.database = database
        self.notifier = notifier
        self.update_interval = update_interval
        self.highest_quests = _HighestQuests.load_from_file()
        self.updates_per_second = 1 / updates_per_second

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def _complete_quest(self, ac: AdventureContainer):
        quest: Quest = ac.quest
        player: Player = self.db().get_player_data(ac.player.player_id)  # get the most up to date object
        ac.player = player
        if quest.finish_quest(player):
            xp, money = quest.get_rewards(player)
            player.add_xp(xp)
            player.add_money(money)
            if player.guild:
                guild = self.db().get_guild(player.guild.guild_id)  # get the most up to date object
                guild.prestige += quest.get_prestige()
                self.db().update_guild(guild)
                player.guild = guild
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
        player: Player = self.db().get_player_data(ac.player.player_id)  # get the most up to date object
        player.add_xp(xp)
        player.add_money(money)
        ac.player = player
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        text = f"*{event.event_text}*{_gain(xp, money)}"
        self.notifier.notify(ac.player, text)

    def process_update(self, ac: AdventureContainer):
        if ac.is_on_a_quest() and ac.is_quest_finished():
            self._complete_quest(ac)
        else:
            self._process_event(ac)

    def get_updates(self) -> List[AdventureContainer]:
        return self.db().get_all_pending_updates(self.update_interval)

    def handle_players_meeting(self, zones_players_map: Dict[int, List[Player]]):
        """
        handle the meeting of 2 players for each visited zone this update.

        The more time passes between quest manager thread calls, the better this works, because it accumulates more
        players. Too much time however and very few players will never be notified. Gotta find a balance.
        """
        for zone_id in zones_players_map:
            if len(zones_players_map[zone_id]) < 4:  # only let players meet if there's more than 4 players in a zone
                if (len(zones_players_map[zone_id]) > 1) and (random.randint(1, 20) < 15):
                    # if there's less than 4 but more than one, have a very low chance of an encounter
                    continue
            # choose randomly the players that will meet
            players: List[Player] = zones_players_map[zone_id]
            player1: Player = random.choice(players)
            players.remove(player1)
            player2: Player = random.choice(players)
            # get the most up-to-date objects
            player1 = self.db().get_player_data(player1.player_id)
            player2 = self.db().get_player_data(player2.player_id)
            if zone_id == 0:
                string, actions = Strings.players_meet_in_town, Strings.town_actions
            else:
                string, actions = Strings.players_meet_on_a_quest, Strings.quest_actions
            xp = (10 * zone_id * max([player1.level, player2.level])) if zone_id > 0 else 10
            text = f"{string} {random.choice(actions)}\n\n{Strings.xp_gain.format(xp=xp)}"
            player1.add_xp(xp)
            player2.add_xp(xp)
            self.db().update_player_data(player1)
            self.db().update_player_data(player2)
            self.notifier.notify(player1, text.format(name=player2.name))
            self.notifier.notify(player2, text.format(name=player1.name))
            log.info(f"Players {player1.name} & {player2.name} have met")
            sleep(self.updates_per_second * 2)

    def run(self):
        zones_players_map: Dict[int, List[Player]] = {}
        updates = self.get_updates()
        for update in updates:
            add_to_zones_players_map(zones_players_map, update)
            self.process_update(update)
            sleep(self.updates_per_second)
        self.handle_players_meeting(zones_players_map)


class GeneratorManager:
    """ helper class to manage the quest & zone event generator """

    def __init__(self, database: PilgramDatabase, generator: PilgramGenerator):
        """
        :param database: database adapter to use to get & set data
        :param generator: generator adapter to used to generate quests & events
        """
        self.database = database
        self.generator = generator

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def __get_zones_to_generate(self, biases: Dict[int, int]) -> Tuple[List[Zone], List[int]]:
        result: List[Zone] = []
        zones = self.db().get_all_zones()
        hq = _HighestQuests.load_from_file()
        quest_counts = self.db().get_quests_counts()
        for zone, count in zip(zones, quest_counts):
            if hq.is_quest_number_too_low(zone, count - biases.get(zone.zone_id, 0)):
                result.append(zone)
        return result, quest_counts

    def run(self, timeout_between_ai_calls: float, biases: Dict[int, int] = None):
        """
        Run the generator manager process, checking

        :param timeout_between_ai_calls: amount of time in seconds to wait between AI generator calls
        :param biases:
            biases to add to QUEST_THRESHOLD when checking for zones to generate divided by zone. Used to force the
            manager to generate for certain zones if needed.
        :return: None
        """
        if not biases:
            biases = {}
        zones, quest_numbers = self.__get_zones_to_generate(biases)
        log.info(f"Found {len(zones)} zones to generate quests/events for")
        for zone in zones:
            try:
                try:
                    log.info(f"generating quests for zone {zone.zone_id}")
                    quests = self.generator.generate_quests(zone, quest_numbers)
                    self.db().add_quests(quests)
                    log.info(f"Quest generation done for zone {zone.zone_id}")
                except Exception as e:
                    log.error(f"Encountered an error while generating quests for zone {zone.zone_id}: {e}")
                sleep(timeout_between_ai_calls)
                if quest_numbers[zone.zone_id - 1] < MAX_QUESTS_FOR_EVENTS:
                    log.info(f"generating zone events for zone {zone.zone_id}")
                    # only generate zone events if there are less than MAX_QUESTS_FOR_EVENTS
                    zone_events = self.generator.generate_zone_events(zone)
                    self.db().add_zone_events(zone_events)
                    log.info(f"Zone event generation done for zone {zone.zone_id}")
            except Exception as e:
                log.error(f"Encountered an error while generating events for zone {zone.zone_id}: {e}")
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
        # generate artifacts if needed
        available_artifacts = self.db().get_number_of_unclaimed_artifacts()
        if available_artifacts < ARTIFACTS_THRESHOLD:
            log.info(f"generating artifacts")
            artifacts = self.generator.generate_artifacts()
            self.db().add_artifacts(artifacts)
            log.info("artifact generation done")


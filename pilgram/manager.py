import json
import logging
import os
import random
import time
from time import sleep
from datetime import timedelta, datetime
from typing import List, Dict, Tuple

from pilgram.classes import Quest, Player, AdventureContainer, Zone, QuickTimeEvent, QTE_CACHE, TOWN_ZONE, Cult
from pilgram.generics import PilgramDatabase, PilgramNotifier, PilgramGenerator
from pilgram.globals import ContentMeta
from pilgram.strings import Strings
from pilgram.utils import generate_random_eldritch_name, read_json_file, save_json_to_file

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


MONEY = ContentMeta.get("money.name")
QUEST_THRESHOLD = 3
ARTIFACTS_THRESHOLD = 15

MAX_QUESTS_FOR_EVENTS = 600  # * 25 = 3000
MAX_QUESTS_FOR_TOWN_EVENTS = MAX_QUESTS_FOR_EVENTS * 2


def _gain(xp: int, money: int, renown: int, tax: float = 0) -> str:
    tax_str = "" if tax == 0 else f" (taxed {int(tax * 100)}% by your guild)"
    renown_str = "" if renown == 0 else f"You gain {renown} renown"
    return f"\n\n_You gain {xp} xp & {money} {MONEY}{tax_str}\n\n{renown_str}_"


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
        tax: float = 0
        if quest.finish_quest(player):
            xp, money = quest.get_rewards(player)
            renown = quest.get_prestige() * 200
            if player.guild:
                guild = self.db().get_guild(player.guild.guild_id)  # get the most up to date object
                guild.prestige += quest.get_prestige()
                guild.tourney_score += renown
                self.db().update_guild(guild)
                player.guild = guild
                if guild.founder != player:  # check if winnings should be taxed
                    founder = self.db().get_player_data(guild.founder.player_id)  # get most up to date object
                    tax = guild.tax / 100
                    amount = int(money * tax)
                    amount_am = founder.add_money(amount)  # am = after modifiers
                    self.db().update_player_data(founder)
                    self.notifier.notify(founder, Strings.tax_gain.format(amount=amount_am, name=player.name))
                    money -= amount
            player.add_xp(xp)
            money_am = player.add_money(money)  # am = after modifiers
            player.renown += renown
            piece: bool = False
            if random.randint(1, 10) < (3 + player.cult.artifact_drop_bonus):  # 30% base chance to gain a piece of an artifact
                player.artifact_pieces += 1
                piece = True
            self.notifier.notify(
                player,
                quest.success_text + Strings.quest_success.format(name=quest.name) + _gain(xp, money_am, renown, tax=tax) + (Strings.piece_found if piece else "")
            )
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
        player: Player = self.db().get_player_data(ac.player.player_id)  # get the most up to date object
        xp, money = event.get_rewards(ac.player)
        player.add_xp(xp)
        money_am = player.add_money(money)  # am = after modifiers
        ac.player = player
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        text = f"*{event.event_text}*{_gain(xp, money_am, 0)}"
        if random.randint(1, 10) == 1:  # 10% chance of a quick time event
            log.info(f"Player '{player.name}' encountered a QTE.")
            qte = random.choice(QuickTimeEvent.LIST)
            QTE_CACHE[player.player_id] = qte
            text += f"*QTE*\n\n{qte}"
        elif player.player_id in QTE_CACHE:
            del QTE_CACHE[player.player_id]
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
                if len(zones_players_map[zone_id]) < 2:
                    # if there's only one player then skip
                    continue
                if random.randint(1, 20) < 15:
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
            if update.player.cult.can_meet_players:
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
        log.info(f"Available artifacts: {available_artifacts}, threshold: {ARTIFACTS_THRESHOLD}")
        if available_artifacts < ARTIFACTS_THRESHOLD:
            log.info(f"generating artifacts")
            try:
                artifacts = self.generator.generate_artifacts()
                for artifact in artifacts:
                    try:
                        self.db().add_artifact(artifact)
                    except Exception as e:
                        log.error(f"Encountered an error while adding artifact '{artifact.name}': {e}")
                        try:
                            artifact.name += " of " + generate_random_eldritch_name()
                            log.info(f"changed name ({artifact.name}), trying to add the artifact again")
                            self.db().add_artifact(artifact)
                        except Exception as e:
                            log.error(f"adding a random name did not work: {e}")
                log.info("artifact generation done")
            except Exception as e:
                log.error(f"Encountered an error while generating artifacts: {e}")


class TourneyManager:
    DURATION = 1209600  # 2 weeks in seconds

    def __init__(self, notifier: PilgramNotifier, database: PilgramDatabase, notification_delay: int):
        self.notifier = notifier
        self.database = database
        self.notification_delay = notification_delay
        tourney_json = {}
        if os.path.isfile("tourney.json"):
            tourney_json = read_json_file("tourney.json")
        self.tourney_edition = tourney_json.get("edition", 1)
        self.tourney_start = tourney_json.get("start", time.time())
        if not tourney_json:
            self.save()

    def save(self):
        save_json_to_file("tourney.json", {"edition": self.tourney_edition, "start": self.tourney_start})

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def has_tourney_ended(self) -> bool:
        return time.time() >= self.tourney_start + self.DURATION

    def run(self):
        if not self.has_tourney_ended():
            return
        log.info(f"Tourney {self.tourney_edition} has ended")
        top_guilds = self.db().get_top_n_guilds_by_score(3)
        # give artifact piece to 1st guild owner
        first_guild = top_guilds[0]
        winner = self.db().get_player_data(first_guild.founder.player_id)
        winner.artifact_pieces += 1
        self.notifier.notify(winner, f"Your guild won the *biweekly Guild Tourney n.{self.tourney_edition}*!\nyou are awarded an artifact piece!")
        sleep(self.notification_delay)
        # award money to top 3 guilds members
        for guild, reward, position in zip(top_guilds, (10000, 5000, 1000), ("first", "second", "third")):
            log.info(f"guild '{guild.name}' placed {position}")
            members = self.db().get_guild_members_data(guild)
            for player_id, _, _ in members:
                player = self.db().get_player_data(player_id)
                reward_am = player.add_money(reward)  # am = after modifiers
                self.db().update_player_data(player)
                self.notifier.notify(
                    player,
                    f"Your guild placed *{position}* in the *biweekly Guild Tourney n.{self.tourney_edition}*!\nYou are awarded {reward_am} {MONEY}!"
                )
                sleep(self.notification_delay)
        # reset all scores & start a new tourney
        self.db().reset_all_guild_scores()
        self.tourney_start = time.time()
        self.tourney_edition += 1
        log.info(f"New tourney started, edition {self.tourney_edition}, start: {self.tourney_start} (now)")
        self.save()


class TimedUpdatesManager:
    """ helper class to encapsulate all the small updates needed for the game to function """

    def __init__(self, notifier: PilgramNotifier, database: PilgramDatabase):
        self.notifier = notifier
        self.database = database

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def run(self):
        # update members
        Cult.update_number_of_members(self.db().get_cults_members_number())
        # update randomized stats
        for cult in Cult.LIST:
            if cult.can_randomize():
                cult.randomize()

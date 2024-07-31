import json
import logging
import os
import random
import time
from abc import ABC
from datetime import datetime, timedelta
from time import sleep
from typing import Self

from pilgram.classes import (
    QTE_CACHE,
    TOWN_ZONE,
    AdventureContainer,
    Auction,
    Cult,
    Enemy,
    Player,
    Quest,
    QuickTimeEvent,
    Zone,
)
from pilgram.combat_classes import CombatContainer
from pilgram.equipment import Equipment, EquipmentType
from pilgram.flags import BUFF_FLAGS, ForcedCombat
from pilgram.generics import PilgramDatabase, PilgramGenerator, PilgramNotifier
from pilgram.globals import ContentMeta
from pilgram.strings import Strings
from pilgram.utils import generate_random_eldritch_name

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


MONEY = ContentMeta.get("money.name")
QUEST_THRESHOLD = 3
ARTIFACTS_THRESHOLD = 15

MAX_QUESTS_FOR_EVENTS = 600  # * 25 = 3000
MAX_QUESTS_FOR_TOWN_EVENTS = MAX_QUESTS_FOR_EVENTS * 2

NUM_MULT_LUT = {4: 2.5, 8: 2, 12: 1.5, 16: 1, 20: 0.75}


def _gain(xp: int, money: int, renown: int, tax: float = 0) -> str:
    tax_str = "" if tax == 0 else f" (taxed {int(tax * 100)}% by your guild)"
    renown_str = "" if renown == 0 else f"You gain {renown} renown"
    return f"\n\n_You gain {xp} xp & {money} {MONEY}{tax_str}\n\n{renown_str}_"


def _get_tourney_score_multiplier(player_num: int) -> int:
    for player_num_threshold, mult in NUM_MULT_LUT.items():
        if player_num <= player_num_threshold:
            return mult
    return 1


class _HighestQuests:
    """records highest reached quest by players per zone, useful to the generator to see what it has to generate"""

    FILENAME = "questprogressdata.json"

    def __init__(self, data: dict[str, int]) -> None:
        self.__data: dict[int, int] = {}
        for k, v in data.items():
            self.__data[int(k)] = v

    @classmethod
    def load_from_file(cls) -> Self:
        if os.path.isfile(cls.FILENAME):
            with open(cls.FILENAME) as f:
                return _HighestQuests(json.load(f))
        return _HighestQuests({})

    def save(self):
        with open(self.FILENAME, "w") as f:
            json.dump(self.__data, f)

    def update(self, zone_id: int, progress: int) -> None:
        if self.__data.get(zone_id - 1, 0) < progress:
            self.__data[zone_id - 1] = progress
            self.save()

    def is_quest_number_too_low(self, zone: Zone, number_of_quests: int) -> bool:
        return number_of_quests < (
            self.__data.get(zone.zone_id - 1, 0) + QUEST_THRESHOLD
        )


def add_to_zones_players_map(
    zones_player_map: dict[int, list[Player]], adventure_container: AdventureContainer
) -> None:
    """add the player to a map that indicates which zone it is in. Used for meeting other players."""
    zone_id = adventure_container.zone().zone_id if adventure_container.zone() else 0
    if zone_id not in zones_player_map:
        zones_player_map[zone_id] = []
    zones_player_map[zone_id].append(adventure_container.player)


class Manager(ABC):
    """generic manager object"""

    def __init__(self, database: PilgramDatabase):
        self.database = database

    def db(self) -> PilgramDatabase:
        """wrapper around the acquire method to make calling it less verbose"""
        return self.database.acquire()


class QuestManager(Manager):
    """helper class to neatly manage zone events & quests"""

    def __init__(
        self,
        database: PilgramDatabase,
        update_interval: timedelta,
        updates_per_second: int = 10,
    ) -> None:
        """
        :param database: database adapter to use to get & set data
        :param update_interval: the amount of time that has to pass since the last update before another update
        :param updates_per_second: the amount of time in seconds between notifications
        """
        super().__init__(database)
        self.update_interval = update_interval
        self.highest_quests = _HighestQuests.load_from_file()
        self.updates_per_second = 1 / updates_per_second

    def _complete_quest(self, ac: AdventureContainer) -> None:
        quest: Quest = ac.quest
        player: Player = self.db().get_player_data(
            ac.player.player_id
        )  # get the most up to date object
        ac.player = player
        tax: float = 0
        quest_finished, roll, value_to_beat = quest.finish_quest(player)
        if quest_finished:
            xp, money = quest.get_rewards(player)
            renown = quest.get_prestige() * 200
            if player.guild:
                guild = self.db().get_guild(
                    player.guild.guild_id
                )  # get the most up-to-date object
                guild.prestige += quest.get_prestige()
                guild_members = len(self.db().get_guild_members_data(guild))
                mult = _get_tourney_score_multiplier(guild_members)
                guild.tourney_score += int(renown * mult)
                self.db().update_guild(guild)
                player.guild = guild
                if guild.founder != player:  # check if winnings should be taxed
                    founder = self.db().get_player_data(
                        guild.founder.player_id
                    )  # get most up-to-date object
                    tax = guild.tax / 100
                    amount = int(money * tax)
                    amount_am = founder.add_money(amount)  # am = after modifiers
                    self.db().update_player_data(founder)
                    self.db().create_and_add_notification(
                        founder,
                        Strings.tax_gain.format(amount=amount_am, name=player.name),
                    )
                    money -= amount
            player.add_xp(xp)
            money_am = player.add_money(money)  # am = after modifiers
            player.completed_quests += 1
            player.renown += renown
            piece: bool = False
            if random.randint(1, 10) < (
                3 + player.cult.artifact_drop_bonus
            ):  # 30% base chance to gain a piece of an artifact
                player.artifact_pieces += 1
                piece = True
            self.db().create_and_add_notification(
                player,
                quest.success_text
                + Strings.quest_success.format(name=quest.name)
                + f"\n\n{Strings.quest_roll.format(roll=roll, target=value_to_beat)}"
                + _gain(xp, money_am, renown, tax=tax)
                + (Strings.piece_found if piece else ""),
            )
        else:
            self.db().create_and_add_notification(
                player,
                quest.failure_text
                + Strings.quest_fail.format(name=quest.name)
                + f"\n\n{Strings.quest_roll.format(roll=roll, target=value_to_beat)}",
            )
        self.highest_quests.update(
            ac.zone().zone_id, ac.quest.number + 1
        )  # zone() will return a zone and not None since player must be in a quest to reach this part of the code
        ac.quest = None
        self.db().update_quest_progress(ac)
        player.progress.set_zone_progress(quest.zone, quest.number + 1)
        player.hp_percent = 1.0
        self.db().update_player_data(player)
        if player.get_number_of_tried_quests() == 4:
            self.db().create_and_add_notification(
                player,
                Strings.you_can_choose_a_cult
            )

    @staticmethod
    def __player_regenerate_hp(ac: AdventureContainer, player: Player) -> str:
        hours_passed: float = (datetime.now() - ac.last_update).seconds / 3600
        regenerated_hp: int = (
            int((player.gear_level * 0.75) * hours_passed) + player.cult.passive_regeneration
        )
        player.modify_hp(regenerated_hp)
        return f"You regenerate {regenerated_hp} HP ({player.get_hp_string()})."

    def _process_event(self, ac: AdventureContainer) -> None:
        zone = ac.zone()
        event = self.db().get_random_zone_event(zone)
        player: Player = self.db().get_player_data(
            ac.player.player_id
        )  # get the most up-to-date object
        xp, money = event.get_rewards(ac.player)
        player.add_xp(xp)
        money_am = player.add_money(money)  # am = after modifiers
        ac.player = player
        if player.hp_percent < 1.0:
            regeneration_text = self.__player_regenerate_hp(ac, player)
        else:
            regeneration_text = ""
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        text = f"*{event.event_text}*{_gain(xp, money_am, 0)}"
        if ac.is_on_a_quest():
            if player.player_id in QTE_CACHE:
                del QTE_CACHE[player.player_id]
                text = Strings.qte_failed + "\n\n" + text
            elif random.randint(1, 10) <= (
                1 + player.cult.qte_frequency_bonus
            ):  # 10% base chance of a quick time event if player is on a quest
                # log.info(f"Player '{player.name}' encountered a QTE.")
                qte = random.choice(QuickTimeEvent.LIST)
                QTE_CACHE[player.player_id] = qte
                text += f"*QTE*\n\n{qte}\n\n"
            elif random.randint(1, 10) <= (
                1 + player.cult.discovery_bonus
            ):  # 10% base change of finding an item
                items = self.db().get_player_items(player.player_id)
                if len(items) < player.get_inventory_size():
                    item = Equipment.generate(
                        player.level + random.randint(0, 5),
                        EquipmentType.get_random(),
                        random.randint(0, 3),
                    )
                    # log.info(f"Player '{player.name}' found item: '{item.name}'.")
                    item_id = self.db().add_item(item, player)
                    item.equipment_id = item_id
                    items.append(item)
                    text += f"You found an item:\n*{item.name}*\n\n"
            text += regeneration_text
        self.db().create_and_add_notification(ac.player, text)

    def _process_combat(
        self, ac: AdventureContainer, updates: list[AdventureContainer]
    ) -> None:
        player: Player = self.db().get_player_data(ac.player.player_id)
        self.__player_regenerate_hp(ac, player)
        hours_passed: float = (datetime.now() - ac.last_update).seconds / 3600
        regenerated_hp: int = (
            1 + int(player.gear_level * hours_passed) + player.cult.passive_regeneration
        )
        player.modify_hp(regenerated_hp)
        # select helper from current updates
        helper: Player | None = None
        for update in updates:
            if (
                (player.guild is not None)
                and (update.player != player)
                and update.is_on_a_quest()
                and (update.zone() == ac.zone())
                and (update.player.guild is not None)
                and (update.player.guild == player.guild)
            ):
                helper = update.player
                break
        enemy_level_modifier: int = ac.quest.number
        if ForcedCombat.is_set(player.flags):
            days_left = (ac.finish_time - datetime.now()).days
            enemy_level_modifier += 5 - days_left if days_left < 5 else 1
        enemy = Enemy(
            self.db().get_random_enemy_meta(ac.quest.zone), [], enemy_level_modifier
        )
        combat = CombatContainer([player, enemy], {player: helper, enemy: None})
        text = "Combat starts!\n\n" + combat.fight()
        if player.is_dead():
            log.info(
                f"Player '{player.name}' died in combat against a {enemy.meta.name}"
            )
            text += f"\n\n{enemy.meta.lose_text}" + Strings.quest_fail.format(
                name=ac.quest.name
            )
            ac.quest = None
            player.hp_percent = 1.0
        else:
            log.info(f"Player '{player.name}' won against a {enemy.meta.name}")
            xp, money = enemy.get_rewards(player)
            renown = (enemy.get_level() + ac.quest.number + 1) * 10
            player.add_xp(xp)
            player.renown += renown
            money_am = player.add_money(money)
            text += f"\n\n{enemy.meta.win_text}{_gain(xp, money_am, renown)}"
            # more rewards if combat was forced
            if ForcedCombat.is_set(player.flags) and (
                random.random() <= 0.5
            ):  # 50% change to get an artifact piece if combat was forced
                if (player.level - ac.quest.zone.level) < 6:
                    log.info(f"Artifact piece drop for {player.name}")
                    player.add_artifact_pieces(1)
                    text += Strings.piece_found
        # unset player flags
        for flag in BUFF_FLAGS:
            if flag.is_set(player.flags):
                player.flags = flag.unset(player.flags)
        if ForcedCombat.is_set(player.flags):
            player.flags = ForcedCombat.unset(player.flags)
        # save data to db
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        # notify player
        self.db().create_and_add_notification(ac.player, text, notification_type="Combat Log")

    def process_update(
        self, ac: AdventureContainer, updates: list[AdventureContainer]
    ) -> None:
        if ac.is_on_a_quest():
            player: Player = self.db().get_player_data(ac.player.player_id)
            if ac.is_quest_finished():
                self._complete_quest(ac)
            elif ForcedCombat.is_set(player.flags) or (
                random.randint(1, 100) <= 10
            ):  # 10% base chance of combat
                self._process_combat(ac, updates)
            else:
                self._process_event(ac)
        else:
            self._process_event(ac)

    def get_updates(self) -> list[AdventureContainer]:
        return self.db().get_all_pending_updates(self.update_interval)

    def handle_players_meeting(self, zones_players_map: dict[int, list[Player]]):
        """
        handle the meeting of 2 players for each visited zone this update.

        The more time passes between quest manager thread calls, the better this works, because it accumulates more
        players. Too much time however and very few players will never be notified. Gotta find a balance.
        """
        for zone_id in zones_players_map:
            if (
                len(zones_players_map[zone_id]) < 4
            ):  # only let players meet if there's more than 4 players in a zone
                if len(zones_players_map[zone_id]) < 2:
                    # if there's only one player then skip
                    continue
                if random.randint(1, 20) < 15:
                    # if there's less than 4 but more than one, have a very low chance of an encounter
                    continue
            # choose randomly the players that will meet
            players: list[Player] = zones_players_map[zone_id]
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
            xp = (
                (10 * zone_id * max([player1.level, player2.level]))
                if zone_id > 0
                else 10
            )
            text = (
                f"{string} {random.choice(actions)}\n\n{Strings.xp_gain.format(xp=xp)}"
            )
            player1.add_xp(xp)
            player2.add_xp(xp)
            self.db().update_player_data(player1)
            self.db().update_player_data(player2)
            self.db().create_and_add_notification(player1, text.format(name=player2.name))
            self.db().create_and_add_notification(player2, text.format(name=player1.name))
            log.info(f"Players {player1.name} & {player2.name} have met")
            sleep(self.updates_per_second * 2)

    def run(self) -> None:
        zones_players_map: dict[int, list[Player]] = {}
        updates = self.get_updates()
        for update in updates:
            if update.player.cult.can_meet_players:
                add_to_zones_players_map(zones_players_map, update)
            self.process_update(update, updates)
            sleep(self.updates_per_second)
        self.handle_players_meeting(zones_players_map)


class GeneratorManager(Manager):
    """helper class to manage the quest & zone event generator"""

    def __init__(self, database: PilgramDatabase, generator: PilgramGenerator) -> None:
        """
        :param database: database adapter to use to get & set data
        :param generator: generator adapter to used to generate quests & events
        """
        super().__init__(database)
        self.generator = generator

    def __get_zones_to_generate(
        self, biases: dict[int, int]
    ) -> tuple[list[Zone], list[int]]:
        result: list[Zone] = []
        zones = self.db().get_all_zones()
        hq = _HighestQuests.load_from_file()
        quest_counts = self.db().get_quests_counts()
        for zone, count in zip(zones, quest_counts, strict=False):
            if hq.is_quest_number_too_low(zone, count - biases.get(zone.zone_id, 0)):
                result.append(zone)
        return result, quest_counts

    def run(
        self, timeout_between_ai_calls: float, biases: dict[int, int] = None
    ) -> None:
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
                    log.error(
                        f"Encountered an error while generating quests for zone {zone.zone_id}: {e}"
                    )
                sleep(timeout_between_ai_calls)
                if quest_numbers[zone.zone_id - 1] < MAX_QUESTS_FOR_EVENTS:
                    # only generate zone events & enemies if there are less than MAX_QUESTS_FOR_EVENTS
                    log.info(f"generating zone events for zone {zone.zone_id}")
                    zone_events = self.generator.generate_zone_events(zone)
                    self.db().add_zone_events(zone_events)
                    log.info(f"Zone events generation done for zone {zone.zone_id}")
                    log.info(f"Generating enemy metas for zone {zone.zone_id}")
                    enemy_metas = self.generator.generate_enemy_metas(zone)
                    for enemy_meta in enemy_metas:
                        try:
                            self.db().add_enemy_meta(enemy_meta)
                        except Exception as e:
                            log.error(e)
                    log.info(
                        f"Enemy metas event generation done for zone {zone.zone_id}"
                    )
            except Exception as e:
                log.error(
                    f"Encountered an error while generating events & enemies for zone {zone.zone_id}: {e}"
                )
            finally:
                sleep(timeout_between_ai_calls)
        if len(zones) > 0:
            # generate town events only if there ia less than 6000 (600 * 2 * 5) of them
            if sum(quest_numbers) > MAX_QUESTS_FOR_TOWN_EVENTS:
                return
            # generate something for the town if you generated something for other zones
            try:
                log.info("generating zone events for town")
                town_events = self.generator.generate_zone_events(TOWN_ZONE)
                self.db().add_zone_events(town_events)
                log.info("Zone event generation done for town")
            except Exception as e:
                log.error(f"Encountered an error while generating for town zone: {e}")
        # generate artifacts if needed
        available_artifacts = self.db().get_number_of_unclaimed_artifacts()
        log.info(
            f"Available artifacts: {available_artifacts}, threshold: {ARTIFACTS_THRESHOLD}"
        )
        if available_artifacts < ARTIFACTS_THRESHOLD:
            log.info("generating artifacts")
            try:
                artifacts = self.generator.generate_artifacts()
                for artifact in artifacts:
                    try:
                        self.db().add_artifact(artifact)
                    except Exception as e:
                        log.error(
                            f"Encountered an error while adding artifact '{artifact.name}': {e}"
                        )
                        try:
                            artifact.name += " of " + generate_random_eldritch_name()
                            log.info(
                                f"changed name ({artifact.name}), trying to add the artifact again"
                            )
                            self.db().add_artifact(artifact)
                        except Exception as e:
                            log.error(f"adding a random name did not work: {e}")
                log.info("artifact generation done")
            except Exception as e:
                log.error(f"Encountered an error while generating artifacts: {e}")


class TourneyManager(Manager):
    def __init__(
        self,
        database: PilgramDatabase,
        notification_delay: int,
    ) -> None:
        super().__init__(database)
        self.notification_delay = notification_delay

    def db(self) -> PilgramDatabase:
        """wrapper around the acquire method to make calling it less verbose"""
        return self.database.acquire()

    def run(self) -> None:
        tourney = self.db().get_tourney()
        if not tourney.has_tourney_ended():
            return
        log.info(f"Tourney {tourney.tourney_edition} has ended")
        top_guilds = self.db().get_top_n_guilds_by_score(3)
        # give artifact piece to 1st guild owner
        first_guild = top_guilds[0]
        winner = self.db().get_player_data(first_guild.founder.player_id)
        winner.artifact_pieces += 1
        self.db().create_and_add_notification(
            winner,
            f"Your guild won the *biweekly Guild Tourney n.{tourney.tourney_edition}*!\nyou are awarded an artifact piece!",
        )
        sleep(self.notification_delay)
        # award money to top 3 guilds members
        for guild, reward, position in zip(
            top_guilds, (10000, 5000, 1000), ("first", "second", "third"), strict=False
        ):
            log.info(f"guild '{guild.name}' placed {position}")
            members = self.db().get_guild_members_data(guild)
            for player_id, _, _ in members:
                player = self.db().get_player_data(player_id)
                # players that joined the guild less than a day ago will not get tourney rewards
                if (datetime.now() - player.last_guild_switch) < timedelta(days=1):
                    continue
                reward_am = player.add_money(reward)  # am = after modifiers
                self.db().update_player_data(player)
                self.db().create_and_add_notification(
                    player,
                    f"Your guild placed *{position}* in the *biweekly Guild Tourney n.{tourney.tourney_edition}*!\nYou are awarded {reward_am} {MONEY}!",
                )
                sleep(self.notification_delay)
        # reset all scores & start a new tourney
        self.db().reset_all_guild_scores()
        tourney.tourney_start = time.time()
        tourney.tourney_edition += 1
        log.info(
            f"New tourney started, edition {tourney.tourney_edition}, start: {tourney.tourney_start} (now)"
        )
        self.db().update_tourney(tourney)


class TimedUpdatesManager(Manager):
    """helper class to encapsulate all the small updates needed for the game to function"""

    def __init__(self, database: PilgramDatabase) -> None:
        super().__init__(database)

    def run(self) -> None:
        # update cult members
        Cult.update_number_of_members(self.db().get_cults_members_number())
        # update randomized stats
        for cult in Cult.LIST:
            if cult.can_randomize():
                cult.randomize()
        # update auctions
        expired_auctions: list[Auction] = self.db().get_expired_auctions()
        log.info(f"{len(expired_auctions)} expired auctions to process")
        for auction in expired_auctions:
            if not auction.best_bidder:
                self.db().create_and_add_notification(
                    auction.auctioneer,
                    f"No one bid on your auctioned item ({auction.item.name}) and it expired!",
                )
                sleep(1)
            else:
                self.db().create_and_add_notification(
                    auction.auctioneer,
                    f"Your auctioned item '{auction.item.name}' has been bought by {auction.best_bidder} for {auction.best_bid} {MONEY}.",
                )
                self.db().create_and_add_notification(
                    auction.best_bidder,
                    f"You won the auction for item '{auction.item.name}', you paid {auction.best_bid} {MONEY}.",
                )
                # handle money transfer
                auction.best_bidder.money -= auction.best_bid
                auction.auctioneer.add_money(auction.best_bid)
                self.db().update_player_data(auction.auctioneer)
                self.db().update_player_data(auction.best_bidder)
                # handle item transfer
                self.db().update_item(auction.item, auction.best_bidder)
                auctioneer_items = self.db().get_player_items(
                    auction.auctioneer.player_id
                )
                winner_items = self.db().get_player_items(auction.best_bidder.player_id)
                auctioneer_items.remove(auction.item)
                winner_items.append(auction.item)
                # wait a couple of seconds since you just sent 2 messages
                sleep(2)
            # delete the auction from the database
            self.db().delete_auction(auction)


class NotificationsManager(Manager):
    """class that is tasked with sending all the notifications"""
    _PENDING_NOTIFICATIONS = "pending_notifications.json"

    def __init__(self, notifier: PilgramNotifier, database: PilgramDatabase) -> None:
        self.notifier = notifier
        super().__init__(database)

    def run(self) -> None:
        notifications = self.db().get_pending_notifications()
        for notification in notifications:
            self.notifier.notify(notification)
            sleep(1)

    def load_pending_notifications(self) -> None:
        if not os.path.isfile("pending_notifications.json"):
            return
        with open(self._PENDING_NOTIFICATIONS, "r") as f:
            notifications = json.load(f)["notifications"]
            for notification_dict in notifications:
                self.db().create_and_add_notification(
                    Player.create_default(notification_dict["id"], str(notification_dict["id"]), ""),
                    notification_dict["text"]
                )
        os.remove(self._PENDING_NOTIFICATIONS)

    def save_pending_notifications(self) -> None:
        notifications = self.db().get_pending_notifications()
        if not notifications:
            return
        with open(self._PENDING_NOTIFICATIONS, "w") as f:
            json.dump({"notifications": [{"id": n.target.player_id, "text": n.text} for n in notifications]}, f)


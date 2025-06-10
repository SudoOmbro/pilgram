import json
import logging
import os
import random
import time
from abc import ABC
from copy import deepcopy, copy
from datetime import datetime, timedelta
from time import sleep
from typing import Self

from pilgram.classes import (
    QTE_CACHE,
    TOWN_ZONE,
    AdventureContainer,
    Auction,
    Enemy,
    Player,
    Quest,
    QuickTimeEvent,
    Zone, InternalEventBus, Event, Notification, Pet,
)
from pilgram.combat_classes import CombatContainer, CombatActor
from pilgram.equipment import Equipment, EquipmentType, ConsumableItem
from pilgram.flags import BUFF_FLAGS, ForcedCombat, Ritual1, Ritual2, Pity1, Pity2, Pity3, Pity4, PITY_FLAGS, Pity5, \
    QuestCanceled, InCrypt, Raiding, DeathwishMode, Catching
from pilgram.generics import PilgramDatabase, PilgramGenerator, PilgramNotifier
from pilgram.globals import ContentMeta
from pilgram.listables import DEFAULT_TAG
from pilgram.modifiers import get_modifiers_by_rarity, Rarity, Modifier
from pilgram.strings import Strings, rewards_string
from pilgram.utils import generate_random_eldritch_name

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


MONEY = ContentMeta.get("money.name")
QUEST_THRESHOLD = 3
ARTIFACTS_THRESHOLD = 15

MAX_QUESTS_FOR_EVENTS = 600  # * 25 = 3000
MAX_QUESTS_FOR_TOWN_EVENTS = MAX_QUESTS_FOR_EVENTS * 2

NUM_MULT_LUT = {
    4: 2,
    8: 1.75,
    12: 1.5,
    16: 1.25,
    20: 1
}


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
        self.player_shades: dict[int, list[Player]] = {}

    @staticmethod
    def _create_shade(
            player: Player,
            max_equipped_items: int = 3,
            empty_satchel: bool = True,
            suffix: str = "'s Shade"
    ) -> Player:
        # deepcopy a player
        shade: Player = deepcopy(player)
        shade.name = player.name + suffix
        shade.hp_percent = 1.0
        shade.team = 1
        # remove some equipped items if necessary
        while len(list(shade.equipped_items.values())) > max_equipped_items:
            key = random.choice(list(shade.equipped_items.keys()))
            del shade.equipped_items[key]
        # empty satchel
        if empty_satchel:
            shade.satchel = []
        return shade

    def create_shade(self, player: Player, zone: Zone | None) -> None:
        if zone is None:
            return
        log.info(f"creating shade of player {player.name} in {zone.zone_name}")
        if self.player_shades.get(zone.zone_id, None) is None:
            self.player_shades[zone.zone_id] = []
        shade: Player = self._create_shade(player)
        self.player_shades[zone.zone_id].append(shade)

    def _complete_quest(self, ac: AdventureContainer) -> None:
        quest: Quest = ac.quest
        player: Player = self.db().get_player_data(
            ac.player.player_id
        )  # get the most up to date object
        ac.player = player
        tax: float = 0
        quest_finished, roll, value_to_beat = quest.finish_quest(player)
        anomaly = self.db().get_current_anomaly()
        # pity
        if (not quest_finished) and Pity5.is_set(player.flags):
            quest_finished = True
        # give quest rewards
        if quest_finished:
            # reset pity flags
            for flag in PITY_FLAGS:
                if flag.is_set(player.flags):
                    player.unset_flag(flag)
            # get rewards
            xp, money = quest.get_rewards(player)
            if ac.zone() == anomaly.zone:
                xp = int(xp * anomaly.xp_mult)
                money = int(money * anomaly.money_mult)
            renown = quest.get_prestige() * 200
            xp_am = player.add_xp(xp)  # am = after modifiers
            money_am = player.add_money(money)  # am = after modifiers
            # pay taxes if player is in a guild
            if player.guild:
                guild = self.db().get_guild(player.guild.guild_id)  # get the most up-to-date object
                guild.prestige += quest.get_prestige()
                tax = guild.tax / 100
                amount = int(money_am * tax)
                guild.bank += amount
                player.money -= amount
                guild_members = len(self.db().get_guild_members_data(guild))
                mult = _get_tourney_score_multiplier(guild_members)
                guild.tourney_score += int(renown * mult)
                self.db().update_guild(guild)
                # create a log
                guild.create_bank_log("deposit", player.player_id, amount)
            # add to completed quests & add renown
            player.completed_quests += 1
            player.add_renown(renown)
            # add zone essence
            player.add_essence(quest.zone.zone_id, 1)
            # get artifact piece if lucky
            piece: bool = False
            if random.randint(1, 10) < (
                3 + player.vocation.artifact_drop_bonus + (anomaly.artifact_drop_bonus if ac.zone() == anomaly.zone else 0)
            ):  # 30% base chance to gain a piece of an artifact
                player.artifact_pieces += 1
                piece = True
            self.db().create_and_add_notification(
                player,
                quest.success_text
                + Strings.quest_success.format(name=quest.name)
                + f"\n\n{Strings.quest_roll.format(roll=roll, target=value_to_beat)}"
                + rewards_string(xp_am, money_am, renown, tax=tax)
                + (Strings.piece_found if piece else ""),
            )
        else:
            # create shade & notification text
            self.create_shade(player, ac.zone())
            failure_text = quest.failure_text + Strings.quest_fail.format(name=quest.name) + f"\n\n{Strings.quest_roll.format(roll=roll, target=value_to_beat)}"
            # give rewards anyway if vocation permits it
            if player.vocation.quest_fail_rewards_multiplier > 0:
                xp, money = quest.get_rewards(player)
                xp_am = player.add_xp(xp)  # am = after modifiers
                money_am = player.add_money(money)  # am = after modifiers
                failure_text + rewards_string(xp_am, money_am, 0)
            # create the notification
            self.db().create_and_add_notification(
                player,
                failure_text,
            )
            # add to pity counter
            if not Pity1.is_set(player.flags):
                player.flags = Pity1.set(player.flags)
            elif not Pity2.is_set(player.flags):
                player.flags = Pity2.set(player.flags)
            elif not Pity3.is_set(player.flags):
                player.flags = Pity3.set(player.flags)
            elif not Pity4.is_set(player.flags):
                player.flags = Pity4.set(player.flags)
            elif not Pity5.is_set(player.flags):
                player.flags = Pity5.set(player.flags)
        self.highest_quests.update(
            ac.zone().zone_id, ac.quest.number + 1
        )  # zone() will return a zone and not None since player must be in a quest to reach this part of the code
        ac.quest = None
        self.db().update_quest_progress(ac)
        player.progress.set_zone_progress(quest.zone, quest.number + 1)
        player.hp_percent = 1.0
        self.db().update_player_data(player)

    @staticmethod
    def __player_regenerate_hp(ac: AdventureContainer, player: Player) -> str:
        hours_passed: float = (datetime.now() - ac.last_update).seconds / 3600
        regenerated_hp: int = (
            int((player.gear_level * 0.75) * hours_passed) + player.vocation.passive_regeneration
        )
        player.modify_hp(regenerated_hp)
        return f"You regenerate {regenerated_hp} HP ({player.get_hp_string()})."

    def _process_event(self, ac: AdventureContainer) -> None:
        zone = ac.zone()
        event = self.db().get_random_zone_event(zone)
        anomaly = self.db().get_current_anomaly()
        player: Player = self.db().get_player_data(
            ac.player.player_id
        )  # get the most up-to-date object
        xp, money = event.get_rewards(ac.player)
        if ac.zone() == anomaly.zone:
            xp = int(xp * anomaly.xp_mult)
            money = int(money * anomaly.money_mult)
        xp_am = player.add_xp(xp)  # am = after modifiers
        money_am = player.add_money(money)  # am = after modifiers
        ac.player = player
        if player.hp_percent < 1.0:
            regeneration_text = self.__player_regenerate_hp(ac, player)
        else:
            regeneration_text = ""
        text = f"*{event.event_text}*{rewards_string(xp_am, money_am, 0)}"
        if ac.is_on_a_quest():
            player.add_sanity(5)
            if player.player_id in QTE_CACHE:
                del QTE_CACHE[player.player_id]
                text = Strings.qte_failed + "\n\n" + text
            elif random.randint(1, 10) <= (1 + player.vocation.qte_frequency_bonus):
                # log.info(f"Player '{player.name}' encountered a QTE.")
                qte = random.choice(QuickTimeEvent.LISTS[DEFAULT_TAG])
                QTE_CACHE[player.player_id] = qte
                text += f"*QTE*\n\n{qte}\n\n"
            elif random.randint(1, 10) <= (
                1 + player.vocation.discovery_bonus + (anomaly.item_drop_bonus if ac.zone() == anomaly.zone else 0)
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
        else:
            player.add_sanity(20)
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        self.db().create_and_add_notification(ac.player, text)

    @staticmethod
    def _buff_enemy(player: Player, enemy: Enemy | Player):
        if Ritual1.is_set(player.flags):
            if isinstance(enemy, Player):
                enemy.level += 5
            else:
                enemy.level_modifier += 5
        if Ritual2.is_set(player.flags):
            if isinstance(enemy, Player):
                enemy.level += 5
            else:
                enemy.level_modifier += 5

    def _process_combat_death(self, player: Player, ac: AdventureContainer) -> str:
        """ either revive the player or respawn them in town """
        if (player.vocation.revive_chance > 0) and (random.random() < player.vocation.revive_chance):
            player.hp_percent = 0.25
            return Strings.post_combat_revive
        else:
            lost_money: int = int(player.money * 0.1 * player.vocation.money_loss_on_death)
            previous_quest = ac.quest  # use this otherwise the death notification will always say 'crypt exploration'
            ac.quest = None
            if DeathwishMode.is_set(player.flags):
                player.level = 1
                player.money = 0
                player.essences = {}
                player.equipped_items = {}
                self.db().create_and_add_notification(player, "You died while Deathwish mode was active! You lost all of your levels, BA & essences. Also all of your items have been unequipped.")
            else:
                player.money -= lost_money  # lose 10% of money on death
            player.hp_percent = 1.0
            player.sanity = 55
            player.renown = 0
            return (Strings.quest_fail + Strings.lose_money).format(name=previous_quest.name if previous_quest else Strings.crypt_quest_name, money=lost_money)

    def _create_enemy(self, ac: AdventureContainer, modifiers_amount: int, level_modifier: int, prefix: str = ""):
        anomaly = self.db().get_current_anomaly()
        modifiers: list[Modifier] = []
        enemy_level_modifier: int = level_modifier
        if ac.zone() == anomaly.zone:
            enemy_level_modifier += anomaly.level_bonus
        for _ in range(modifiers_amount):
            choice_list = get_modifiers_by_rarity(random.randint(Rarity.UNCOMMON, Rarity.LEGENDARY))
            modifier_type: type[Modifier] = random.choice(choice_list)
            modifiers.append(modifier_type.generate(ac.quest.zone.level + enemy_level_modifier))
        return Enemy(
            self.db().get_random_enemy_meta(ac.quest.zone),
            modifiers,
            int(enemy_level_modifier),
            name_prefix=prefix
        )

    def _process_combat(
        self, ac: AdventureContainer, updates: list[AdventureContainer]
    ) -> None:
        player: Player = self.db().get_player_data(ac.player.player_id)
        anomaly = self.db().get_current_anomaly()
        self.__player_regenerate_hp(ac, player)
        hours_passed: float = (datetime.now() - ac.last_update).seconds / 3600
        regenerated_hp: int = (
            1 + int(player.gear_level * hours_passed) + player.vocation.passive_regeneration
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
        if not self.player_shades.get(ac.zone().zone_id, None):
            # if there are no shades to fight then generate an enemy
            enemy_level_modifier: int = ac.quest.number
            if ForcedCombat.is_set(player.flags):
                days_left = (ac.finish_time - datetime.now()).days
                enemy_level_modifier += 2 + (5 - days_left if days_left < 5 else 1)
                modifiers_amount = 2
                if DeathwishMode.is_set(player.flags):
                    modifiers_amount += 2
                    enemy_level_modifier *= 2
                if player.sanity <= 50:
                    modifiers_amount += 1
                    enemy_level_modifier += 5 + ((player.get_max_sanity() - player.sanity)/5)
                if player.sanity <= 0:
                    modifiers_amount += int((-player.sanity) / 20)
                    if random.randint(0, -player.sanity) > 145:
                        self.db().create_and_add_notification(player, Strings.insanity_meet_yourself)
                        enemy = self._create_shade(
                            player,
                            max_equipped_items=7,
                            empty_satchel=False,
                            suffix="'s Nightmare"
                        )
                    else:
                        enemy = self._create_enemy(ac, modifiers_amount, enemy_level_modifier)
                else:
                    enemy = self._create_enemy(ac, modifiers_amount, enemy_level_modifier)
            elif random.randint(1, 100) < 20:
                # 20% chance of randomly getting a monster with a modifier
                enemy = self._create_enemy(ac, 1, enemy_level_modifier)
            else:
                enemy = self._create_enemy(ac, 0, enemy_level_modifier)
        else:
            # fight a shade
            enemy = self.player_shades[ac.zone().zone_id].pop(0)
        # buff enemy with ritual
        self._buff_enemy(player, enemy)
        # do combat
        combat = CombatContainer([player, enemy], {player: helper, enemy: None})
        text = "Combat starts!\n\n" + combat.fight()
        # finish combat
        if player.is_dead():
            if isinstance(enemy, Enemy):
                text += f"\n\n{enemy.meta.lose_text}"
                log.info(f"Player '{player.name}' died in combat against a {enemy.meta.name}")
            else:
                text += f"\n\n{Strings.shade_loss}"
                log.info(f"Player '{player.name}' died in combat against {enemy.name}")
            self.create_shade(player, ac.zone())
            text += self._process_combat_death(player, ac)
        else:
            log.info(f"Player '{player.name}' won against {enemy.get_name()}")
            # get rewards
            xp, money = enemy.get_rewards(player)
            if ac.zone() == anomaly.zone:
                xp = int(xp * anomaly.xp_mult)
                money = int(money * anomaly.money_mult)
            renown = (enemy.get_level() + ac.quest.number + 1) * 10
            # add rewards
            xp_am = player.add_xp(xp)
            player.add_renown(renown)
            money_am = player.add_money(money)
            # handle pet
            if player.pet is not None:
                player.pet.add_xp(xp, owner=player)
                player.pet.heal()
                self.db().update_pet(player.pet, player)
            # create notification text
            if isinstance(enemy, Enemy):
                text += f"\n\n{enemy.meta.win_text}{rewards_string(xp_am, money_am, renown)}"
            else:
                text += f"\n\n{Strings.shade_win}{rewards_string(xp_am, money_am, renown)}"
                player.sanity += 50
            # more rewards if combat was forced
            if ForcedCombat.is_set(player.flags) and (
                random.random() <= 0.5
            ):  # 40% change to get an artifact piece if combat was forced
                if (player.level - enemy.get_level()) < 5:
                    log.info(f"Artifact piece drop for {player.name}")
                    player.add_artifact_pieces(1)
                    text += Strings.piece_found
            # add to guild tourney score & prestige
            if player.guild:
                guild = self.db().get_guild(player.guild.guild_id)  # get the most up-to-date object
                guild.tourney_score += enemy.get_level()
                prestige = enemy.get_prestige(ac.quest.zone.level)
                guild.prestige += max(1, prestige)
                self.db().update_guild(guild)
        # unset player flags
        for flag in BUFF_FLAGS:
            if flag.is_set(player.flags):
                player.flags = flag.unset(player.flags)
        if ForcedCombat.is_set(player.flags):
            player.unset_flag(ForcedCombat)
        # save data to db
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        # notify player
        self.db().create_and_add_notification(ac.player, text, notification_type="Combat Log")

    def _process_crypt_update(self, ac: AdventureContainer):
        player: Player = self.db().get_player_data(ac.player.player_id)
        shade = self._create_shade(self.db().get_random_player_data())
        self._buff_enemy(player, shade)
        combat = CombatContainer([player, shade], {player: None, shade: None})
        text = "Combat starts!\n\n" + combat.fight()
        if player.is_dead():
            player.unset_flag(InCrypt)
            text += f"\n\n{Strings.shade_loss}"
            log.info(f"Player '{player.name}' died in combat against {shade.name}")
            text += self._process_combat_death(player, ac)
        else:
            xp, money = shade.get_rewards(player)
            renown = shade.get_level() * 10
            # add rewards
            xp_am = player.add_xp(xp)
            player.add_renown(renown)
            money_am = player.add_money(money)
            # handle pet
            if player.pet is not None:
                player.pet.add_xp(xp, owner=player)
                player.pet.heal()
                self.db().update_pet(player.pet, player)
            text += f"\n\n{Strings.shade_win}{rewards_string(xp_am, money_am, renown)}"
        for flag in BUFF_FLAGS:
            if flag.is_set(player.flags):
                player.flags = flag.unset(player.flags)
        self.db().update_player_data(player)
        self.db().update_quest_progress(ac)
        self.db().create_and_add_notification(ac.player, text, notification_type="Combat Log")

    def process_raid_combat(self, ac: AdventureContainer, is_boss: bool):
        leader = self.db().get_player_data(ac.player.player_id)
        guild = self.db().get_owned_guild(leader)
        party = self.db().get_raid_participants(guild)
        mult = _get_tourney_score_multiplier(len(party))
        # get combat participants
        participants: list[CombatActor] = party + [self._create_enemy(ac, random.randint(0, 2), int(x.level / 3)) for x in party]
        if is_boss:
            guild.last_raid = datetime.now()
            participants.append(self._create_enemy(ac, 5, int(leader.level * 1.5), prefix="Legendary "))
        # process combat
        combat = CombatContainer(participants, {})
        combat_log = "Combat starts!\n\n" + combat.fight()
        # give rewards to members that are still alive & return dead members to town
        for member in party:
            if member.is_dead():
                member_ac = self.db().get_player_adventure_container(member)
                text = self._process_combat_death(member, member_ac)
                if not member_ac.is_on_a_quest():
                    member.unset_flag(Raiding)
                    self.db().update_player_data(member)
                    self.db().update_quest_progress(member_ac)
                    self.db().create_and_add_notification(member, combat_log + text)
                    continue
            xp, money = member.get_rewards(member)
            if is_boss:
                # finish quest
                member_ac = self.db().get_player_adventure_container(member)
                member_ac.quest = None
                member.unset_flag(Raiding)
                member.hp_percent = 1.0
                # add money, xp & renown (x4)
                xp_am = member.add_xp(xp * 4)
                money_am = member.add_money(money * 4)
                renown = member.get_prestige(ac.quest.zone.level) * 4
                member.add_renown(renown)
                guild.prestige += renown
                guild.tourney_score += int(renown * mult)
                # add relic
                item = Equipment.generate(member.level, EquipmentType.get_random("relic"), 3)
                items = self.db().get_player_items(member.player_id)
                item_id = self.db().add_item(item, member)
                item.equipment_id = item_id
                items.append(item)
                # notify player
                self.db().create_and_add_notification(
                    member,
                    combat_log + "\n\n" + Strings.raid_finished + rewards_string(xp_am, money_am, renown)
                )
                self.db().update_quest_progress(member_ac)
            else:
                # add money, xp & renown
                xp_am = member.add_xp(xp)
                money_am = member.add_money(money)
                renown = member.get_prestige(ac.quest.zone.level)
                member.add_renown(renown)
                # handle member pet
                if member.pet is not None:
                    member.pet.add_xp(xp, owner=member)
                    member.pet.hp_percent = 1.0
                    self.db().update_pet(member.pet, member)
                guild.prestige += renown
                # notify player
                self.db().create_and_add_notification(
                    member,
                    combat_log + "\n\n" + Strings.raid_win + rewards_string(xp_am, money_am, renown)
                )
            self.db().update_player_data(member)
        # if leader is dead then abort the raid
        if leader.is_dead():
            for member in party:
                if not member.is_dead():
                    member_ac = self.db().get_player_adventure_container(member)
                    self.db().create_and_add_notification(member, Strings.raid_leader_died)
                    member.unset_flag(Raiding)
                    member.hp_percent = 1.0
                    self.db().update_player_data(member)
                    self.db().update_quest_progress(member_ac)
        # update guild & leader adventure container
        self.db().update_guild(guild)
        self.db().update_quest_progress(ac)

    def process_catch_pet(self, ac: AdventureContainer):
        player = ac.player
        zone = ac.zone()
        bait: ConsumableItem or None = player.use_best_bait_item()
        bait_power = (0.1 + 0 if bait is None else bait.bait_power) * (player.level / zone.level)
        roll_result = player.roll(100)
        enemy = self._create_enemy(ac, random.randint(0, 2), 0)
        text = "Catching result:\n\n"
        if roll_result <= 100 * bait_power:
            # catch successful
            text += Strings.pet_caught.format(name=enemy.meta.name)
            pet = Pet.build_from_captured_enemy(player, enemy)
            pet_id = self.db().add_pet(pet, player)
            if player.pet is None:
                pet.id = pet_id
                player.pet = pet
        else:
            text += Strings.pet_escaped.format(name=enemy.meta.name)
        player.unset_flag(Catching)
        self.db().create_and_add_notification(player, text)
        self.db().update_player_data(player)

    def process_update(
        self, ac: AdventureContainer, updates: list[AdventureContainer]
    ) -> bool:
        """ Process a player update & return whether the player can meet other players """
        if ac.is_on_a_quest():
            player: Player = self.db().get_player_data(ac.player.player_id)
            if Raiding.is_set(ac.player.flags):
                try:
                    self.process_raid_combat(ac, ac.is_quest_finished())
                    return False
                except Exception as e:
                    log.error(f"an error occurred while processing raid for player {player.name}: {e}")
                    return False
            if Catching.is_set(player.flags):
                self.process_catch_pet(ac)
            elif ac.is_quest_finished():
                self._complete_quest(ac)
                return False
            elif QuestCanceled.is_set(player.flags):
                player.unset_flag(QuestCanceled)
                ac.player = player
                ac.quest = None
                self.db().update_quest_progress(ac)
                self.db().update_player_data(player)
                self.db().create_and_add_notification(player, Strings.quest_abandoned)
                return False
            elif ForcedCombat.is_set(player.flags) or (
                (random.randint(1, 100) + player.vocation.combat_frequency) >= 85
            ):  # 10% base chance of combat
                self._process_combat(ac, updates)
                return False
            else:
                self._process_event(ac)
        elif InCrypt.is_set(ac.player.flags):
            self._process_crypt_update(ac)
            return False
        else:
            self._process_event(ac)
        return True

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
            reward_value = (
                (10 * zone_id * max([player1.level, player2.level]))
                if zone_id > 0
                else 10
            )
            for player, other_player in zip([player1, player2], [player2, player1]):
                xp_am = player.add_xp(reward_value)
                mn_am = player.add_money(reward_value) if player.vocation.gain_money_on_player_meet else 0
                text = f"{string} {random.choice(actions)}" + rewards_string(xp_am, mn_am, 0)
                self.db().update_player_data(player)
                self.db().create_and_add_notification(
                    player,
                    text.format(name=other_player.name),
                    notification_type="Meeting"
                )

    def run(self) -> None:
        zones_players_map: dict[int, list[Player]] = {}
        updates = self.get_updates()
        for update in updates:
            if self.process_update(update, updates) and update.player.vocation.can_meet_players:
                add_to_zones_players_map(zones_players_map, update)
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
        zones: list[Zone] = self.db().get_all_zones()
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
        # update anomaly
        try:
            anomaly = self.db().get_current_anomaly()
            if anomaly.is_expired():
                zones = copy(self.db().get_all_zones())
                random.shuffle(zones)
                new_anomaly = self.generator.generate_anomaly(zones[0])
                self.db().update_anomaly(new_anomaly)
        except Exception as e:
            log.error("Encountered an error while generating anomaly: " + str(e))


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
        if len(top_guilds) < 3:
            return
        # give artifact piece to 1st guild owner
        first_guild = top_guilds[0]
        winner = self.db().get_player_data(first_guild.founder.player_id)
        winner.artifact_pieces += 1
        self.db().create_and_add_notification(
            winner,
            f"Your guild won the *biweekly Guild Tourney n.{tourney.tourney_edition}*!\nyou are awarded an artifact piece!",
        )
        # award money to top 3 guilds members
        for guild, reward, position in zip(
            top_guilds, (10000, 5000, 1000), ("first", "second", "third"), strict=False
        ):
            log.info(f"guild '{guild.name}' placed {position}")
            members = self.db().get_guild_members_data(guild)
            for player_id, _, _ in members:
                player = self.db().get_player_data(player_id)
                reward_am = player.add_money(reward)  # am = after modifiers
                log.info(f"rewarding {reward_am} money to {player.name}")
                self.db().update_player_data(player)
                log.info(f"notifying {player.name} of the win")
                self.db().create_and_add_notification(
                    player,
                    f"Your guild placed *{position}* in the *biweekly Guild Tourney n.{tourney.tourney_edition}*!\nYou are awarded {reward_am} {MONEY}!",
                )
                sleep(0.5)
        # reset all scores & start a new tourney
        self.db().reset_all_guild_scores()
        self.db().reset_caches()
        log.info(f"successfully reset all guild scores")
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
        # update auctions
        expired_auctions: list[Auction] = self.db().get_expired_auctions()
        log.info(f"{len(expired_auctions)} expired auctions to process")
        for auction in expired_auctions:
            if not auction.best_bidder:
                self.db().create_and_add_notification(
                    auction.auctioneer,
                    f"No one bid on your auctioned item ({auction.item.name}) and it expired!",
                )
            else:
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
                if auction.item in auctioneer_items:
                    auctioneer_items.remove(auction.item)
                winner_items.append(auction.item)
                # notify
                self.db().create_and_add_notification(
                    auction.auctioneer,
                    f"Your auctioned item '{auction.item.name}' has been bought by {auction.best_bidder.name} for {auction.best_bid} {MONEY}.",
                )
                self.db().create_and_add_notification(
                    auction.best_bidder,
                    f"You won the auction for item '{auction.item.name}', you paid {auction.best_bid} {MONEY}.",
                )
                # wait a couple of seconds since you just sent 2 messages
            # delete the auction from the database
            self.db().delete_auction(auction)


class NotificationsManager(Manager):
    """class that is tasked with sending all the notifications"""
    _PENDING_NOTIFICATIONS = "pending_notifications.json"

    def __init__(self, notifier: PilgramNotifier, database: PilgramDatabase) -> None:
        self.notifier = notifier
        super().__init__(database)
        self._tmp_blocked_users: list[int] = []

    def send_notification(self, notification: Notification, delay: float = 1.0) -> None:
        result = self.notifier.notify(notification)
        if not result.get("ok", False):
            reason = result.get("reason", "")
            if reason == "blocked":
                self._tmp_blocked_users.append(notification.target.player_id)
        sleep(delay)

    @staticmethod
    def get_internal_event_notification_text(event: Event) -> str:
        string = event.type
        if event.type == "level up":
            level: int = event.data["level"]
            string = f"You reached level {level}!"
            if level == 5:
                string += "\n\nYou unlocked the first profession slot!"
            elif level == 20:
                string += "\n\nYou unlocked the second profession slot!"
            if level == event.recipient.get_ascension_level():
                string += "\n\nYou can now ascend (if you have 10 artifact pieces)."
        elif event.type == "sanity low":
            sanity = event.data["sanity"]
            for value, strings in Strings.sanity_lines.items():
                if sanity >= value:
                    string = random.choice(strings)
        elif event.type == "pet level up":
            pet_name: str = event.data["name"]
            level: int = event.data["level"]
            string = f"Your pet '{pet_name}' has reached level {level}!"
        return string

    def run(self) -> None:
        notifications = self.db().get_pending_notifications()
        # handle internal events (more important)
        for event in InternalEventBus().consume_all():
            if event.recipient.player_id in self._tmp_blocked_users:
                continue
            notification_text = self.get_internal_event_notification_text(event)
            self.send_notification(Notification(event.recipient, notification_text), delay=0.1)
        # handle notifications
        for notification in notifications:
            if notification.target.player_id in self._tmp_blocked_users:
                continue
            self.send_notification(notification)

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

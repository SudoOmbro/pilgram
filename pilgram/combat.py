from typing import Union

from pilgram.classes import Player, Enemy


class CombatContainer:

    def __init__(self, player: Player, enemy: Enemy, helper: Union[Player, None]):
        self.player = player
        self.enemy = enemy
        self.helper = helper

    def fight(self) -> str:
        """ simulate combat between players and enemies. Return battle report in a string. """
        pass  # TODO actually implement the combat

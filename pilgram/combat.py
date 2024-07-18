from typing import Union, List, Dict

from pilgram.classes import Player, Enemy
from pilgram.combat_classes import CombatActor


class CombatContainer:

    def __init__(self, participants: List[Union[Player, Enemy]], helpers: Dict[CombatActor, Union[Player, None]]):
        self.participants = participants
        self.helpers = helpers

    def choose_what_to_do(self):
        pass

    def fight(self) -> str:
        """ simulate combat between players and enemies. Return battle report in a string. """
        fight_log: str = ""
        is_fight_over: bool = False
        while not is_fight_over:
            self.participants.sort(key=lambda a: a.get_initiative())
            actors = self.participants
            for actor in actors:
                pass
        return fight_log

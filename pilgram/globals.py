import json
import logging
from abc import ABC
from typing import Any, Self

from pilgram.utils import PathDict

log = logging.getLogger(__name__)

__INNER_REGEX = r"[^*_`\[\]~\n\s]"
__DESCR_INNER_REGEX = r"[^*_`\[\]~\n]"

PLAYER_NAME_REGEX = rf"^{__INNER_REGEX}{{4,20}}$"
MINIGAME_NAME_REGEX = r"^[A-Za-z]+$"
GUILD_NAME_REGEX = rf"^{__INNER_REGEX}{{2,30}}$"
DESCRIPTION_REGEX = rf"^{__DESCR_INNER_REGEX}{{10,300}}$"
POSITIVE_INTEGER_REGEX = r"^[\d]+$"
YES_NO_REGEX = r"^(?:y|n)$"
SPELL_NAME_REGEX = r"^[A-Za-z]+$"


class Slots:
    HEAD = 0
    CHEST = 1
    LEGS = 2
    ARMS = 3
    PRIMARY = 4
    SECONDARY = 5
    RELIC = 6

    NUMBER = 7

    ARMOR = (HEAD, CHEST, LEGS, ARMS)
    WEAPONS = (PRIMARY, SECONDARY)

    @classmethod
    def get_from_string(cls, string: str) -> int:
        class_vars = {key: value for key, value in vars(cls).items() if not key.startswith('_')}
        return class_vars[string.upper()]


class __GenericGlobalSettings(ABC):
    """read only singleton that holds global variables"""

    _instance = None
    FILENAME: str

    def __init__(self) -> None:
        raise RuntimeError("This class is a singleton, call instance() instead.")

    @classmethod
    def __instance(cls) -> Self:
        if cls._instance is None:
            log.info(f"Creating new {cls.__name__} instance")
            cls._instance = cls.__new__(cls)
            with open(cls.FILENAME) as file:
                cls._instance.dictionary = PathDict(json.load(file))
        return cls._instance

    @classmethod
    def get(cls, path: str, separator: str = ".", default: Any = None) -> Any:
        try:
            return cls.__instance().dictionary.path_get(path, separator)
        except KeyError as e:
            if default is not None:
                return default
            raise e


class __GenericGlobalSettingsLazyLoaded(ABC):
    """
    global settings which only loads a file in memory when it is needed. Useful to avoid using up too much memory.
    """

    FILENAME: str

    @classmethod
    def get(cls, path: str, separator: str = ".", default: Any = None) -> Any:
        try:
            with open(cls.FILENAME) as file:
                dictionary = PathDict(json.load(file))
                return dictionary.path_get(path, separator)
        except KeyError as e:
            if default is not None:
                return default
            raise e


class ContentMeta(__GenericGlobalSettingsLazyLoaded):
    """Contains all info about the world, like default values for players, world name, etc."""

    FILENAME = "content_meta.json"


class GlobalSettings(__GenericGlobalSettings):
    """Contains more technical settings like API keys"""

    FILENAME = "settings.json"

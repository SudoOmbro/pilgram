import json
import logging
from abc import ABC
from typing import Any

from pilgram.utils import PathDict

log = logging.getLogger(__name__)

__INNER_REGEX = r"[A-Za-z0-9\-,.!?;:\(\)\/+=\"'@#$%^&]"

PLAYER_NAME_REGEX = fr"^{__INNER_REGEX}{{4,20}}$"
GUILD_NAME_REGEX = fr"^{__INNER_REGEX}{{2,30}}$"
DESCRIPTION_REGEX = fr"^{__INNER_REGEX}{{10,300}}$"
POSITIVE_INTEGER_REGEX = r"^[\d]+$"
YES_NO_REGEX = r"^(?:y|n)$"


class __GenericGlobalSettings(ABC):
    """ read only singleton that holds global variables """
    _instance = None
    FILENAME: str

    def __init__(self):
        raise RuntimeError("This class is a singleton, call instance() instead.")

    @classmethod
    def __instance(cls):
        if cls._instance is None:
            log.info(f"Creating new {cls.__name__} instance")
            cls._instance = cls.__new__(cls)
            with open(cls.FILENAME) as file:
                cls._instance.dictionary = PathDict(json.load(file))
        return cls._instance

    @classmethod
    def get(cls, path: str, separator: str = ".") -> Any:
        return cls.__instance().dictionary.path_get(path, separator)


class ContentMeta(__GenericGlobalSettings):
    """ Contains all info about the world, like default values for players, world name, etc. """
    FILENAME = "content_meta.json"


class GlobalSettings(__GenericGlobalSettings):
    """ Contains more technical settings like API keys """
    FILENAME = "settings.json"

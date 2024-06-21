import time
from datetime import timedelta
from typing import Union, Dict, Any, List


class IntervalError(Exception):
    pass


LETTERS_TO_INTERVALS: Dict[str, timedelta] = {
    "d": timedelta(days=1),
    "h": timedelta(hours=1),
    "m": timedelta(minutes=1),
    "s": timedelta(seconds=1),
    "w": timedelta(weeks=1)
}


def read_text_file(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()


def read_update_interval(interval_str: str) -> timedelta:
    result = timedelta(seconds=0)
    split_string = interval_str.split(' ')
    for token in split_string:
        letter = token[-1]
        if letter not in LETTERS_TO_INTERVALS:
            raise IntervalError(f"Invalid interval string, '{letter}' not supported")
        interval = LETTERS_TO_INTERVALS[letter]
        result += interval * int(token[:-1])
    return result


def has_recently_accessed_cache(storage: Dict[int, float], user_id: int, cooldown: int):
    if user_id in storage:
        cooldown_expire = storage[user_id]
        if cooldown_expire > time.time():
            return True
    # clear cache of expired values
    keys_to_delete: List[int] = []
    for key, cooldown_expire in storage.items():
        if cooldown_expire <= time.time():
            keys_to_delete.append(key)
    for key in keys_to_delete:
        del storage[key]
    # set cooldown
    storage[user_id] = time.time() + cooldown
    return False


class PathDict:
    """ A dictionary that can only set & get variables using string paths """

    def __init__(self, dictionary: Union[Dict, None] = None):
        self.__dictionary = dictionary if dictionary else {}

    def path_get(self, path: str, separator: str = ".") -> Any:
        keys = path.split(separator)
        rv = self.__dictionary
        for key in keys:
            if key not in rv:
                raise KeyError(f"Could not find key '{key}' in dictionary: {self.__dict__}")
            rv = rv[key]
        return rv

    def path_set(self, path: str, value: Any, separator: str = "."):
        keys = path.split(separator)
        last_key = keys[-1]
        keys = keys[:-1]
        container = self.__dictionary
        for key in keys:
            if key not in container:
                container[key] = {}
            container = container[key]
        container[last_key] = value

    def __str__(self):
        return str(self.__dictionary)


class TempIntCache:

    def __init__(self):
        self.cache: Dict[int, Any] = {}

    def get(self, key: int) -> Union[Any, None]:
        return self.cache.get(key, None)

    def set(self, key: int, value: Any):
        self.cache[key] = value

    def drop(self, key: int):
        del self.cache[key]

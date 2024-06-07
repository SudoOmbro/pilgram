from typing import Union, Dict, Any


def read_text_file(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()


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

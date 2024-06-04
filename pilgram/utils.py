from typing import Union, Dict, Any


class PathDict:

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

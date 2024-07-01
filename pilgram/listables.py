from abc import ABC
from typing import List, Dict

from pilgram.globals import ContentMeta


class Listable(ABC):
    LIST: List = []

    def __init_subclass__(cls, meta_name: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if meta_name and not hasattr(cls, '_initialized'):
            cls.LIST = []
            for listable_json in ContentMeta.get(meta_name):
                cls.LIST.append(cls.create_from_json(listable_json))
            print(f"Loaded {len(cls.LIST)} {meta_name}")
            cls._initialized = True

    @classmethod
    def create_from_json(cls, listable_json: Dict) -> "Listable":
        raise NotImplementedError
from __future__ import annotations

from abc import ABC
from random import Random, randint
from typing import Generic, TypeVar

from pilgram.globals import ContentMeta

T = TypeVar("T")


class Listable(Generic[T], ABC):
    LIST: list[T] = []

    def __init_subclass__(cls, meta_name: str = None, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if meta_name and not hasattr(cls, "_initialized"):
            cls.LIST = []
            for listable_json in ContentMeta.get(meta_name):
                cls.LIST.append(cls.create_from_json(listable_json))
            print(f"Loaded {len(cls.LIST)} {meta_name}")
            cls._initialized = True

    @classmethod
    def create_from_json(cls, listable_json: dict) -> T:
        raise NotImplementedError

    @classmethod
    def get(cls, listable_id: int) -> T:
        return cls.LIST[listable_id]

    @classmethod
    def get_random(cls) -> T:
        return cls.LIST[randint(0, len(cls.LIST) - 1)]

    @classmethod
    def get_random_selection(cls, seed: float, amount: int) -> list[T]:
        rng = Random(seed)
        return rng.sample(cls.LIST, amount)

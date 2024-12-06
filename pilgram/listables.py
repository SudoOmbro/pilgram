from __future__ import annotations

import json
from abc import ABC
from random import Random, randint
from typing import Generic, TypeVar


T = TypeVar("T")
DEFAULT_TAG: str = "default"


class Listable(Generic[T], ABC):
    ALL_ITEMS: list[T]
    LISTS: dict[str, list[T]]

    def __init_subclass__(cls, base_filename: str = None, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if base_filename and not hasattr(cls, "_initialized"):
            filename = f"content/{base_filename}.json"
            items_counter: int = 0
            tags_counter: int = 0
            cls.LISTS = {}
            cls.ALL_ITEMS = []
            items = json.load(open(filename)).get("items", None)
            if not items:
                raise ValueError(f"No items found in {filename}")
            for listable_json in items:
                tag: str = listable_json.get("tag", DEFAULT_TAG)
                if tag not in cls.LISTS:
                    cls.LISTS[tag] = []
                    tags_counter += 1
                item: T = cls.create_from_json(listable_json)
                cls.LISTS[tag].append(item)
                cls.ALL_ITEMS.append(item)
                items_counter += 1
            print(f"Loaded {items_counter} {base_filename}, {tags_counter} tag{"s" if tags_counter > 1 else ""} found")
            cls._initialized = True

    @classmethod
    def create_from_json(cls, listable_json: dict) -> T:
        raise NotImplementedError

    @classmethod
    def get(cls, listable_id: int) -> T:
        return cls.ALL_ITEMS[listable_id]

    @classmethod
    def get_random(cls, tag: str = DEFAULT_TAG) -> T:
        return cls.LISTS[tag][randint(0, len(cls.LISTS[tag]) - 1)]

    @classmethod
    def get_random_selection(cls, seed: float, amount: int, tag: str = DEFAULT_TAG) -> list[T]:
        rng = Random(seed)
        return rng.sample(cls.LISTS[tag], amount)

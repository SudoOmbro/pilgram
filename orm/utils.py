import logging
import time
from typing import Any

__VALUE, __TTL = (0, 1)

log = logging.getLogger(__name__)


def cache_ttl_quick(ttl=3600):
    def decorator(func):
        storage: dict[Any, tuple[Any, float]] = {}

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = args
            # if value is cached and isn't expired then return
            try:
                if key in storage:
                    cache_record = storage[key]
                    if cache_record[__TTL] > time.time():
                        storage[key] = (cache_record[__VALUE], time.time() + ttl)  # refresh ttl
                        return cache_record[__VALUE]
            except Exception as e:
                log.exception(f"Exception when accessing cache_ttl_quick: {e}")
            # calculate value
            result = func(*args, **kwargs)
            # add value to storage and return the resulting value
            storage[key] = (result, time.time() + ttl)
            return result
        return wrapper
    return decorator


def __get_oldest_key(storage: dict, ttl: float):
    try:
        oldest_time = time.time() + (ttl * 2)
        oldest_key = None
        for key, record in storage.items():
            if record[__TTL] < oldest_time:
                oldest_time = record[__TTL]
                oldest_key = key
        return oldest_key
    except Exception as e:
        log.exception(f"Exception while performing __get_oldest_key: {e}")
        return None


def cache_sized_ttl_quick(size_limit=256, ttl=3600):
    def decorator(func):
        storage: dict[Any, tuple[Any, float]] = {}

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = args
            # if value is cached and isn't expired then return
            try:
                if key in storage:
                    cache_record = storage[key]
                    if cache_record[__TTL] > time.time():
                        storage[key] = (cache_record[__VALUE], time.time() + ttl)  # refresh ttl
                        return cache_record[__VALUE]
            except Exception as e:
                log.exception(f"Exception when accessing cache_sized_ttl_quick: {e}")
            # calculate value
            result = func(*args, **kwargs)
            # if cache is full then remove oldest record
            while len(storage) >= size_limit:
                oldest_key = __get_oldest_key(storage, ttl)
                if oldest_key is None:
                    break
                storage.pop(oldest_key)
            # add value to storage and return the resulting value
            storage[key] = (result, time.time() + ttl)
            return result
        return wrapper
    return decorator


def cache_ttl_single_value(ttl=3600):
    def decorator(func):
        value = None
        time_to_live = time.time()

        def wrapper(*args, **kwargs):
            nonlocal value, time_to_live
            if time_to_live > time.time():
                return value
            value = func(*args, **kwargs)
            time_to_live = time.time() + ttl
            return value
        return wrapper
    return decorator

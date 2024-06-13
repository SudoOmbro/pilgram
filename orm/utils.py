import time


def cache(size_limit=0, ttl=0, quick_key_access=False):
    def decorator(func):
        storage = {}
        ttls = {}
        keys = []

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = (*args,)

            # Check if their return value is already known
            if key in storage:
                result = storage[key]
            else:
                # If not, get the result
                result = func(*args, **kwargs)
                storage[key] = result

                # If a ttl has been set, remember when it is going to expire
                if ttl != 0:
                    ttls[key] = time.time() + ttl

                # If quick_key_access is being used, remember the key
                if quick_key_access:
                    keys.append(key)

                # If a size limit has been set, make sure the size hasn't been exceeded
                if size_limit != 0 and len(storage) > size_limit:
                    if quick_key_access:
                        oldest_key = keys[0]
                        del keys[0]
                    else:
                        oldest_key = list(storage.keys())[0]
                    del storage[oldest_key]

            # Check ttls if it is enabled
            if ttl != 0:
                while True:
                    if quick_key_access:
                        oldest_key = keys[0]
                    else:
                        oldest_key = list(storage.keys())[0]

                    # If they key has expired, remove the entry and it's quick access key if quick_key_access=True
                    if ttls[oldest_key] < time.time():
                        del storage[oldest_key]
                        if quick_key_access:
                            del keys[0]
                    else:
                        break

            return result
        return wrapper
    return decorator


# more specialized & optimized versions of the above function


def cache_ttl_quick(ttl=3600):
    def decorator(func):
        storage = {}
        ttls = {}
        keys = []

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = args

            # Check if their return value is already known
            if key in storage:
                result = storage[key]
            else:
                # If not, get the result
                result = func(*args, **kwargs)
                storage[key] = result
                ttls[key] = time.time() + ttl
                keys.append(key)

            while len(keys) != 0:
                oldest_key = keys[0]
                # If they key has expired, remove the entry, and it's quick access key if quick_key_access=True
                if ttls[oldest_key] < time.time():
                    storage.pop(oldest_key)
                    keys.pop(0)
                else:
                    break

            return result
        return wrapper
    return decorator


def cache_sized_quick(size_limit=256):
    def decorator(func):
        storage = {}
        keys = []

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = (*args,)

            # Check if their return value is already known
            if key in storage:
                result = storage[key]
            else:
                # If not, get the result
                result = func(*args, **kwargs)
                storage[key] = result
                keys.append(key)
                # If a size limit has been set, make sure the size hasn't been exceeded
                if len(storage) > size_limit:
                    oldest_key = keys[0]
                    keys.pop(0)
                    storage.pop(oldest_key)

            return result
        return wrapper
    return decorator


def cache_sized_ttl_quick(size_limit=256, ttl=3600):
    def decorator(func):
        storage = {}
        ttls = {}
        keys = []

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = (*args,)

            # Check if their return value is already known
            if key in storage:
                result = storage[key]
            else:
                # If not, get the result
                result = func(*args, **kwargs)
                storage[key] = result
                ttls[key] = time.time() + ttl
                keys.append(key)
                # Make sure the size hasn't been exceeded
                if len(storage) > size_limit:
                    oldest_key = keys[0]
                    keys.pop(0)
                    storage.pop(oldest_key)
            # Check ttls
            while len(keys) != 0:
                oldest_key = keys[0]
                # If they key has expired, remove the entry and it's quick access key
                if ttls[oldest_key] < time.time():
                    storage.pop(oldest_key)
                    keys.pop(0)
                else:
                    break

            return result
        return wrapper
    return decorator


def cache_ttl_single_value(ttl=3600):
    def decorator(func):
        value = None
        time_to_live = time.time()

        def wrapper(*args, **kwargs):
            nonlocal value
            nonlocal time_to_live
            if time_to_live > time.time():
                return value
            value = func(*args, **kwargs)
            time_to_live = time.time() + ttl
            return value
        return wrapper
    return decorator


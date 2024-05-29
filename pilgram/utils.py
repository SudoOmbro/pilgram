def cache(size_limit=0, ttl=0, quick_key_access=False):
    def decorator(func):
        import time
        storage = {}
        ttls = {}
        keys = []

        def wrapper(*args, **kwargs):
            # Generate a key based on arguments being passed
            key = (*args,) + tuple([(k, v) for k, v in kwargs.items()])

            # Check if they return value is already known
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

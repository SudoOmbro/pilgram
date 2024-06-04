import json
import logging

from pilgram.utils import PathDict

log = logging.getLogger(__name__)


class ContentMeta:
    """ singleton instance that holds global variables """
    _instance = None

    def __init__(self):
        raise RuntimeError("This class is a singleton, call instance() instead.")

    @classmethod
    def instance(cls):
        if cls._instance is None:
            log.info('Creating new Globals instance')
            cls._instance = cls.__new__(cls)
            cls._instance.meta = PathDict(json.load(open("content_meta.json")))
        return cls._instance

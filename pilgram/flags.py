from abc import ABC

import numpy as np


_NEXT_FLAG: np.uint32 = np.uint32(1)


class Flag(ABC):
    __FLAG: np.uint32

    def __init_subclass__(cls, **kwargs):
        global _NEXT_FLAG
        super().__init_subclass__()
        cls.__FLAG = _NEXT_FLAG
        _NEXT_FLAG = np.left_shift(_NEXT_FLAG, 1)

    @classmethod
    def set(cls, target: np.uint32) -> np.uint32:
        """ returns the target flag container (a 64 bit int) with the current flag set """
        return np.bitwise_or(cls.__FLAG, target)

    @classmethod
    def unset(cls, target: np.uint32) -> np.uint32:
        return np.bitwise_xor(cls.__FLAG, target)

    @classmethod
    def is_set(cls, target: np.uint32) -> bool:
        return np.bitwise_and(cls.__FLAG, target) == cls.__FLAG

    @classmethod
    def get(cls) -> np.uint32:
        return cls.__FLAG


class HexedFlag(Flag):
    pass

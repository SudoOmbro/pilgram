from abc import ABC

import numpy as np

_NEXT_FLAG: np.uint32 = np.uint32(1)  # we can have a maximum of 32 flags


class Flag(ABC):
    FLAG: np.uint32

    def __init_subclass__(cls, **kwargs) -> None:
        global _NEXT_FLAG
        super().__init_subclass__()
        cls.FLAG = _NEXT_FLAG
        _NEXT_FLAG = np.left_shift(_NEXT_FLAG, 1)

    @classmethod
    def set(cls, target: np.uint32) -> np.uint32:
        """returns the target flag container (a 64 bit int) with the current flag set"""
        return np.bitwise_or(cls.FLAG, target)

    @classmethod
    def unset(cls, target: np.uint32) -> np.uint32:
        return np.bitwise_xor(cls.FLAG, target)

    @classmethod
    def is_set(cls, target: np.uint32) -> bool:
        return np.bitwise_and(cls.FLAG, target) == cls.FLAG

    @classmethod
    def get(cls) -> np.uint32:
        return cls.FLAG

    @classmethod
    def get_empty(cls) -> np.uint32:
        return np.uint32(0)


class HexedFlag(Flag):
    pass  # 1


class CursedFlag(Flag):
    pass  # 2


class AlloyGlitchFlag1(Flag):
    pass  # 3


class AlloyGlitchFlag2(Flag):
    pass  # 4


class AlloyGlitchFlag3(Flag):
    pass  # 5


class LuckFlag1(Flag):
    pass  # 6


class LuckFlag2(Flag):
    pass  # 7


class StrengthBuff(Flag):
    """buff all normal damage (slash, pierce & blunt)"""
    pass  # 8


class OccultBuff(Flag):
    pass  # 9


class FireBuff(Flag):
    pass  # 10


class IceBuff(Flag):
    pass  # 11


class AcidBuff(Flag):
    pass  # 12


class ElectricBuff(Flag):
    pass  # 13


class ForcedCombat(Flag):
    pass  # 14


class MightBuff1(Flag):
    pass  # 15


class MightBuff2(Flag):
    pass  # 16


class MightBuff3(Flag):
    pass  # 17


class SwiftBuff1(Flag):
    pass  # 18


class SwiftBuff2(Flag):
    pass  # 19


class SwiftBuff3(Flag):
    pass  # 20


class Ritual1(Flag):
    pass  # 21


class Ritual2(Flag):
    pass  # 22


class Pity1(Flag):
    pass  # 23


class Pity2(Flag):
    pass  # 24


class Pity3(Flag):
    pass  # 25


class Pity4(Flag):
    pass  # 26


class Pity5(Flag):
    pass  # 27


class DeathwishMode(Flag):
    pass  # 28


class QuestCanceled(Flag):
    pass  # 29


class Catching(Flag):
    pass  # 30


class Raiding(Flag):
    pass  # 31


class InCrypt(Flag):
    pass  # 32


BUFF_FLAGS: tuple[type[Flag], ...] = (
    StrengthBuff,
    OccultBuff,
    FireBuff,
    IceBuff,
    AcidBuff,
    ElectricBuff,
    MightBuff1,
    MightBuff2,
    MightBuff3,
    SwiftBuff1,
    SwiftBuff2,
    SwiftBuff3,
    Ritual1,
    Ritual2
)

PITY_FLAGS: tuple[type[Flag], ...] = (
    Pity1,
    Pity2,
    Pity3,
    Pity4,
    Pity5
)

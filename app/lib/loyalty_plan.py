from enum import IntEnum


class SchemeTier(IntEnum):
    PLL = 1
    BASIC = 2
    PARTNER = 3
    COMING_SOON = 4


class ImageTypes(IntEnum):
    HERO = 0
    BANNER = 1
    OFFER = 2
    ICON = 3
    ASSET = 4
    REFERENCE = 5
    PERSONAL_OFFERS = 6
    PROMOTIONS = 7
    TIER = 8
    ALT_HERO = 9

from enum import IntEnum


class ImageStatus(IntEnum):
    DRAFT = 0
    PUBLISHED = 1


IMAGE_STATUSES = (
    (ImageStatus.DRAFT, "draft"),
    (ImageStatus.PUBLISHED, "published"),
)


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

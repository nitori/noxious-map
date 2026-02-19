from typing import TypedDict, NotRequired, Literal


class DepthPoint(TypedDict):
    x: float
    y: float


class BaseMapObject(TypedDict):
    id: str
    name: str
    originX: float
    originY: float
    updatedAt: int
    depthPoints: NotRequired[list[DepthPoint]]


class MapTile(TypedDict):
    type: str
    x: int
    y: int
    rotation: NotRequired[int]


class MapOpject(TypedDict):
    type: str
    x: int
    y: int
    flipX: bool
    originX: NotRequired[float]
    originY: NotRequired[float]
    signMessage: NotRequired[str]


class Light(TypedDict):
    """
    skipped some fields related to 'flicker' or 'pulse', as we only generate static images.
    """

    id: str
    x: float  # there were some float values
    y: float
    color: str
    intensity: float
    radius: float
    falloff: Literal["exponential", "linear"]
    shape: Literal["soft", "circle"]


class Map(TypedDict):
    """Fields might still be missing. Have to see later."""

    id: str  # uuid
    name: str
    fogDensity: int
    fogEnabled: bool
    fogStyle: Literal["light"]
    height: int
    width: int

    moodlightBrightness: int
    moodlightColor: str
    moodlightContrast: int
    moodlightEnabled: bool
    moodlightLevel: int
    moodlightSaturation: int
    pvp: bool
    rainEnabled: bool
    rainIntensity: int
    rainStyle: Literal["storm"]
    thunderEnabled: bool
    thunderFrequency: int
    updatedAt: int
    version: int

    lights: list[Light]
    mapObjects: list[MapOpject]
    mapTiles: list[MapTile]

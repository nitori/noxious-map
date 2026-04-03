from pydantic import BaseModel, Field


class Position(BaseModel):
    x: int
    y: int


class FPosition(BaseModel):
    x: float
    y: float


class MapTile(Position):
    type: str
    rotation: int = 0


class MapObjectOverrides(Position):
    """This extends the base MapObject from mapObjects.json"""

    type: str
    x: int
    y: int
    originX: float | None = None
    originY: float | None = None
    flipX: bool = False

    frameRate: int | None = None
    frameWidth: int | None = None
    frameHeight: int | None = None

    signMessage: str | None = None
    shopId: str | None = None

    barber: bool = False
    nameTag: str | None = None
    nameTagHeight: int | None = None

    shadow: bool = False
    shadowDirection: int = 0

    itemStorage: bool = False
    npcId: str | None = None
    craftingStationId: str | None = None


class FishingItem(BaseModel):
    itemId: str
    chance: float
    maxAmount: int
    minAmount: int


class Fishing(BaseModel):
    items: list[FishingItem]


class BlockingTile(Position):
    rangedPassthrough: bool = False
    fishing: Fishing | None = None


class Teleport(Position):
    toMap: str
    toX: int
    toY: int
    itemRequired: str | int | None = None
    levelRequired: int = 0
    denyMessage: str | None = None


class Monster(Position):
    monster: str
    amount: int
    # empty str means "infinite" radius
    wanderRadius: int | str | None = None
    respawnTime: int | None = None

    @property
    def respawn_display(self) -> str:
        if self.respawnTime is None:
            return "n/a"

        rt = self.respawnTime / 1000
        if rt >= 60:
            rt = rt / 60
            if rt.is_integer():
                return f"{rt:.0f} minutes"
            return f"{rt / 60:.2f} minutes"
        return f"{rt:.0f} seconds"


class SitTile(Position):
    direction: int


class Light(FPosition):
    id: str
    color: str
    falloff: str
    flicker: bool = False
    flickerSpeed: int = 0
    flickerStrength: int = 0
    intensity: int
    radius: int
    shape: str | None = None
    pulse: bool = False
    pulseSpeed: float = 0.0
    pulseMin: int = 0


class Map(BaseModel):
    id: str
    name: str
    width: int
    height: int
    mapTiles: list[MapTile] = Field(default_factory=list)
    mapObjects: list[MapObjectOverrides] = Field(default_factory=list)
    blockingTiles: list[BlockingTile] = Field(default_factory=list)
    teleports: list[Teleport] = Field(default_factory=list)
    monsters: list[Monster] = Field(default_factory=list)
    sitTiles: list[SitTile] = Field(default_factory=list)
    lights: list[Light] = Field(default_factory=list)
    loopMusic: bool = False
    music: str | None = None
    pvp: bool = False

    moodlightEnabled: bool = False
    moodlightColor: str = ""
    moodlightLevel: int = 0
    moodlightBrightness: int = 0
    moodlightContrast: int = 0
    moodlightSaturation: int = 0

    rainEnabled: bool = False
    rainIntensity: int = 0
    rainStyle: str = ""

    thunderEnabled: bool = False
    thunderFrequency: int = 0

    fogEnabled: bool = False
    fogDensity: int = 0
    fogStyle: str = ""

    snowEnabled: bool = False
    snowIntensity: int = 0
    snowStyle: str = ""

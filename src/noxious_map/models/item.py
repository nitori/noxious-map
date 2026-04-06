from pydantic import BaseModel, Field


class Item(BaseModel):
    id: str
    name: str
    stackable: bool
    hideHair: bool
    disallow_trading: bool

    icon: str | None = None
    drop_icon: str | None = None
    sprite: str | None = None
    sprite_data: dict = Field(default_factory=dict)
    sprite_f: str | None = None
    sprite_data_f: dict = Field(default_factory=dict)
    sfx: str | None = None
    slot: int | None = None
    type: int | None = None
    description: str | None = None
    weight: int = 0
    minLevel: int = 0
    stats: list[dict] = Field(default_factory=list)
    requiredClasses: list[int] = Field(default_factory=list)
    rarity: str | None = None
    range: int | None = None

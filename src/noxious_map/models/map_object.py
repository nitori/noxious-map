from pydantic import BaseModel, Field


class DepthPoint(BaseModel):
    x: float
    y: float


class MapObject(BaseModel):
    id: str
    name: str
    originX: float
    originY: float
    image: str | None = None
    depthPoints: list[DepthPoint] = Field(default_factory=list)
    frameRate: int | None = None
    frameWidth: int | None = None
    frameHeight: int | None = None

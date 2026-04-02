from dataclasses import dataclass


@dataclass
class ObjectMapRanges:
    min_x: int
    min_y: int
    max_x: int
    max_y: int


@dataclass
class Paddings:
    left: int
    top: int
    right: int
    bottom: int

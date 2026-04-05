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

    def __iter__(self):
        # CSS order
        yield self.top
        yield self.right
        yield self.bottom
        yield self.left

    def __str__(self):
        return ",".join(str(val) for val in self)

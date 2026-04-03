from typing import Self
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
from dataclasses import dataclass, field, fields
import textwrap


@dataclass
class TiledWorld:
    version: str
    tiledversion: str
    orientation: str
    renderorder: str
    width: int
    height: int
    tilewidth: int
    tileheight: int
    infinite: bool
    nextlayerid: int
    nextobjectid: int

    tilesets: list[Tileset] = field(default_factory=list)
    layers: list[ObjectLayer] = field(default_factory=list)

    def __repr__(self):
        attrs = []
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, list):
                attrs.append(f"    {f.name}=[")

                sublines = []
                for subvalue in value:
                    sublines.append(f"{subvalue!r},")

                subtext = "\n".join(sublines)
                subtext = textwrap.indent(subtext, " " * 8)
                attrs.extend(subtext.splitlines())

                attrs.append(f"    ],")
            else:
                attrs.append(f"    {f.name}={value!r},")

        return "\n".join([f"{self.__class__.__name__}(", *attrs, ")"])


@dataclass
class ObjectLayer:
    id: int
    name: str
    draworder: str | None = None

    @classmethod
    def from_element(cls, elem: ET.Element) -> Self:
        # <objectgroup draworder="index" id="1" name="Maps">
        draworder = elem.attrib.get("draworder")
        layer_id = int(elem.attrib["id"])
        layer_name = elem.attrib["name"]
        return cls(layer_id, layer_name, draworder)


@dataclass
class Tile:
    """Image tile currently only"""

    id: int
    source: Path
    width: int
    height: int

    def copy(self) -> Tile:
        return Tile(
            id=self.id, source=self.source, width=self.width, height=self.height
        )

    @classmethod
    def from_element(cls, path: Path, elem: ET.Element) -> Self:
        #  <tile id="1">
        #   <image source="../../maps/default/Modern_town.webp" width="3520" height="1897"/>
        #  </tile>

        tile_id = int(elem.attrib["id"])
        image_tag = elem.find("image")
        if image_tag is None:
            raise ValueError(f"Unkown tile {path}")

        source = (path / image_tag.attrib["source"]).resolve()
        width = int(image_tag.attrib["width"])
        height = int(image_tag.attrib["height"])

        return cls(tile_id, source, width, height)

    def to_xml(self, path: Path) -> ET.Element:
        root = ET.Element("tile", {"id": str(self.id)})
        image = ET.Element(
            "image",
            {
                "source": str(self.source.relative_to(path, walk_up=True).as_posix()),
                "width": str(self.width),
                "height": str(self.height),
            },
        )
        root.append(image)
        return root


@dataclass
class Tileset:
    version: str
    tiledversion: str
    name: str
    source: Path
    firstgid: int
    tiles: list[Tile] = field(default_factory=list)

    def find_tile_by_source(self, source: Path) -> Tile | None:
        for tile in self.tiles:
            # Note: on Windows both sources are WindowsPath, which
            # compare true if only the casing mismatches.
            if tile.source == source:
                return tile
        return None

    @classmethod
    def from_element(cls, path: Path, elem: ET.Element) -> Self:
        # <tileset firstgid="1" source="maps.tsx"/>
        firstgid = int(elem.attrib["firstgid"])
        source = path.parent.joinpath(elem.attrib["source"]).resolve()

        tree = ET.parse(source)
        root = tree.getroot()

        tiles = []
        for elem in root:
            if elem.tag != "tile":
                continue

            tile = Tile.from_element(source.parent, elem)
            tiles.append(tile)

        return cls(
            version=root.attrib["version"],
            tiledversion=root.attrib["tiledversion"],
            name=root.attrib["name"],
            source=source,
            firstgid=firstgid,
            tiles=tiles,
        )

    def to_xml(self):
        tile_sizes = self.calculate_tilesizes()
        root = ET.Element(
            "tileset",
            {
                "version": self.version,
                "tiledversion": self.tiledversion,
                "name": self.name,
                "tilewidth": str(tile_sizes[0]),
                "tileheight": str(tile_sizes[1]),
                "tilecount": str(len(self.tiles)),
                "columns": "0",
            },
        )

        root.append(
            ET.Element(
                "grid", {"orientation": "orthogonal", "width": "1", "height": "1"}
            )
        )

        for tile in self.tiles:
            root.append(tile.to_xml(self.source.parent))
        return root

    def write_xml(self):
        root = self.to_xml()
        raw_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        reparsed = minidom.parseString(raw_xml)
        raw_xml = reparsed.toprettyxml(indent=" ", encoding="UTF-8")
        self.source.write_bytes(raw_xml)

    def calculate_tilesizes(self):
        max_width, max_height = 0, 0
        for tile in self.tiles:
            max_width = max(max_width, tile.width)
            max_height = max(max_height, tile.height)
        return max_width, max_height

    def copy(self):
        return Tileset(
            version=self.version,
            tiledversion=self.tiledversion,
            name=self.name,
            source=self.source,
            firstgid=self.firstgid,
            tiles=[t.copy() for t in self.tiles],
        )

    def __repr__(self):
        tiles = [
            "    tiles=[",
            *[f"        {tile}," for tile in self.tiles],
            "    ],",
        ]

        return "\n".join(
            [
                f"{self.__class__.__name__}(",
                f"    version={self.version!r},",
                f"    tiledversion={self.tiledversion!r},",
                f"    name={self.name!r},",
                f"    source={self.source!r},",
                f"    firstgid={self.firstgid!r},",
                *tiles,
                ")",
            ]
        )


def parse_world(file) -> TiledWorld:
    path = Path(file)

    tree = ET.parse(path)
    root = tree.getroot()

    world = TiledWorld(
        version=root.attrib["version"],
        tiledversion=root.attrib["tiledversion"],
        orientation=root.attrib["orientation"],
        renderorder=root.attrib["renderorder"],
        width=int(root.attrib["width"]),
        height=int(root.attrib["height"]),
        tilewidth=int(root.attrib["tilewidth"]),
        tileheight=int(root.attrib["tileheight"]),
        infinite=bool(int(root.attrib["infinite"])),
        nextlayerid=int(root.attrib["nextlayerid"]),
        nextobjectid=int(root.attrib["nextobjectid"]),
    )

    for child in root:
        if child.tag == "tileset":
            tileset = Tileset.from_element(path, child)
            world.tilesets.append(tileset)
        elif child.tag == "objectgroup":
            layer = ObjectLayer.from_element(child)
            world.layers.append(layer)

    return world

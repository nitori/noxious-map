from typing import Self
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
from dataclasses import dataclass, field, fields
import textwrap

NOXIOUS_NS = "https://noxious.gg/2026/tiled"
ET.register_namespace("nox", NOXIOUS_NS)


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
    layers: list[ObjectGroup] = field(default_factory=list)

    def copy(self) -> TiledWorld:
        return TiledWorld(
            version=self.version,
            tiledversion=self.tiledversion,
            orientation=self.orientation,
            renderorder=self.renderorder,
            width=self.width,
            height=self.height,
            tilewidth=self.tilewidth,
            tileheight=self.tileheight,
            infinite=self.infinite,
            nextlayerid=self.nextlayerid,
            nextobjectid=self.nextobjectid,
            tilesets=[ts.copy() for ts in self.tilesets],
            layers=[layer.copy() for layer in self.layers],
        )

    def get_layer_by_name(self, name: str) -> ObjectGroup:
        for layer in self.layers:
            if layer.name == name:
                return layer
        raise ValueError(f"Layer not found: {name!r}")

    def get_tile_by_gid(self, gid: int) -> Tile | None:
        for tileset in sorted(self.tilesets, key=lambda ts: ts.firstgid, reverse=True):
            if gid >= tileset.firstgid:
                tile_id = gid - tileset.firstgid
                return tileset.find_tile_by_id(tile_id)  # if not found, returns None
        return None

    def get_image_object_by_gid(self, gid: int) -> ImageObject | None:
        for layer in self.layers:
            for obj in layer.objects:
                if isinstance(obj, ImageObject):
                    if obj.gid == gid:
                        return obj
        return None

    def write_xml(self, path: Path):
        root = self.to_xml(path)
        raw_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        reparsed = minidom.parseString(raw_xml)
        raw_xml = reparsed.toprettyxml(indent=" ", encoding="UTF-8")
        path.write_bytes(raw_xml)

    def to_xml(self, path: Path) -> ET.Element:
        root = ET.Element(
            "map",
            {
                "version": self.version,
                "tiledversion": self.tiledversion,
                "orientation": self.orientation,
                "renderorder": self.renderorder,
                "width": str(self.width),
                "height": str(self.height),
                "tilewidth": str(self.tilewidth),
                "tileheight": str(self.tileheight),
                "infinite": "1" if self.infinite else "0",
                "nextlayerid": str(self.nextlayerid),
                "nextobjectid": str(self.nextobjectid),
            },
        )

        for tileset in self.tilesets:
            ts_elem = ET.Element(
                "tileset",
                {
                    "firstgid": str(tileset.firstgid),
                    "source": tileset.source.relative_to(path.parent).as_posix(),
                },
            )
            root.append(ts_elem)

        for layer in self.layers:
            root.append(layer.to_xml())

        return root

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


def tryint(value: str | None) -> int | None:
    if value is None:
        return None
    return int(value)


def tryfloat(value: str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def float_str(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


@dataclass
class Property:
    type: str
    value: str

    def copy(self) -> Property:
        return Property(type=self.type, value=self.value)


@dataclass
class TiledObject:
    id: int
    x: float
    y: float

    def copy(self) -> TiledObject:
        return TiledObject(id=self.id, x=self.x, y=self.y)

    @classmethod
    def from_element(cls, elem: ET.Element) -> ImageObject | PointObject:
        if "gid" in elem.attrib:
            return ImageObject.from_element(elem)
        elif elem.find("point") is not None:
            return PointObject.from_element(elem)

        raise NotImplementedError(f"Unsupported object element: {elem}")

    def to_xml(self) -> ET.Element:
        return ET.Element(
            "object",
            {
                "id": str(self.id),
                "x": float_str(self.x),
                "y": float_str(self.y),
            },
        )


@dataclass
class ImageObject(TiledObject):
    width: float | None = None
    height: float | None = None
    gid: int | None = None
    name: str | None = None

    def copy(self) -> ImageObject:
        return ImageObject(
            id=self.id,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            gid=self.gid,
            name=self.name,
        )

    @classmethod
    def from_element(cls, elem: ET.Element) -> Self:
        return cls(
            id=int(elem.attrib["id"]),
            x=float(elem.attrib["x"]),
            y=float(elem.attrib["y"]),
            width=tryfloat(elem.attrib.get("width")),
            height=tryfloat(elem.attrib.get("height")),
            gid=tryint(elem.attrib.get("gid")),
            name=elem.attrib.get("name"),
        )

    def to_xml(self) -> ET.Element:
        root = ET.Element(
            "object",
            {
                "id": str(self.id),
                "name": str(self.name),
                "gid": str(self.gid),
                "x": float_str(self.x),
                "y": float_str(self.y),
            },
        )
        if self.width is not None:
            root.attrib["width"] = float_str(self.width)
        if self.height is not None:
            root.attrib["height"] = float_str(self.height)
        return root


@dataclass
class PointObject(TiledObject):
    properties: dict[str, Property] = field(default_factory=dict)

    def copy(self) -> PointObject:
        return PointObject(
            id=self.id,
            x=self.x,
            y=self.y,
            properties={name: prop.copy() for name, prop in self.properties.items()},
        )

    @classmethod
    def from_element(cls, elem: ET.Element) -> Self:
        properties = {}
        for prop in elem.findall("properties/property"):
            name = prop.attrib["name"]
            type = prop.attrib["type"]
            value = prop.attrib["value"]
            properties[name] = Property(type, value)

        return cls(
            id=int(elem.attrib["id"]),
            x=float(elem.attrib["x"]),
            y=float(elem.attrib["y"]),
            properties=properties,
        )

    def to_xml(self) -> ET.Element:
        root = super().to_xml()
        props = ET.Element("properties")
        for name, prop in self.properties.items():
            props.append(
                ET.Element(
                    "property",
                    {
                        "name": name,
                        "type": prop.type,
                        "value": prop.value,
                    },
                )
            )
        root.append(props)
        root.append(ET.Element("point"))
        return root


@dataclass
class ObjectGroup:
    id: int
    name: str
    draworder: str | None = None
    objects: list[TiledObject] = field(default_factory=list)

    def copy(self) -> ObjectGroup:
        return ObjectGroup(
            id=self.id,
            name=self.name,
            draworder=self.draworder,
            objects=[obj.copy() for obj in self.objects],
        )

    @classmethod
    def from_element(cls, elem: ET.Element) -> Self:
        # <objectgroup draworder="index" id="1" name="Maps">
        draworder = elem.attrib.get("draworder")
        layer_id = int(elem.attrib["id"])
        layer_name = elem.attrib["name"]

        objects = []
        for obj_elem in elem:
            objects.append(TiledObject.from_element(obj_elem))

        return cls(layer_id, layer_name, draworder, objects)

    def to_xml(self):
        root_attrs = {}
        if self.draworder is not None:
            root_attrs["draworder"] = self.draworder
        root_attrs["id"] = str(self.id)
        root_attrs["name"] = str(self.name)

        root = ET.Element("objectgroup", root_attrs)
        for obj in self.objects:
            root.append(obj.to_xml())
        return root

    def __repr__(self):
        attrs = []
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, list):
                attrs.append(f"    {f.name}=[")
                for obj in value:
                    attrs.append(f"        {obj},")
                attrs.append("    ],")
            else:
                attrs.append(f"    {f.name}={value!r},")

        return "\n".join([f"{self.__class__.__name__}(", *attrs, ")"])


@dataclass
class Tile:
    """Image tile currently only"""

    id: int
    source: Path
    width: int
    height: int
    noxious_id: str | None = None

    def copy(self) -> Tile:
        return Tile(
            id=self.id,
            source=self.source,
            width=self.width,
            height=self.height,
            noxious_id=self.noxious_id,
        )

    @classmethod
    def from_element(cls, path: Path, elem: ET.Element) -> Self:
        #  <tile id="1" nox:id="abc">
        #   <image source="../../maps/default/Modern_town.webp" width="3520" height="1897"/>
        #  </tile>

        tile_id = int(elem.attrib["id"])
        image_tag = elem.find("image")
        if image_tag is None:
            raise ValueError(f"Unkown tile {path}")

        source = (path / image_tag.attrib["source"]).resolve()
        width = int(image_tag.attrib["width"])
        height = int(image_tag.attrib["height"])
        noxious_id = elem.attrib.get(f"{{{NOXIOUS_NS}}}id")

        return cls(
            id=tile_id, source=source, width=width, height=height, noxious_id=noxious_id
        )

    def to_xml(self, path: Path) -> ET.Element:
        tile_attrs = {
            "id": str(self.id),
        }
        if self.noxious_id is not None:
            tile_attrs[f"{{{NOXIOUS_NS}}}id"] = self.noxious_id
        root = ET.Element("tile", tile_attrs)
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

    def find_tile_by_id(self, id: int) -> Tile | None:
        for tile in self.tiles:
            if tile.id == id:
                return tile
        return None

    def find_tile_by_source(self, source: Path) -> Tile | None:
        for tile in self.tiles:
            # Note: on Windows both sources are WindowsPath, which
            # compare true if only the casing mismatches.
            if tile.source == source:
                return tile
        return None

    def find_tile_by_noxious_id(self, noxious_id: str) -> Tile | None:
        for tile in self.tiles:
            if tile.noxious_id is not None and tile.noxious_id == noxious_id:
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
            layer = ObjectGroup.from_element(child)
            world.layers.append(layer)

    return world

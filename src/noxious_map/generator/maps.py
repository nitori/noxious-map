from random import Random
from functools import cmp_to_key
from typing import Generator, TypedDict, Collection
import re
import shutil
from pathlib import Path

from PIL import Image

from noxious_map.models import Map, MapObject, Item
from noxious_map.models.map import Teleport
from noxious_map.types import Paddings, ObjectMapRanges
from noxious_map.utils import compare_depth_sort, nc, progress
from noxious_map.tiled import (
    parse_world,
    Tile,
    TiledObject,
    ImageObject,
    PointObject,
    Property,
)
from .base import BaseGenerator

random = Random()
random.seed(123)


class Telepad(TypedDict):
    src_positions: list[tuple[int, int]]
    src_center: tuple[int, int]
    dest_map: str
    dest_positions: list[tuple[int, int]]
    dest_center: tuple[int, int]


def normalize_name(name: str) -> str:
    return re.sub(r'[/\\ <>":|?*]', "_", name)


class MapGenerator(BaseGenerator):
    def generate(self):
        print("generating maps...")
        self.load_maps()
        print("Done!")

    def load_maps(self):
        # loading once early on to check if file can be loaded
        old_world = parse_world(self.tiled_dir / "world.tmx")
        orig_tileset = old_world.tilesets[0]
        tileset = orig_tileset.copy()
        tileset.tiles = []

        new_world = old_world.copy()
        new_world.nextobjectid = 1
        map_objects = new_world.get_layer_by_name("Maps")
        point_objects = new_world.get_layer_by_name("Connections")
        original_map_order = [
            obj.properties["tileMapId"].value for obj in map_objects.objects
        ]
        map_objects.objects = []
        point_objects.objects = []

        max_tile_id = max(t.id for t in orig_tileset.tiles) if orig_tileset.tiles else 0

        # load items data
        items_data_raw = self.load("data/items.json")
        items_data: dict[str | int, Item] = {
            item["id"]: Item.model_validate(item, extra="forbid")
            for item in items_data_raw
        }

        tile_maps_raw = self.load("data/maps.json")
        tile_maps: list[Map] = []
        id_map_tile_map: dict[str, Map] = {}
        for tile_map_raw in tile_maps_raw:
            loaded_map = Map.model_validate(tile_map_raw, extra="forbid")
            tile_maps.append(loaded_map)
            id_map_tile_map[loaded_map.id] = loaded_map

        missing_teleport_destination_maps = []

        for tile_map, img, paddings, default_filepath in self.generate_map_images(
            tile_maps
        ):
            tile = orig_tileset.find_tile_by_noxious_id(tile_map.id)
            if tile is None:
                tile = orig_tileset.find_tile_by_source(default_filepath)

            if tile:
                tile = tile.copy()
            else:
                print()
                print(f"Tile not found: {tile_map.id}  {tile_map.name}")

            if tile is None:
                max_tile_id += 1
                tile = Tile(
                    id=max_tile_id,
                    source=default_filepath,
                    width=img.width,
                    height=img.height,
                )

            tile.properties["noxious_id"] = Property(type="string", value=tile_map.id)
            tile.properties["paddings"] = Property(type="string", value=str(paddings))
            tile.properties["baseSize"] = Property(
                type="string", value=str(self.get_base_map_size(tile_map))
            )
            tile.properties["mapWidth"] = Property(
                type="int", value=str(tile_map.width)
            )
            tile.properties["mapHeight"] = Property(
                type="int", value=str(tile_map.height)
            )
            tile.source = default_filepath
            tile.width = img.width
            tile.height = img.height
            tileset.tiles.append(tile)

            old_object = old_world.get_image_object_by_tile_map_id(tile_map.id)
            if old_object:
                obj = old_object.copy()
                obj.id = new_world.nextobjectid
                new_world.nextobjectid += 1
            else:
                obj = ImageObject(
                    id=new_world.nextobjectid,
                    x=0.0,
                    y=0.0,
                    width=None,
                    height=None,
                    gid=tileset.firstgid + tile.id,
                    name=tile_map.name,
                )
                new_world.nextobjectid += 1

            obj.width = tile.width
            obj.height = tile.height
            obj.properties["tileMapId"] = Property(type="string", value=tile_map.id)
            obj.properties["tileMapName"] = Property(type="string", value=tile_map.name)

            map_objects.objects.append(obj)
            # for group in self.group_teleport_islands(tile_map.teleports):
            for tp in tile_map.teleports:
                dest_tile_map = id_map_tile_map.get(tp.toMap)
                if dest_tile_map is None:
                    missing_teleport_destination_maps.append((tile_map, tp))
                    continue
                src_x, src_y = tp.x, tp.y
                local_xy = self.get_tile_center(src_x, src_y, tile_map, paddings)
                world_x, world_y = self.to_tiled_image_position(
                    local_xy, (obj.x, obj.y), img.size
                )
                pobject = PointObject(
                    name=f"To: {dest_tile_map.name}",
                    id=new_world.nextobjectid,
                    x=world_x,
                    y=world_y,
                    properties={
                        "attachedTo": Property(type="object", value=str(obj.id)),
                        "srcMapId": Property(type="string", value=tile_map.id),
                        "srcMapName": Property(type="string", value=tile_map.name),
                        "srcPos": Property(type="string", value=str((tp.x, tp.y))),
                        "destMapId": Property(type="string", value=dest_tile_map.id),
                        "destMapName": Property(
                            type="string", value=dest_tile_map.name
                        ),
                        "destPos": Property(type="string", value=str((tp.toX, tp.toY))),
                    },
                )
                new_world.nextobjectid += 1

                if tp.itemRequired is not None:
                    pobject.properties["itemRequired"] = Property(
                        type="string", value=str(tp.itemRequired)
                    )
                    if tp.itemRequired in items_data:
                        item = items_data[tp.itemRequired]
                        pobject.properties["itemName"] = Property(
                            type="string", value=str(item.name)
                        )
                if tp.denyMessage is not None:
                    pobject.properties["denyMessage"] = Property(
                        type="string", value=str(tp.denyMessage)
                    )

                point_objects.objects.append(pobject)

        for tm, tp in missing_teleport_destination_maps:
            print(
                f"[{tm.id}] {tm.name} {(tp.x, tp.y)} missing teleport map: {tp.toMap}, at {(tp.toX, tp.toY)}"
            )

        tileset.tiles.sort(key=lambda t: t.id)
        tileset.write_xml()

        def _sorter(obj: TiledObject) -> int | float:
            noxid = obj.properties.get("tileMapId")
            if noxid is not None and noxid.value in original_map_order:
                return original_map_order.index(noxid.value)
            return float("inf")

        map_objects.objects.sort(key=_sorter)

        new_world.write_xml(self.tiled_dir / "world.tmx")

    @staticmethod
    def to_tiled_image_position(
        local_xy: tuple[float, float], image_xy: tuple[float, float], image_wh
    ) -> tuple[float, float]:
        local_x, local_y = local_xy
        image_x, image_y = image_xy
        image_width, image_height = image_wh
        dx = local_x - image_width / 2
        dy = local_y - image_height
        world_x = image_x + dx / 2 + dy
        world_y = image_y - dx / 2 + dy
        return world_x, world_y

    @staticmethod
    def get_tile_center(
        tile_x: int, tile_y: int, tile_map: Map, paddings
    ) -> tuple[int, int]:
        """Convert a tile grid position (column, row) to pixel coordinates
        on the final padded image, exactly at the center of that isometric tile.

        This matches your base map size calculation and the isometric 64×32 layout.
        """
        # Position of the top-center of the isometric diamond (relative to base map)
        base_x = (tile_x - tile_y) * 32 + tile_map.height * 32
        base_y = (tile_x + tile_y) * 16

        # Move down 16 px to reach the true center of the 64×32 tile
        center_x = base_x
        center_y = base_y + 16

        # Add the padding offsets so the coordinates are correct on the final img
        pixel_x = paddings.left + center_x
        pixel_y = paddings.top + center_y

        return pixel_x, pixel_y

    def generate_map_images(
        self, tile_maps: list[Map]
    ) -> Generator[tuple[Map, Image.Image, Paddings, Path]]:
        map_folder = self.out_dir / "maps"
        if map_folder.exists():
            shutil.rmtree(map_folder)
        map_folder.mkdir(parents=True, exist_ok=True)

        for tile_map in progress(tile_maps):
            # if tile_map.id not in ("xf07cohu0dqymrh", "a2f5vu1iw2okj2o"):
            #     continue

            # if i >= 5:
            #     print("")
            #     print("TEMPORARY BREAK")
            #     break

            map_im = self.generate_base_map(tile_map)
            obj_im, paddings = self.generate_map_objects(tile_map)

            extended_map = Image.new("RGBA", obj_im.size, (0, 0, 0, 0))
            extended_map.alpha_composite(map_im, (paddings.left, paddings.top))
            extended_map.alpha_composite(obj_im)

            name = normalize_name(tile_map.id)
            filename = f"{name}.webp"

            folders: list[tuple[str, int | tuple[float, float]]] = [
                ("default", 1),
                ("low", 2),
                ("small", 3),
                ("tiny", 4),
                ("micro", 5),
                ("fixed", (256, 256)),
            ]
            for folder, resize in folders:
                filepath = map_folder / folder / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                if filepath.exists():
                    raise FileExistsError(str(filepath))

                if resize == 1:
                    extended_map.save(filepath, quality=75)
                elif isinstance(resize, tuple):
                    tmp_map = extended_map.copy()
                    tmp_map.thumbnail(resize, Image.Resampling.BICUBIC)
                    tmp_map.save(filepath, quality=75)
                else:
                    w, h = extended_map.size
                    tmp_map = extended_map.resize(
                        (max(1, w // resize), max(1, h // resize)),
                        Image.Resampling.BICUBIC,
                    )
                    tmp_map.save(filepath, quality=75)

            default_filepath = map_folder / "default" / filename
            yield tile_map, extended_map, paddings, default_filepath

    @staticmethod
    def group_adjacent(
        points: Collection[tuple[int, int]],
    ) -> list[list[tuple[int, int]]]:
        # AI generated
        """Group 8-connected points into islands. Duplicates removed automatically."""
        if not points:
            return []
        positions = set(points)
        dirs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        visited: set[tuple[int, int]] = set()
        groups: list[list[tuple[int, int]]] = []
        for start in positions:
            if start in visited:
                continue
            group: list[tuple[int, int]] = []
            stack = [start]
            visited.add(start)
            while stack:
                x, y = stack.pop()
                group.append((x, y))
                for dx, dy in dirs:
                    n = (x + dx, y + dy)
                    if n in positions and n not in visited:
                        visited.add(n)
                        stack.append(n)
            groups.append(group)
        return groups

    @staticmethod
    def _get_center(points: list[tuple[int, int]]) -> tuple[int, int]:
        # AI generated
        """Most central tile in the group."""
        if len(points) == 1:
            return points[0]
        sx = sum(p[0] for p in points)
        sy = sum(p[1] for p in points)
        n = len(points)
        cx, cy = sx / n, sy / n
        return min(points, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)

    def group_teleport_islands(self, teleports: list[Teleport]) -> list[Telepad]:
        # AI generated
        """Super-simple version. Returns list of dicts, one per logical portal group."""
        if not teleports:
            return []

        from collections import defaultdict

        by_map: dict[str, list[Teleport]] = defaultdict(list)
        for tp in teleports:
            by_map[tp.toMap].append(tp)

        result: list[Telepad] = []
        for dmap, tps in by_map.items():
            mapping = {(tp.x, tp.y): (tp.toX, tp.toY) for tp in tps}
            dest_groups = self.group_adjacent(mapping.values())

            for dg in dest_groups:
                dset = set(dg)
                src_pts = [s for s, d in mapping.items() if d in dset]
                for sg in self.group_adjacent(src_pts):
                    dg_this = list({mapping[s] for s in sg})  # unique dests
                    result.append(
                        {
                            "src_positions": sg,
                            "src_center": self._get_center(sg),
                            "dest_map": dmap,
                            "dest_positions": dg_this,
                            "dest_center": self._get_center(dg_this),
                        }
                    )
        return result

    @staticmethod
    def get_base_map_size(tile_map: Map) -> tuple[int, int]:
        width = tile_map.width
        height = tile_map.height
        size = (width + height) * 32, (width + height) * 16
        return size

    def generate_base_map(self, tile_map: Map) -> Image.Image:
        tiles_texture_dir = self.bundle_dir / "textures" / "mapTiles"
        size = self.get_base_map_size(tile_map)
        map_im = Image.new("RGBA", size, (0, 0, 0, 0))
        rows = tile_map.height

        tile_images = {}

        for tile in tile_map.mapTiles:
            stem = tile.type
            if stem not in tile_images:
                tiles_texture_filename = tiles_texture_dir / f"{stem}.png"
                if not tiles_texture_filename.exists():
                    raise ValueError(f"missing tile texture: {tiles_texture_filename}")

                im = Image.open(tiles_texture_filename)
                im = im.convert("RGBA")
                tile_images[stem] = im

            grid_x = tile.x
            grid_y = tile.y
            pos_x = (grid_x - grid_y) * 32 - 32 + (rows * 32)
            pos_y = (grid_x + grid_y) * 16
            map_im.alpha_composite(tile_images[stem], (pos_x, pos_y))

        return map_im

    def generate_map_objects(self, tile_map: Map) -> tuple[Image.Image, Paddings]:
        obj_texture_dir = self.bundle_dir / "textures" / "mapObjects"
        rows = tile_map.height
        base_width, base_height = self.get_base_map_size(tile_map)

        obj_images = {}

        map_objects_list = self.load("data/mapObjects.json")
        map_objects: dict[str, MapObject] = {}
        for map_object in map_objects_list:
            map_objects[map_object["id"]] = MapObject.model_validate(
                map_object, extra="forbid"
            )

        objects_to_draw = []

        ranges = ObjectMapRanges(
            min_x=0,
            min_y=0,
            max_x=base_width,
            max_y=base_height,
        )

        first_print = True
        for obj in tile_map.mapObjects:
            id = obj.type
            try:
                base_obj = map_objects[id]
            except KeyError:
                if first_print:
                    print()
                first_print = False
                print(
                    f"Map object {id!r} is missing but used in map {tile_map.id} ({tile_map.name!r})"
                )
                continue

            if id not in obj_images:
                assert base_obj.image is not None
                _, _, base_image_ext = base_obj.image.rpartition(".")
                obj_texture_file = obj_texture_dir / f"{id}.{base_image_ext}"
                if not obj_texture_file.exists():
                    print(
                        f"Map object {id!r} is missing tile object texture: {obj_texture_file.name} ({tile_map.name!r})"
                    )
                    continue

                frame_width = base_obj.frameWidth
                frame_height = base_obj.frameHeight

                obj_im = Image.open(obj_texture_file)
                obj_im = obj_im.convert("RGBA")

                if frame_width is not None and frame_height is not None:
                    obj_im = obj_im.crop((0, 0, frame_width, frame_height))

                obj_images[id] = obj_im

            obj_im: Image.Image = obj_images[id]
            flipped = obj.flipX
            if flipped:
                obj_im = obj_im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            origin_screen_x = ((obj.x - obj.y) * 32) + (rows * 32)
            origin_screen_y = (obj.x + obj.y + 1) * 16

            pos_x = round(
                origin_screen_x - (nc(obj.originX, base_obj.originX) * obj_im.width)
            )
            pos_y = round(
                origin_screen_y - (nc(obj.originY, base_obj.originY) * obj_im.height)
            )

            bbox = (pos_x, pos_y, pos_x + obj_im.width, pos_y + obj_im.height)

            obj_right = pos_x + obj_im.width
            obj_bottom = pos_y + obj_im.height
            ranges.min_x = min(ranges.min_x, pos_x)
            ranges.min_y = min(ranges.min_y, pos_y)
            ranges.max_x = max(ranges.max_x, obj_right)
            ranges.max_y = max(ranges.max_y, obj_bottom)

            objects_to_draw.append(
                {
                    "obj": obj,
                    "base_obj": base_obj,
                    "bbox": bbox,
                    "im": obj_im,
                    "pos": (pos_x, pos_y),
                    "origin_screen_x": origin_screen_x,
                    "origin_screen_y": origin_screen_y,
                }
            )

        objects_to_draw.sort(key=cmp_to_key(compare_depth_sort))

        paddings = Paddings(
            left=max(0, -ranges.min_x),
            top=max(0, -ranges.min_y),
            right=max(0, ranges.max_x - base_width),
            bottom=max(0, ranges.max_y - base_height),
        )

        canvas_width = base_width + paddings.left + paddings.right
        canvas_height = base_height + paddings.top + paddings.bottom
        obj_map_im = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

        for obj in objects_to_draw:
            x, y = obj["pos"]
            obj_map_im.alpha_composite(obj["im"], (paddings.left + x, paddings.top + y))

        return obj_map_im, paddings

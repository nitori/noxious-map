from functools import cmp_to_key
import re
import shutil

from PIL import Image

from noxious_map.models import Map, MapObject
from noxious_map.types import Paddings, ObjectMapRanges
from noxious_map.utils import compare_depth_sort, nc
from .base import BaseGenerator


class MapGenerator(BaseGenerator):
    def generate(self):
        print("generate maps")
        print(self.bundle_dir)
        print(self.out_dir)
        print(self.root)

        self.load_maps()

    def load_maps(self):
        tile_maps = self.load("data/maps.json")

        map_of_maps: dict[str, Map] = {}

        map_folder = self.out_dir / "maps"
        shutil.rmtree(map_folder)
        map_folder.mkdir(parents=True, exist_ok=True)

        for tile_map in tile_maps:
            loaded_map = Map.model_validate(tile_map, extra="forbid")
            assert loaded_map.id not in map_of_maps, "map id already exists"
            map_of_maps[loaded_map.id] = loaded_map

        for map_id, tile_map in map_of_maps.items():
            print(f'Teleports of {tile_map.name} [{map_id}]:')
            for tp in tile_map.teleports:
                if tp.toMap in map_of_maps:
                    other_map = map_of_maps[tp.toMap]
                    print(f'  - {other_map.name} [{other_map.id}]')
                else:
                    print(f'  - missing: {tp.toMap}')

            map_im = self.generate_base_map(tile_map)
            obj_im, paddings = self.generate_map_objects(tile_map)

            extended_map = Image.new("RGBA", obj_im.size, (0, 0, 0, 0))
            extended_map.alpha_composite(map_im, (paddings.left, paddings.top))
            extended_map.alpha_composite(obj_im)

            name = tile_map.name
            name = re.sub(r'[/\\ <>":|?*]', "_", name)
            filename = f"{name}.webp"

            folders = [["default", 1], ["low", 2], ["small", 3], ["tiny", 4], ["micro", 5]]
            for folder, resize in folders:
                filepath = map_folder / folder / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                if filepath.exists():
                    raise FileExistsError(str(filepath))

                if resize == 1:
                    extended_map.save(filepath, quality=75)
                else:
                    w, h = extended_map.size
                    tmp_map = extended_map.resize(
                        (max(1, w // resize), max(1, h // resize)), Image.Resampling.BICUBIC
                    )
                    tmp_map.save(filepath, quality=75)

                print(f"Saved {filepath}")

    def compine_maps(self):
        pass

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
            map_objects[map_object["id"]] = MapObject.model_validate(map_object, extra="forbid")

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
                    f"Map object {id!r} is missing but used in map {tile_map['id']} ({tile_map['name']!r})"
                )
                continue

            if id not in obj_images:
                _, _, base_image_ext = base_obj.image.rpartition(".")
                obj_texture_file = obj_texture_dir / f"{id}.{base_image_ext}"
                if not obj_texture_file.exists():
                    print(
                        f"Map object {id!r} is missing tile object texture: {obj_texture_file.name} ({tile_map['name']!r})"
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
                origin_screen_x
                - (nc(obj.originX, base_obj.originX) * obj_im.width)
            )
            pos_y = round(
                origin_screen_y
                - (nc(obj.originY, base_obj.originY) * obj_im.height)
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

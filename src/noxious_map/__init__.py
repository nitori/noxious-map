from dataclasses import dataclass
from pathlib import Path
import shutil
import json
from functools import cmp_to_key

from PIL import Image

from .downloader import download_data
from .generator import BaseGenerator, MobGenerator
from .types import Map, BaseMapObject
from .utils import cmp_func


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


class DataFetcher:
    def __init__(self, base_path: Path):
        self._here = base_path

    def load_json(self, data_file: str):
        file_path = self._here / "bundle" / "data" / data_file
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def get_base_map_size(self, tile_map: Map) -> tuple[int, int]:
        width = tile_map["width"]
        height = tile_map["height"]
        size = (width + height) * 32, (width + height) * 16
        return size

    def generate_base_map(self, tile_map: Map) -> Image.Image:
        tiles_texture_dir = self._here / "bundle" / "textures" / "mapTiles"
        size = self.get_base_map_size(tile_map)
        map_im = Image.new("RGBA", size, (0, 0, 0, 0))
        rows = tile_map["height"]

        tile_images = {}

        for tile in tile_map["mapTiles"]:
            stem = tile["type"]
            if stem not in tile_images:
                tiles_texture_filename = tiles_texture_dir / f"{stem}.png"
                if not tiles_texture_filename.exists():
                    raise ValueError(f"missing tile texture: {tiles_texture_filename}")

                im = Image.open(tiles_texture_filename)
                im = im.convert("RGBA")
                tile_images[stem] = im

            grid_x = tile["x"]
            grid_y = tile["y"]
            pos_x = (grid_x - grid_y) * 32 - 32 + (rows * 32)
            pos_y = (grid_x + grid_y) * 16
            map_im.alpha_composite(tile_images[stem], (pos_x, pos_y))

        return map_im

    def generate_map_objects(self, tile_map: Map) -> tuple[Image.Image, Paddings]:
        obj_texture_dir = self._here / "bundle" / "textures" / "mapObjects"
        rows = tile_map["height"]
        base_width, base_height = self.get_base_map_size(tile_map)

        obj_images = {}

        map_objects_list = self.load_json("mapObjects.json")
        map_objects: dict[str, BaseMapObject] = {}
        for map_object in map_objects_list:
            map_objects[map_object["id"]] = map_object

        objects_to_draw = []

        ranges = ObjectMapRanges(
            min_x=0,
            min_y=0,
            max_x=base_width,
            max_y=base_height,
        )

        first_print = True
        for obj in tile_map["mapObjects"]:
            id = obj["type"]
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
                base_image_name = base_obj.get("image", "foo.png")
                _, _, base_image_ext = base_image_name.rpartition(".")
                obj_texture_file = obj_texture_dir / f"{id}.{base_image_ext}"
                if not obj_texture_file.exists():
                    print(
                        f"Map object {id!r} is missing tile object texture: {obj_texture_file.name} ({tile_map['name']!r})"
                    )
                    continue

                frame_width = base_obj.get("frameWidth")
                frame_height = base_obj.get("frameHeight")

                obj_im = Image.open(obj_texture_file)
                obj_im = obj_im.convert("RGBA")

                if frame_width is not None and frame_height is not None:
                    obj_im = obj_im.crop((0, 0, frame_width, frame_height))

                obj_images[id] = obj_im

            obj_im: Image.Image = obj_images[id]
            flipped = obj.get("flipX", False)
            if flipped:
                obj_im = obj_im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            origin_screen_x = ((obj["x"] - obj["y"]) * 32) + (rows * 32)
            origin_screen_y = (obj["x"] + obj["y"] + 1) * 16

            pos_x = round(
                origin_screen_x
                - (obj.get("originX", base_obj["originX"]) * obj_im.width)
            )
            pos_y = round(
                origin_screen_y
                - (obj.get("originY", base_obj["originY"]) * obj_im.height)
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

        objects_to_draw.sort(key=cmp_to_key(cmp_func))

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


def main(here: Path):
    download_data(here)

    generators: list[BaseGenerator] = [
        MobGenerator(here),
    ]

    # noinspection PyShadowingNames
    for generator in generators:
        generator.generate()

    map_folder = here / "html" / "maps"
    shutil.rmtree(map_folder)
    map_folder.mkdir(parents=True, exist_ok=True)

    gen = DataFetcher(here)
    maps: list[Map] = gen.load_json("maps.json")

    metadata = []
    map_ids = {}

    for i, tile_map in enumerate(maps):
        print(f"\r{(i + 1) * 100 / len(maps):.1f}%", end="")
        map_im = gen.generate_base_map(tile_map)
        obj_im, paddings = gen.generate_map_objects(tile_map)

        extended_map = Image.new("RGBA", obj_im.size, (0, 0, 0, 0))
        extended_map.alpha_composite(map_im, (paddings.left, paddings.top))
        extended_map.alpha_composite(obj_im)

        name = tile_map["name"]
        name = name.replace("/", "_")
        name = name.replace("\\", "_")
        name = name.replace(" ", "_")
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

        metadata.append(
            {
                "id": tile_map["id"],
                "name": tile_map["name"],
                "file": filename,
                "size": [extended_map.width, extended_map.height],
                "paddings": [
                    paddings.top,
                    paddings.right,
                    paddings.bottom,
                    paddings.left,
                ],
                "pos": [0, -25_000],
                "columns": tile_map["width"],
                "rows": tile_map["height"],
            }
        )
        map_ids[tile_map["id"]] = tile_map["name"]
    print()

    metadata.sort(key=lambda item: item["id"].casefold())
    map_ids = dict(sorted(map_ids.items()))

    old_map_ids_file = map_folder.parent / "js" / "map-ids-old.json"
    old_map_ids = json.loads(old_map_ids_file.read_text(encoding="utf-8"))
    rev_old_map_ids = {}
    for id, name in old_map_ids.items():
        assert name not in rev_old_map_ids, f"{name} already in rev_old_map_ids"
        rev_old_map_ids[name] = id

    def find_old_id(newid: str):
        map_name = map_ids[newid]
        return rev_old_map_ids.get(map_name)

    metadata_file = map_folder.parent / "js" / "metadata.json"
    with metadata_file.open("r", encoding="utf-8") as f:
        old_metadata = json.load(f)
        remap_metadata = {old_md["id"]: old_md for old_md in old_metadata}

    for md in metadata:
        old_md = remap_metadata.get(md["id"], None)
        if old_md is None:
            old_id = find_old_id(md["id"])
            old_md = remap_metadata.get(old_id, None)
        if old_md:
            md["pos"] = old_md["pos"]
            if md["pos"] == [0, 0]:
                md["pos"] = [0, -25_000]

    with metadata_file.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")

    map_ids_file = map_folder.parent / "js" / "map-ids.json"
    with map_ids_file.open("w", encoding="utf-8") as f:
        json.dump(map_ids, f, indent=2)
        f.write("\n")

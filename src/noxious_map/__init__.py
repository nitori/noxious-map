from dataclasses import dataclass
from pathlib import Path
import shutil
import zipfile
import json
import random
import base64
from functools import cmp_to_key
import hashlib
import textwrap
from html import escape

import requests
from PIL import Image

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


def checksum_file(path: Path | str) -> str:
    with open(path, "rb") as f:
        digest = hashlib.md5()
        for chunk in iter(lambda: f.read(1 << 14), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


class DataFetcher:
    def __init__(self, base_path: Path):
        self._here = base_path

    def update_data(self):
        filename = self._here / "bundle.zip"
        bundle_dir = self._here / "bundle"
        url = "https://server.noxious.gg/data/bundle"

        r = requests.head(url)
        checksum = r.headers["Etag"].strip("\"'").lower()

        if checksum != checksum_file(filename):
            r = requests.get(url, stream=True)

            print("downloading...")
            with filename.open("wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        else:
            print("skipping download.")

        print("unzipping...")
        shutil.rmtree(bundle_dir)
        with zipfile.ZipFile(filename, "r") as zf:
            zf.extractall(bundle_dir)

        print("formatting json files in bundle/data/ ...")
        for json_file in (bundle_dir / "data").glob("*.json"):
            with json_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            rval = base64.urlsafe_b64encode(random.randbytes(12)).decode("ascii")
            tmp_json_file = json_file.with_stem(f"{json_file.stem}_{rval}")

            with tmp_json_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            shutil.copyfile(tmp_json_file, json_file)
            tmp_json_file.unlink()

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
                print(f'Map object {id!r} is missing but used in map {tile_map['id']} ({tile_map['name']!r})')
                continue

            if id not in obj_images:
                obj_texture_file = obj_texture_dir / f"{id}.png"
                if not obj_texture_file.exists():
                    print(f'Map object {id!r} is missing tile object texture: {obj_texture_file.name} ({tile_map['name']!r})')
                    continue

                obj_im = Image.open(obj_texture_file)
                obj_im = obj_im.convert("RGBA")
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

    def generate_mob_drop_list(self):
        bundle_dir = self._here / "bundle"
        data_dir = bundle_dir / 'data'
        sprites_dir = bundle_dir / 'textures' / 'sprites'

        monsters_file = data_dir / 'monsters.json'

        html_dir = self._here / 'html'
        out_sprites_dir = html_dir / 'sprites'

        shutil.rmtree(out_sprites_dir)
        out_sprites_dir.mkdir(parents=True, exist_ok=True)

        textures_data = (data_dir / 'textures.json').read_text(encoding='utf-8')
        textures_data = json.loads(textures_data)
        textures_data = {t['id']: t for t in textures_data}

        items_data = (data_dir / 'items.json').read_text(encoding='utf-8')
        items_data = json.loads(items_data)
        items_data = {item['id']: item for item in items_data}

        with monsters_file.open('r', encoding='utf-8') as f:
            monsters = json.load(f)

        monsters.sort(key=lambda m: m['level'])

        html = textwrap.dedent('''\
        <!doctype html>
        <html lang="en" data-bs-theme="dark">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta name="metadata-mtime" content="%%METADATA_MTIME%%">
            <title>Noxious monster list</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
                  rel="stylesheet"
                  integrity="sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"
                  crossorigin="anonymous">
            <style>
                img.sprite {
                    max-width: 246px;
                    height: auto;
                }
                .td-img {width:246px;}
                .td-name {width:auto;}
                .td-level {width:100px;}
                .td-hostile {width:100px;}
                .td-health {width:100px;}
                .td-drops {width:50%;}

                #simple-list:checked ~ .table .td-img,
                #simple-list:checked ~ .table .td-drops {
                    display: none;
                }
            </style>
        </head>
        <body>
        <div class="container-fluid">
        <input id="simple-list" type="checkbox"> <label for="simple-list">Simplified list</label>
        <table class="table table-striped">
        <thead>
        <tr>
            <th class="td-img p-0"></th>
            <th class="td-name">Name</th>
            <th class="td-hostile">Hostility</th>
            <th class="td-level">Level</th>
            <th class="td-health">Health/Mana</th>
            <th class="td-drops p-0">Drops</th>
        </tr>
        </thead>
        <tbody>
        ''')

        print('Generating monster drop table...')
        for i, monster in enumerate(monsters):
            print(f"\r{(i + 1) * 100 / len(monsters):.1f}%", end="")
            monster_sprite = sprites_dir / f'{monster["sprite"]}.png'

            sprite_path = 'sprites/default.png'
            width, height = 64, 64
            if monster_sprite.exists():
                im = Image.open(monster_sprite).convert('RGBA')
                tdata = textures_data.get(monster['id'])
                if tdata:
                    w, h = tdata['cellWidth'], tdata['cellHeight']
                    im = im.crop((0, 0, w, h))
                    out_monster = (out_sprites_dir / monster_sprite.name).with_suffix('.webp')
                    im.save(out_monster, quality=80)
                    sprite_path = f'sprites/{out_monster.name}'
                    width, height = im.size

            html += textwrap.dedent(f'''\
            <tr>
                <td class="td-img p-0">
                    <img src="{escape(sprite_path)}" width="{width}" height="{height}" class="sprite"
                         alt="Sprite of {escape(monster['name'])}">
                </td>
                <td class="td-name">{escape(monster['name'])}</td>
                <td class="td-hostile">{escape(monster['hostility'])}</td>
                <td class="td-level">{escape(str(monster['level']))}</td>
                <td class="td-health">{escape(str(monster['maxHealth']))}/{escape(str(monster['maxMana']))}</td>
                <td class="td-drops p-0">
            ''')

            html += '<table class="table table-striped">'
            html += '<colgroup>'
            html += '<col width="40%" style="width:40%">'
            html += '<col width="20%" style="width:20%">'
            html += '<col width="20%" style="width:20%">'
            html += '<col width="20%" style="width:20%">'
            html += '</colgroup>'
            html += '<tr>'
            html += '<th>Item</th>'
            html += '<th>Amount</th>'
            html += '<th>Chance</th>'
            html += '<th>Ratio</th>'
            html += '</tr>'
            for drop in monster.get('drops', []):
                item = items_data[drop['item']]
                drop_icon = item['dropIcon']
                chance = drop['chance']

                html += '<tr>'
                html += f'<td>{escape(item['name'])}</td>'
                html += f'<td>×{escape(str(drop['amount']))}</td>'
                if chance > 0:
                    html += f'<td>{escape(str(chance))}%</td>'
                    prop = 100/chance
                    if prop.is_integer() or prop >= 10:
                        html += f'<td>1 : {int(prop):_}</td>'
                    else:
                        html += f'<td>1 : {prop:_.2f}</td>'
                else:
                    html += f'<td>0%</td>'
                    html += f'<td>1 : 0</td>'
                html += '</tr>'
            html += '</table>'

            html += '</td></tr>'
        print()

        html += textwrap.dedent('''\
        </tbody>
        </table>
        </div>
        </body>
        </html>
        ''')

        with (html_dir / 'mobs.html').open('w', encoding='utf-8') as f:
            f.write(html)


def main(here: Path):
    gen = DataFetcher(here)
    gen.update_data()
    gen.generate_mob_drop_list()

    map_folder = here / "html" / "maps"
    shutil.rmtree(map_folder)
    map_folder.mkdir(parents=True, exist_ok=True)

    maps: list[Map] = gen.load_json("maps.json")

    metadata = []

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
                "pos": [0, 0],
                "columns": tile_map["width"],
                "rows": tile_map["height"],
            }
        )
    print()

    metadata.sort(key=lambda item: item["id"].casefold())

    metadata_file = map_folder.parent / "js" / "metadata.json"
    with metadata_file.open("r", encoding="utf-8") as f:
        old_metadata = json.load(f)
        remap_metadata = {old_md["id"]: old_md for old_md in old_metadata}

    for md in metadata:
        old_md = remap_metadata.get(md["id"], None)
        if old_md:
            md["pos"] = old_md["pos"]

    with metadata_file.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")

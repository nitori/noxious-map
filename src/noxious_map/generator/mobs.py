import shutil
import json
import time
from pathlib import Path

from PIL import Image

from .base import BaseGenerator


class MobGenerator(BaseGenerator):
    def generate(self):
        max_monster_sprite_width = 0
        max_drop_icon_width = 0

        bundle_dir = self.root / "bundle"

        monsters_file = self.bundle("data/monsters.json")
        out_sprites_dir = self.out("sprites")

        shutil.rmtree(out_sprites_dir)
        out_sprites_dir.mkdir(parents=True, exist_ok=True)

        textures_data = (bundle_dir / "data" / "textures.json").read_text(
            encoding="utf-8"
        )
        textures_data = json.loads(textures_data)
        textures_data = {t["id"]: t for t in textures_data}

        items_data = (bundle_dir / "data" / "items.json").read_text(encoding="utf-8")
        items_data = json.loads(items_data)
        items_data = {item["id"]: item for item in items_data}

        with monsters_file.open("r", encoding="utf-8") as f:
            monsters = json.load(f)

        monsters.sort(key=lambda m: m["level"])

        print("Generating monster drop table...")
        for i, monster in enumerate(monsters):
            print(f"\r{(i + 1) * 100 / len(monsters):.1f}%", end="")

            sprite = dict(path="sprites/default.png", width=64, height=64)

            monster_sprite = self.bundle(f"textures/sprites/{monster['sprite']}.png")
            if monster_sprite.exists():
                im = Image.open(monster_sprite).convert("RGBA")
                tdata = textures_data.get(monster["id"])
                if tdata:
                    w, h = tdata["cellWidth"], tdata["cellHeight"]
                    im = im.crop((0, 0, w, h))

                bbox = im.getbbox()
                if bbox:
                    im = im.crop(bbox)

                out_monster = (out_sprites_dir / monster_sprite.name).with_suffix(
                    ".webp"
                )
                im.save(out_monster, quality=80)
                sprite["path"] = f"sprites/{out_monster.name}"
                sprite["width"] = im.width
                sprite["height"] = im.height
                max_monster_sprite_width = max(max_monster_sprite_width, im.width)

            # replace with dict
            monster["sprite"] = sprite

            for drop in monster.setdefault("drops", []):
                # get the actual item
                drop["item"] = items_data[drop["item"]]

                drop_sprite_id = drop["item"].get(
                    "icon", drop["item"].get("drop_icon", drop["item"].get("sprite"))
                )
                if drop_sprite_id:
                    drop_sprite = self.bundle(
                        f"textures/itemIcons/{drop_sprite_id}.png"
                    )
                    if not drop_sprite.exists():
                        drop_sprite = self.bundle(
                            f"textures/itemDropIcons/{drop_sprite_id}.png"
                        )
                    if drop_sprite.exists():
                        im = Image.open(drop_sprite).convert("RGBA")

                        tdata = textures_data.get(drop_sprite_id)
                        if tdata:
                            w, h = tdata["cellWidth"], tdata["cellHeight"]
                            im = im.crop((0, 0, w, h))

                        bbox = im.getbbox()
                        if bbox:
                            im = im.crop(bbox)

                        out_drop_sprite = (
                            out_sprites_dir / drop_sprite.name
                        ).with_suffix(".webp")
                        im.save(out_drop_sprite, quality=80)
                        drop["sprite"] = {
                            "path": f"sprites/{out_drop_sprite.name}",
                            "width": im.width,
                            "height": im.height,
                        }
                        max_drop_icon_width = max(max_drop_icon_width, im.width)

                if "minAmount" in drop and "maxAmount" in drop:
                    min_amount = drop["minAmount"]
                    max_amount = drop["maxAmount"]
                elif "amount" in drop:
                    min_amount = drop["amount"]
                    max_amount = drop["amount"]
                else:
                    # no values, so just use 0 for now.
                    min_amount = 0
                    max_amount = 0

                if min_amount < max_amount:
                    drop["amount"] = f"{min_amount}-{max_amount}"
                else:
                    drop["amount"] = str(min_amount)

                if drop["chance"] > 0:
                    prop = 100 / drop["chance"]
                    if prop.is_integer() or prop >= 10:
                        drop["probability"] = f"1 : {int(prop):_}"
                    else:
                        drop["probability"] = f"1 : {prop:_.2f}"
                else:
                    drop["chance"] = 0
                    drop["probability"] = "1 : 0"

            monster["drops"] = sorted(
                monster["drops"], key=lambda d: (-d["chance"], d["item"]["name"])
            )

        print()
        monsters = sorted(
            enumerate(monsters),
            key=lambda m: (m[1]["level"], m[0]),
        )
        monsters = [m for i, m in monsters]

        # check if template or the current python file changed
        mtime = (self.templates_root / "mobs.html").stat().st_mtime
        mtime = max(mtime, Path(__file__).stat().st_mtime)

        html = self.render_template(
            "mobs.html",
            monsters=monsters,
            ts=int(mtime),
            max_monster_sprite_width=max_monster_sprite_width,
            max_drop_icon_width=max_drop_icon_width,
        )
        with self.out("mobs.html").open("w", encoding="utf-8", newline="\n") as f:
            f.write(html)

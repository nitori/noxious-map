from pathlib import Path
import shutil
import zipfile
import json
import secrets

import requests

from .models import Map
from .utils import checksum_file, pretty_size, progress, normalize_name


def download_data(here: Path, *, force=False):
    print("Updating bundle.zip")

    filename = here / "bundle.zip"
    bundle_dir = here / "bundle"
    url = "https://server.noxious.gg/data/bundle"

    r = requests.head(url)
    checksum = r.headers["Etag"].strip("\"'").lower()
    file_size = int(r.headers.get("Content-Length", "0"))

    if force or not filename.exists() or checksum != checksum_file(filename):
        r = requests.get(url, stream=True)

        print("  downloading...")
        collected = 0
        with filename.open("wb") as f:
            for chunk in progress(r.iter_content(1 << 16), max=file_size, incfunc=len):
                print(f' [{pretty_size(collected)}/{pretty_size(file_size)}]', end='')
                collected += len(chunk)
                f.write(chunk)
    else:
        print("  skipping download.")

    print("  unzipping...")
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    with zipfile.ZipFile(filename, "r") as zf:
        zf.extractall(bundle_dir)

    print("  formatting json files in bundle/data/ ...")
    for json_file in (bundle_dir / "data").glob("*.json"):
        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        rval = secrets.token_urlsafe(12)
        tmp_json_file = json_file.with_stem(f"{json_file.stem}_{rval}")

        with tmp_json_file.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)

        shutil.copyfile(tmp_json_file, json_file)
        tmp_json_file.unlink()

    # dump all maps in individual files for easier inspection
    maps_json = bundle_dir / "data/maps.json"
    maps_folder = bundle_dir / "maps"
    if maps_folder.exists():
        shutil.rmtree(maps_folder)
    maps_folder.mkdir(parents=True, exist_ok=True)
    with maps_json.open('r', encoding='utf-8') as f:
        maps = json.load(f)
    for tile_map in maps:
        map_file = maps_folder / f"{tile_map['id']}_{normalize_name(tile_map['name'])}.json"
        with map_file.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(tile_map, f, indent=4)

    print("Update complete!")

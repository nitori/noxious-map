from pathlib import Path
import shutil
import zipfile
import json
import secrets

import requests

from .utils import checksum_file, pretty_size


def download_data(here: Path, *, force=False):
    print("Updating bundle.zip")

    filename = here / "bundle.zip"
    bundle_dir = here / "bundle"
    url = "https://server.noxious.gg/data/bundle"

    r = requests.head(url)
    checksum = r.headers["Etag"].strip("\"'").lower()
    file_size = int(r.headers.get("Content-Length", "0"))

    if force or checksum != checksum_file(filename):
        r = requests.get(url, stream=True)

        print("  downloading...")
        collected = 0
        with filename.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                collected += len(chunk)
                if file_size:
                    print(
                        f"\r  {collected / file_size * 100:.1f}%",
                        f"({pretty_size(collected)} of {pretty_size(file_size)})",
                        end="",
                    )
                f.write(chunk)
        print()
    else:
        print("  skipping download.")

    print("  unzipping...")
    shutil.rmtree(bundle_dir)
    with zipfile.ZipFile(filename, "r") as zf:
        zf.extractall(bundle_dir)

    print("  formatting json files in bundle/data/ ...")
    for json_file in (bundle_dir / "data").glob("*.json"):
        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        rval = secrets.token_urlsafe(12)
        tmp_json_file = json_file.with_stem(f"{json_file.stem}_{rval}")

        with tmp_json_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        shutil.copyfile(tmp_json_file, json_file)
        tmp_json_file.unlink()

    print("Update complete!")

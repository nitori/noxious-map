from pathlib import Path

from .downloader import download_data
from .generator import BaseGenerator
from .utils import compare_depth_sort


def main(here: Path):
    download_data(here)

    for gen_cls, _kwargs in BaseGenerator.get_subclasses():
        print(f"Invoking generator: {gen_cls.__name__}")
        gen = gen_cls(here)
        gen.generate()

    print()
    print()
    print("old remaining code disabled")
    print()

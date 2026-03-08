from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class BaseGenerator:
    root: Path
    bundle_dir: Path
    out_dir: Path
    jinja_env: Environment

    _subclasses = []

    def __init_subclass__(cls, **kwargs):
        cls._subclasses.append((cls, kwargs))

    @classmethod
    def get_subclasses(cls):
        return cls._subclasses

    def __init__(self, root: Path):
        self.root = root
        self.bundle_dir = self.root / "bundle"
        self.out_dir = self.root / "html"

        _here = Path(__file__).absolute().parent
        _tplroot = _here / "templates"

        loader = FileSystemLoader(_tplroot)
        self.jinja_env = Environment(autoescape=True, loader=loader)
        self.setup()

    def setup(self):
        """Override to do stuff right after instance was created"""

    def render_template(self, name: str, **context):
        tpl = self.jinja_env.get_or_select_template(name)
        return tpl.render(**context)

    def bundle(self, path: str | Path) -> Path:
        result = self.bundle_dir / path
        if not result.is_relative_to(self.bundle_dir):
            raise FileNotFoundError(str(result))
        return result

    def out(self, path: str | Path) -> Path:
        result = self.out_dir / path
        if not result.is_relative_to(self.out_dir):
            raise FileNotFoundError(str(result))
        return result

    def generate(self):
        raise NotImplementedError()

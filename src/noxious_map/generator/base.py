from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class BaseGenerator:
    root: Path

    def __init__(self, root: Path):
        self.root = root
        self._bundle_dir = self.root / "bundle"
        self._out_dir = self.root / "html"

        _here = Path(__file__).absolute().parent
        _tplroot = _here / "templates"

        loader = FileSystemLoader(_tplroot)
        self.jinja_env = Environment(autoescape=True, loader=loader)

    def render_template(self, name: str, **context):
        tpl = self.jinja_env.get_or_select_template(name)
        return tpl.render(**context)

    def bundle(self, path: str | Path) -> Path:
        result = self._bundle_dir / path
        if not result.is_relative_to(self._bundle_dir):
            raise FileNotFoundError(str(result))
        return result

    def out(self, path: str | Path) -> Path:
        result = self._out_dir / path
        if not result.is_relative_to(self._out_dir):
            raise FileNotFoundError(str(result))
        return result

    def generate(self):
        raise NotImplementedError()

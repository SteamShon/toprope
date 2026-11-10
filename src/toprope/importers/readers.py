"""Built-in readers (ADR-0051): a file, and a URL. Others plug in through `toprope.readers`."""
from __future__ import annotations

from pathlib import Path

from ..errors import fixed
from .port import Profile, Raw


class FileReader:
    kind = "file"

    def read(self, location: str, profile: Profile) -> Raw:
        try:
            return Raw(Path(location).read_bytes(), location)
        except OSError as e:
            raise SystemExit(fixed(f"cannot read {location}: {e.strerror}", "give the path of the file to import")) from None


class HttpReader:
    kind = "http"

    def read(self, location: str, profile: Profile) -> Raw:
        import urllib.request
        if not location.startswith(("https://", "http://")):
            raise SystemExit(fixed(f"{location!r} is not a URL", "give an http(s) URL, or use the file reader"))
        try:
            with urllib.request.urlopen(location, timeout=30) as r:
                return Raw(r.read(), location)
        except OSError as e:
            raise SystemExit(fixed(f"cannot fetch {location}: {e}", "check the URL and that the network allows it")) from None


class TreeReader:
    """Every file under a folder that matches `options.glob` (default `**/*.md`), in path order,
    each after a line `<!-- toprope:file <path> -->` so citations name the file and its line."""
    kind = "tree"

    def read(self, location: str, profile: Profile) -> Raw:
        root = Path(location)
        if not root.is_dir():
            raise SystemExit(fixed(f"{location} is not a folder", "give a folder, or use the file reader for one file"))
        pattern = str(profile.options.get("glob", "**/*.md"))
        files = sorted(p for p in root.glob(pattern) if p.is_file() and ".git" not in p.parts)
        if not files:
            raise SystemExit(fixed(f"no file under {location} matches {pattern}", "set `options: {glob: ...}` in the profile"))
        parts = [f"<!-- toprope:file {p} -->\n{p.read_text(encoding='utf-8', errors='replace')}" for p in files]
        return Raw("\n".join(parts).encode(), location)


BUILTIN = [FileReader(), HttpReader(), TreeReader()]

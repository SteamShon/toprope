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
    """Every file under a folder that matches `options.glob` (default `**/*.md`), in path order, as
    the source's parts, each citing its own path. Matches outside the folder and in hidden folders
    (`.git`, `.venv`) are left out."""
    kind = "tree"

    def read(self, location: str, profile: Profile) -> Raw:
        root = Path(location)
        if not root.is_dir():
            raise SystemExit(fixed(f"{location} is not a folder", "give a folder, or use the file reader for one file"))
        pattern = str(profile.options.get("glob", "**/*.md"))
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise SystemExit(fixed(f"the glob {pattern!r} reaches outside {location}",
                                   "give a pattern inside the folder, e.g. `**/*.md`"))
        base = root.resolve()
        try:
            found = sorted(root.glob(pattern))
        except (ValueError, NotImplementedError) as e:
            raise SystemExit(fixed(f"the glob {pattern!r} does not work: {e}", "give a pattern like `**/*.md`")) from None
        files = [p for p in found if p.is_file() and p.resolve().is_relative_to(base)
                 and not any(part.startswith(".") for part in p.relative_to(root).parts[:-1])]
        if not files:
            raise SystemExit(fixed(f"no file under {location} matches {pattern}", "set `options: {glob: ...}` in the profile"))
        parts = [Raw(p.read_bytes(), str(p)) for p in files]
        return Raw(b"\n".join(x.data for x in parts), location, parts)


BUILTIN = [FileReader(), HttpReader(), TreeReader()]

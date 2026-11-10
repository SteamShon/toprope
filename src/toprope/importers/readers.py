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


BUILTIN = [FileReader(), HttpReader()]

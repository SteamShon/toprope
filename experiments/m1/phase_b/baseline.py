"""What every arm starts from (ADR-0040 §3): the approved self domains `authoring@12` and
`delivery@6`, re-baselined for the M1 recheck on 2026-11-09: the self domains with their promoted
outcome rules and Authoring's bundle questions, approved by the researcher (#192, #205). M1 as
first run started from `authoring@9` and `delivery@1` (below, and the comment under BASELINE_REVS).

The repository's self domains move on (they run their deployed commit, ADR-0045), so the harness
never reads them from the working tree. It reads each domain from a repository revision at which
its baseline commit was that domain's `main`, and the shared files (the composition, the identity
file) from the first domain's revision.

Why not `authoring@4`, the first baseline: today's harness finds an invariant break in it (an
approved commit's check could be recorded again as failed, which the invariant then refuses);
the toolchain's deploy floor refuses it, so the Toprope arm could not start. `authoring@8` fixed
it and `@9`, the first approved commit after the fix, has the same interface; from `@4` to `@9`
elements were only added (commit evidence, and `record_check.settled`), so every element the
binding names still exists. `delivery@1` passes as it is.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

# domain → (its baseline commit, a repository revision at which that commit was its `main`)
BASELINE_REVS = {
    "authoring": ("12-acf2a5f6e362166c", "afba98ab582a0e7c781c089bc3cbc931c2de33ae"),
    "delivery": ("6-c2678fc294429d48", "afba98ab582a0e7c781c089bc3cbc931c2de33ae"),
}
# M1 as first run and reported (M1-report.md): authoring@9-b4ec65433222f096 at 4fcf912b05,
# delivery@1-584aaeea5e686ee8 at b13f193700.
BASELINE = {d: c for d, (c, _) in BASELINE_REVS.items()}
SHARED = ("domains/toprope-self.composition.yaml", "toprope.identity.yaml")

_roots: dict[str, Path] = {}


def _extract(repo: Path, rev: str, paths: list[str], out: Path) -> None:
    r = subprocess.run(["git", "-C", str(repo), "archive", rev, *paths], capture_output=True, check=False)
    if r.returncode != 0:
        raise SystemExit(f"cannot read the baseline {rev[:12]} from {repo}: {r.stderr.decode().strip()} "
                         "(the harness needs the repository's history: clone without --depth)")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        tar.extractall(out, filter="data")


def baseline_root(repo: Path) -> Path:
    """A read-only kernel root holding each self domain as of its baseline revision (once per
    process), with each commit store's `main` checked against `BASELINE`."""
    key = str(repo)
    if key in _roots:
        return _roots[key]
    out = Path(tempfile.mkdtemp(prefix="phase-b-baseline-"))
    first = next(iter(BASELINE_REVS.values()))[1]
    _extract(repo, first, list(SHARED), out)
    for d, (_, rev) in BASELINE_REVS.items():
        _extract(repo, rev, [f"domains/{d}", f".toprope/commits/{d}"], out)
    from toprope.commits import CommitStore
    got = {d: CommitStore(out / ".toprope/commits").main(d).id for d in BASELINE}
    if got != BASELINE:
        raise SystemExit(f"the baseline revisions have {got}, not {BASELINE}")
    _roots[key] = out
    return out

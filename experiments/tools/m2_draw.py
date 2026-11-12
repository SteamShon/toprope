"""M2's draw: a preregistered draw, not the researcher, decides which problem each change request
carries (ADR-0054 §3, `docs/experiments/M2-spec.md` §5).

Usage (from the repo root; the researcher runs every command that reads the salt):
  python experiments/tools/m2_draw.py make-salt ~/m2-salt          # outside the repository
  python experiments/tools/m2_draw.py salt-hash ~/m2-salt          # its sha256 goes in draw.yaml
  python experiments/tools/m2_draw.py freeze-bases experiments/m2/change-requests.yaml
  python experiments/tools/m2_draw.py draw   --salt ~/m2-salt                   # the researcher only
  python experiments/tools/m2_draw.py verify --salt FILE --key change-key.yaml  # after the salt is published

The steps, in order:
1. The researcher makes the salt on their machine. Only its hash goes into
   `experiments/m2/draw.yaml` (`salt_sha256`), committed with the preregistration.
2. The change requests are taken from the diary. Before any seed is written, `freeze-bases` records
   each request's text hash in `experiments/m2/draw-bases.json`. The bases file is committed.
3. `draw` refuses unless `draw.yaml` and `draw-bases.json` are committed and unchanged, and the
   salt matches the committed hash. It then prints each request's type, to the researcher only.
   The types belong to the key and are sealed with it.
4. After scoring, the salt is published, and `verify` recomputes every draw against the key.

For request `seq` with base hash `h` (hex), the draw is
  u = int(sha256(salt ‖ 0x00 ‖ str(seq) ‖ 0x00 ‖ bytes.fromhex(h))) / 2**256,
where `salt` is the salt file's bytes with surrounding whitespace removed. `u` picks the first type
whose cumulative share exceeds it, in the order `draw.yaml` lists them.

When a drawn type cannot be written into its request, the researcher records it under
`not_applicable` in the key. Then the next type in the list is used, wrapping around, skipping
every type recorded there. `none` (a clean control) always applies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
M2 = ROOT / "experiments" / "m2"
CLEAN = "none"


def die(msg: str, fix: str) -> None:
    raise SystemExit(f"error: {msg}. Fix: {fix}")


def read_salt(path: Path) -> bytes:
    try:
        salt = path.read_bytes().strip()
    except OSError as e:
        die(f"cannot read the salt {path}: {e.strerror}", "give the salt file made by `make-salt`")
    if len(salt) < 32:
        die(f"the salt {path} is shorter than 32 bytes", "make one with `make-salt`")
    return salt


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_draw(path: Path) -> tuple[list[tuple[str, float]], int, str]:
    try:
        d = yaml.safe_load(path.read_text()) or {}
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}", "write draw.yaml from draw.template.yaml with the preregistration")
    types = d.get("types")
    if not isinstance(types, list) or not types or not all(isinstance(t, dict) and set(t) == {"type", "share"} for t in types):
        die(f"{path}: `types` is a list of {{type, share}}", "list the types in their order, each with its share")
    shares = [(str(t["type"]), float(t["share"])) for t in types]
    if abs(sum(s for _, s in shares) - 1.0) > 1e-9 or any(s < 0 for _, s in shares):
        die(f"{path}: the shares add up to {sum(s for _, s in shares)}", "make the shares non-negative and add up to 1")
    if CLEAN not in dict(shares):
        die(f"{path}: no `{CLEAN}` type", f"keep `{CLEAN}`, the clean control, among the types")
    salt_sha = str(d.get("salt_sha256", ""))
    if len(salt_sha) != 64 or any(c not in "0123456789abcdef" for c in salt_sha):
        die(f"{path}: `salt_sha256` is not a sha256", "put the output of `salt-hash` there")
    return shares, int(d.get("requests", 0)), salt_sha


def pick(u: float, shares: list[tuple[str, float]]) -> str:
    acc = 0.0
    for t, s in shares:
        acc += s
        if u < acc:
            return t
    return shares[-1][0]          # u within rounding of 1


def draw_one(salt: bytes, seq: int, base_hex: str, shares: list[tuple[str, float]]) -> str:
    d = hashlib.sha256(salt + b"\x00" + str(seq).encode() + b"\x00" + bytes.fromhex(base_hex)).digest()
    return pick(int.from_bytes(d, "big") / 2**256, shares)


def applied(drawn: str, not_applicable: list[str], shares: list[tuple[str, float]]) -> str:
    """The type used when the drawn one, and possibly the next ones, cannot be written."""
    order = [t for t, _ in shares]
    i = order.index(drawn)
    for k in range(len(order)):
        t = order[(i + k) % len(order)]
        if t == CLEAN or t not in not_applicable:
            return t
    return CLEAN


def committed(path: Path) -> bool:
    """True when `path` is tracked by git and has no uncommitted change."""
    rel = str(path.resolve().relative_to(ROOT))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=ROOT).returncode == 0
    return tracked and clean


def inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def cmd_make_salt(a: argparse.Namespace) -> None:
    out = Path(a.out).expanduser()
    if inside_repo(out):
        die(f"{out} is inside the repository, where an agent or a commit could read it",
            "write the salt outside the repository, e.g. in your home directory")
    if out.exists():
        die(f"{out} exists", "keep the salt you made, or remove it first if no hash of it was committed")
    out.write_text(secrets.token_hex(32) + "\n")
    out.chmod(0o600)
    print(f"salt written to {out}; commit only `salt-hash {out}`")


def cmd_salt_hash(a: argparse.Namespace) -> None:
    print(sha256_hex(read_salt(Path(a.salt).expanduser())))


def load_requests(path: Path) -> list[dict]:
    try:
        d = yaml.safe_load(path.read_text()) or {}
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}", "give the change requests file")
    reqs = d.get("requests")
    if not isinstance(reqs, list) or not all(isinstance(r, dict) and "seq" in r and r.get("intent") for r in reqs):
        die(f"{path}: `requests` is a list with `seq` and `intent`", "write each request with its seq and intent")
    return reqs


def cmd_freeze_bases(a: argparse.Namespace) -> None:
    out = Path(a.out)
    if out.exists():
        die(f"{out} exists: the bases are frozen once", "keep it; a request changed after its draw is reported, not redrawn")
    bases = {str(r["seq"]): sha256_hex(str(r["intent"]).encode()) for r in load_requests(Path(a.requests))}
    out.write_text(json.dumps({"frozen_at": datetime.now(UTC).isoformat(timespec="seconds"), "bases": bases},
                              indent=2) + "\n")
    print(f"{len(bases)} bases frozen in {out}; commit it before `draw`")


def bases_and_salt(a: argparse.Namespace) -> tuple[list[tuple[str, float]], int, dict[str, str], bytes]:
    shares, n, salt_sha = load_draw(Path(a.draw))
    salt = read_salt(Path(a.salt).expanduser())
    if sha256_hex(salt) != salt_sha:
        die("the salt does not match the committed `salt_sha256`", "use the salt whose hash the preregistration holds")
    try:
        bases = json.loads(Path(a.bases).read_text())["bases"]
    except (OSError, ValueError, KeyError):
        die(f"cannot read the bases {a.bases}", "run `freeze-bases` and commit its output")
    return shares, n, bases, salt


def cmd_draw(a: argparse.Namespace) -> None:
    for f in (Path(a.draw), Path(a.bases)):
        if not committed(f):
            die(f"{f} is not committed, or changed since", "commit draw.yaml and draw-bases.json before the draw")
    shares, n, bases, salt = bases_and_salt(a)
    if len(bases) < 12:
        die(f"{len(bases)} requests; the spec runs Phase B on at least 12", "keep the diary going until it holds 12")
    for seq in sorted(bases, key=int):
        print(f"{seq}\t{draw_one(salt, int(seq), bases[seq], shares)}")
    print("Keep these with the key, outside the repository. Write each drawn problem into its request; "
          "if one cannot be written, record it under `not_applicable` and use the next type.", file=sys.stderr)


def cmd_verify(a: argparse.Namespace) -> None:
    shares, _, bases, salt = bases_and_salt(a)
    key = yaml.safe_load(Path(a.key).read_text()) or {}
    seeds = {str(s["seq"]): s for s in key.get("seeds", [])}
    problems = []
    for seq in sorted(bases, key=int):
        drawn = draw_one(salt, int(seq), bases[seq], shares)
        s = seeds.get(seq)
        if s is None:
            problems.append(f"request {seq}: not in the key")
            continue
        if s.get("drawn") != drawn:
            problems.append(f"request {seq}: the key says drawn {s.get('drawn')}, the draw gives {drawn}")
        want = applied(drawn, list(s.get("not_applicable") or []), shares)
        if s.get("type") != want:
            problems.append(f"request {seq}: the key uses {s.get('type')}, the rule gives {want}")
    for seq in sorted(set(seeds) - set(bases)):
        problems.append(f"request {seq}: in the key, but not in the frozen bases")
    for p in problems:
        print(p)
    if problems:
        raise SystemExit(1)
    print(f"all {len(bases)} draws match the key")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="m2_draw", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("make-salt"); s.add_argument("out"); s.set_defaults(f=cmd_make_salt)
    s = sub.add_parser("salt-hash"); s.add_argument("salt"); s.set_defaults(f=cmd_salt_hash)
    s = sub.add_parser("freeze-bases"); s.add_argument("requests")
    s.add_argument("--out", default=str(M2 / "draw-bases.json")); s.set_defaults(f=cmd_freeze_bases)
    for name, f in (("draw", cmd_draw), ("verify", cmd_verify)):
        s = sub.add_parser(name)
        s.add_argument("--salt", required=True)
        s.add_argument("--draw", default=str(M2 / "draw.yaml"))
        s.add_argument("--bases", default=str(M2 / "draw-bases.json"))
        if name == "verify":
            s.add_argument("--key", required=True)
        s.set_defaults(f=f)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()

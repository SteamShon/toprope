"""M2's draw: a preregistered draw, not the researcher, decides which problem each change request
carries (ADR-0054 §3, `docs/experiments/M2-spec.md` §5).

Usage (from the repo root; only the researcher runs the commands that read the salt):
  python experiments/tools/m2_draw.py make-salt ~/m2-salt       # outside the repository
  python experiments/tools/m2_draw.py salt-hash ~/m2-salt       # its sha256 goes in draw.yaml
  python experiments/tools/m2_draw.py freeze-bases experiments/m2/change-requests.yaml
  python experiments/tools/m2_draw.py draw   --salt ~/m2-salt   # the researcher only
  python experiments/tools/m2_draw.py verify --salt FILE --key KEY --requests experiments/m2/change-requests.yaml

Two secrets, two jobs:
- **A public beacon stops the researcher from choosing.** The draw mixes in a drand round
  (`quicknet`) published an hour after the bases reached `origin/develop`. When the bases are
  frozen, nobody knows that round, so no wording of a request can be tried until it draws a wished
  type. When the round is published, the bases are already on the protected branch.
- **The salt keeps the key sealed.** The beacon and the bases are public, so without a secret
  anyone could compute the types. Only `sha256(salt)` is committed, in `draw.yaml`, before the
  bases. The salt is published after scoring.

The order:
1. The researcher makes the salt outside the repository, puts its hash in
   `experiments/m2/draw.yaml` (status `frozen`), and merges it into `develop`.
2. The change requests are taken from the diary. `freeze-bases` records each request's
   `intent` hash in `experiments/m2/draw-bases.json`, and that file is merged into `develop`.
   Afterwards `intent` never changes; the seeded wording goes in `seeded_intent`.
3. `draw` reads both files as `origin/develop` has them, and refuses unless all of these hold:
   - each file was added once there and never changed;
   - the working copy matches;
   - `draw.yaml` is frozen and came first;
   - the salt matches its hash;
   - the beacon round is out.

   It prints the round, the bases commit and each request's type, to the researcher only.
4. After scoring, the salt is published, and `verify` recomputes every draw. It also checks
   that every `intent` still matches its base, and lists each `not_applicable`, with its reason,
   for review.

For request `seq` with base hash `h`, with `r` the beacon randomness (sha256 of the round's signature):
  u = int(sha256(salt ‖ 0x00 ‖ r ‖ 0x00 ‖ str(seq) ‖ 0x00 ‖ h)) / 2**256,
where `salt` is the salt file's bytes with surrounding whitespace removed. `u` picks the first type
whose cumulative share exceeds it, in the order `draw.yaml` lists them. When a drawn type cannot be
written, the key records it under `not_applicable` with a reason, and the next type in that order
is used, wrapping around; `none` (a clean control) always applies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import yaml

ROOT = Path(__file__).resolve().parents[2]
DRAW = "experiments/m2/draw.yaml"
BASES = "experiments/m2/draw-bases.json"
REF = "origin/develop"
CLEAN = "none"
MIN_REQUESTS = 12
DELAY = 3600                                 # the round is drawn an hour after the bases landed
BEACON = "https://api.drand.sh/v2/beacons/quicknet"
GENESIS, PERIOD = 1692803367, 3              # quicknet's chain info


def die(msg: str, fix: str) -> None:
    raise SystemExit(f"error: {msg}. Fix: {fix}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_salt(path: Path) -> bytes:
    try:
        salt = path.read_bytes().strip()
    except OSError as e:
        die(f"cannot read the salt {path}: {e.strerror}", "give the salt file made by `make-salt`")
    if len(salt) < 32:
        die(f"the salt {path} is shorter than 32 bytes", "make one with `make-salt`")
    return salt


def parse_draw(text: str) -> tuple[list[tuple[str, float]], str, str]:
    d = yaml.safe_load(text) or {}
    types = d.get("types")
    if not isinstance(types, list) or not types or not all(isinstance(t, dict) and set(t) == {"type", "share"} for t in types):
        die("draw.yaml: `types` is a list of {type, share}", "list the types in their order, each with its share")
    shares = [(str(t["type"]), float(t["share"])) for t in types]
    if abs(sum(s for _, s in shares) - 1.0) > 1e-9 or any(s < 0 for _, s in shares):
        die(f"draw.yaml: the shares add up to {sum(s for _, s in shares)}", "make the shares non-negative and add up to 1")
    if CLEAN not in dict(shares) or len(dict(shares)) != len(shares):
        die("draw.yaml: the types repeat, or lack `none`", f"list each type once, and keep `{CLEAN}`, the clean control")
    salt_sha = str(d.get("salt_sha256", ""))
    if len(salt_sha) != 64 or any(c not in "0123456789abcdef" for c in salt_sha):
        die("draw.yaml: `salt_sha256` is not a sha256", "put the output of `salt-hash` there")
    return shares, salt_sha, str(d.get("status", ""))


def pick(u: float, shares: list[tuple[str, float]]) -> str:
    acc = 0.0
    for t, s in shares:
        acc += s
        if u < acc:
            return t
    return shares[-1][0]          # u within rounding of 1


def draw_one(salt: bytes, rand: bytes, seq: int, base_hex: str, shares: list[tuple[str, float]]) -> str:
    d = hashlib.sha256(salt + b"\x00" + rand + b"\x00" + str(seq).encode() + b"\x00" + bytes.fromhex(base_hex)).digest()
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


# --- git: what the protected branch holds ---

def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def landed(root: Path, path: str, ref: str = REF) -> tuple[str, int, str]:
    """(commit, commit time, content) of `path` on `ref`, which must have added it once and never
    changed it since; the working copy must match."""
    log = git(root, "log", ref, "--format=%H %ct", "--", path).split()
    if not log:
        die(f"{path} is not on {ref}", f"merge it into develop, then `git fetch origin develop`")
    if len(log) != 2:
        die(f"{path} changed on {ref} after it was first merged", "a frozen draw file is never changed; report it, do not redraw")
    commit, when = log[0], int(log[1])
    content = git(root, "show", f"{commit}:{path}")
    local = root / path
    if not local.exists() or local.read_text() != content:
        die(f"the working copy of {path} differs from {ref}", f"check out {path} as {ref} has it")
    return commit, when, content


# --- the beacon ---

def round_at(t: int) -> int:
    return (t - GENESIS) // PERIOD + 1


def fetch_round(rnd: int) -> bytes:
    with urllib.request.urlopen(f"{BEACON}/rounds/{rnd}", timeout=30) as r:
        sig = json.load(r)["signature"]
    return hashlib.sha256(bytes.fromhex(sig)).digest()


def beacon(when: int, fetch: Callable[[int], bytes], now: float | None = None) -> tuple[int, bytes]:
    rnd = round_at(when + DELAY)
    if (time.time() if now is None else now) < GENESIS + (rnd - 1) * PERIOD:
        die(f"beacon round {rnd} is not out yet (an hour after the bases landed)", "run `draw` again after that time")
    try:
        return rnd, fetch(rnd)
    except Exception as e:  # noqa: BLE001 - any failure to fetch is reported the same way
        die(f"cannot fetch beacon round {rnd}: {e}", f"check that {BEACON} is reachable, then run it again")
        raise


# --- commands ---

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
    seqs = [str(r["seq"]) for r in reqs]
    if len(set(seqs)) != len(seqs):
        die(f"{path}: a `seq` repeats", "give each request its own seq")
    return reqs


def cmd_freeze_bases(a: argparse.Namespace) -> None:
    out = Path(a.out)
    if out.exists():
        die(f"{out} exists: the bases are frozen once", "keep it; a request changed after its draw is reported, not redrawn")
    bases = {str(r["seq"]): sha256_hex(str(r["intent"]).encode()) for r in load_requests(Path(a.requests))}
    out.write_text(json.dumps({"frozen_at": datetime.now(UTC).isoformat(timespec="seconds"), "bases": bases},
                              indent=2) + "\n")
    print(f"{len(bases)} bases frozen in {out}; merge it into develop before `draw`")


def drawn_all(root: Path, salt_path: str, fetch: Callable[[int], bytes], now: float | None = None,
              ref: str = REF) -> tuple[dict[str, str], dict]:
    d_commit, d_when, d_text = landed(root, DRAW, ref)
    b_commit, b_when, b_text = landed(root, BASES, ref)
    shares, salt_sha, status = parse_draw(d_text)
    if status != "frozen":
        die("draw.yaml is not `status: frozen`", "freeze the preregistration before the draw")
    if d_when > b_when:
        die("draw.yaml landed after the bases", "the salt's hash is committed before the bases are frozen")
    salt = read_salt(Path(salt_path).expanduser())
    if sha256_hex(salt) != salt_sha:
        die("the salt does not match the committed `salt_sha256`", "use the salt whose hash the preregistration holds")
    bases = json.loads(b_text)["bases"]
    if len(bases) < MIN_REQUESTS:
        die(f"{len(bases)} requests; the spec runs Phase B on at least {MIN_REQUESTS}",
            f"keep the diary going until it holds {MIN_REQUESTS}")
    rnd, rand = beacon(b_when, fetch, now)
    types = {seq: draw_one(salt, rand, int(seq), bases[seq], shares) for seq in sorted(bases, key=int)}
    return types, {"bases_commit": b_commit, "draw_commit": d_commit, "round": rnd, "shares": shares}


def cmd_draw(a: argparse.Namespace, fetch: Callable[[int], bytes] = fetch_round) -> None:
    types, info = drawn_all(Path(a.root), a.salt, fetch)
    print(f"# bases {info['bases_commit']}, draw.yaml {info['draw_commit']}, beacon quicknet round {info['round']}")
    for seq, t in types.items():
        print(f"{seq}\t{t}")
    print("Keep these with the key, outside the repository, with the line above. Write each drawn problem "
          "into its request's `seeded_intent`; if one cannot be written, record it under `not_applicable` "
          "with `why`, and use the next type.", file=sys.stderr)


def cmd_verify(a: argparse.Namespace, fetch: Callable[[int], bytes] = fetch_round) -> None:
    root = Path(a.root)
    types, info = drawn_all(root, a.salt, fetch, ref=a.ref)
    shares = info["shares"]
    key = yaml.safe_load(Path(a.key).read_text()) or {}
    seeds = {str(s["seq"]): s for s in key.get("seeds", [])}
    bases = json.loads(git(root, "show", f"{info['bases_commit']}:{BASES}"))["bases"]
    problems, review = [], []
    for seq, drawn in types.items():
        s = seeds.get(seq)
        if s is None:
            problems.append(f"request {seq}: not in the key")
            continue
        if s.get("drawn") != drawn:
            problems.append(f"request {seq}: the key says drawn {s.get('drawn')}, the draw gives {drawn}")
        na = s.get("not_applicable") or []
        if not all(isinstance(x, dict) and x.get("type") and x.get("why") for x in na):
            problems.append(f"request {seq}: each `not_applicable` entry needs `type` and `why`")
        want = applied(drawn, [str(x.get("type")) for x in na if isinstance(x, dict)], shares)
        if s.get("type") != want:
            problems.append(f"request {seq}: the key uses {s.get('type')}, the rule gives {want}")
        review += [f"request {seq}: {x.get('type')} not applicable: {x.get('why')}" for x in na if isinstance(x, dict)]
    for seq in sorted(set(seeds) - set(types)):
        problems.append(f"request {seq}: in the key, but not in the frozen bases")
    for r in load_requests(Path(a.requests)):
        if sha256_hex(str(r["intent"]).encode()) != bases.get(str(r["seq"])):
            problems.append(f"request {r['seq']}: its `intent` changed after the bases were frozen")
    for line in review:
        print(f"review: {line}")
    for p in problems:
        print(p)
    if problems:
        raise SystemExit(1)
    print(f"all {len(types)} draws match the key (beacon round {info['round']}); "
          f"{len(review)} not-applicable reason(s) above, for review")


def main(argv: list[str] | None = None, fetch: Callable[[int], bytes] = fetch_round) -> None:
    ap = argparse.ArgumentParser(prog="m2_draw", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("make-salt"); s.add_argument("out"); s.set_defaults(f=cmd_make_salt)
    s = sub.add_parser("salt-hash"); s.add_argument("salt"); s.set_defaults(f=cmd_salt_hash)
    s = sub.add_parser("freeze-bases"); s.add_argument("requests")
    s.add_argument("--out", default=str(ROOT / BASES)); s.set_defaults(f=cmd_freeze_bases)
    for name, f in (("draw", cmd_draw), ("verify", cmd_verify)):
        s = sub.add_parser(name)
        s.add_argument("--salt", required=True)
        s.add_argument("--root", default=str(ROOT))
        if name == "verify":
            s.add_argument("--key", required=True)
            s.add_argument("--requests", required=True)
            s.add_argument("--ref", default=REF)
        s.set_defaults(f=f)
    a = ap.parse_args(argv)
    if a.cmd in ("draw", "verify"):
        a.f(a, fetch)
    else:
        a.f(a)


if __name__ == "__main__":
    main()

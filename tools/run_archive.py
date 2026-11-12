"""Experiment run records outside the working tree (ADR-0055).

A run's summary stays in git: its top-level files, and each `scoring*/` directory's own files
(the labels and the metrics). Its raw records live elsewhere: the arms' outputs, the worlds, and
the grader's transcripts. They are kept by content hash, so a copy fetched later is provably the
one that was scored.

Two kinds of keeping:
- **Already in git history (M1).** `split` removes a run's raw directories from the tree. It
  writes `RAW.json`, which names the commit that holds them and each directory's git tree hash,
  and a `.gitignore` that keeps a restored copy out of later commits. `restore` puts them back
  from that commit, through `git archive`, after checking the tree hashes. A clone made with
  `--filter=blob:none` never downloads them until then.
- **Never in git (M2 on).** `pack` makes a byte-for-byte reproducible `.tar.gz` of a run's raw
  records, and a manifest with the archive's sha256 and every file's sha256. The manifest is
  committed, and the archive is uploaded as a GitHub release asset. `fetch` downloads it and
  checks both levels of hash before extracting.

  python tools/run_archive.py split experiments/m1/runs/phase-b [--all-dirs] [--commit REV]
  python tools/run_archive.py restore experiments/m1/runs/phase-b
  python tools/run_archive.py check              # every RAW.json: well formed, raw paths untracked and ignored
  python tools/run_archive.py pack RUN_DIR --out run.tar.gz --manifest RUN_DIR.archive.json [--url URL]
  python tools/run_archive.py fetch MANIFEST --into DIR [--file run.tar.gz]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = "RAW.json"
RUNS = "experiments"                    # where `check` looks for RAW.json files


def die(msg: str, fix: str) -> None:
    raise SystemExit(f"error: {msg}. Fix: {fix}")


def git(*args: str, root: Path = ROOT, binary: bool = False) -> str | bytes:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=not binary)
    if r.returncode != 0:
        err = r.stderr if not binary else r.stderr.decode(errors="replace")
        die(f"git {' '.join(args[:3])} failed: {err.strip()}", "run it from a clone of the repository")
    return r.stdout


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def raw_paths(run: Path, all_dirs: bool) -> list[Path]:
    """The raw parts of a run: every subdirectory, except that a `scoring*` one keeps its own
    files and gives up only its subdirectories (the grader's transcripts)."""
    out = []
    for child in sorted(p for p in run.iterdir() if p.is_dir()):
        if not all_dirs and child.name.startswith("scoring"):
            out += sorted(p for p in child.iterdir() if p.is_dir())
        else:
            out.append(child)
    return out


def cmd_split(a: argparse.Namespace, root: Path = ROOT) -> None:
    run = Path(a.run)
    if (run / RAW).exists():
        die(f"{run / RAW} exists: this run is split", "restore it first if it must be split again")
    commit = git("rev-parse", a.commit, root=root).strip()
    raw = {}
    for p in raw_paths(run, a.all_dirs):
        r = rel(p, root)
        raw[rel(p, run)] = git("rev-parse", f"{commit}:{r}", root=root).strip()
    if not raw:
        die(f"{run} has no raw directory", "name a run directory with arm or world outputs")
    (run / RAW).write_text(json.dumps({"source_commit": commit, "raw": raw}, indent=2) + "\n")
    (run / ".gitignore").write_text("# Raw records, kept in git history only (ADR-0055); restore with\n"
                                    f"# python tools/run_archive.py restore {rel(run, root)}\n"
                                    + "".join(f"/{p}/\n" for p in raw))
    git("rm", "-r", "-q", "--cached", *[rel(run / p, root) for p in raw], root=root)
    print(f"{len(raw)} raw directories of {rel(run, root)} left the tree; they stay at {commit[:12]}")


def load_raw(run: Path) -> dict:
    try:
        m = json.loads((run / RAW).read_text())
    except (OSError, ValueError):
        die(f"cannot read {run / RAW}", "give a run directory that `split` wrote")
    if not isinstance(m.get("source_commit"), str) or not isinstance(m.get("raw"), dict) or not m["raw"]:
        die(f"{run / RAW} is not a split record", "give a run directory that `split` wrote")
    return m


def cmd_restore(a: argparse.Namespace, root: Path = ROOT) -> None:
    run = Path(a.run)
    m = load_raw(run)
    todo = [p for p in m["raw"] if not (run / p).exists()]
    for p in todo:
        full = f"{rel(run, root)}/{p}"
        tree = git("rev-parse", f"{m['source_commit']}:{full}", root=root).strip()
        if tree != m["raw"][p]:
            die(f"{full} at {m['source_commit'][:12]} is tree {tree[:12]}, not the recorded {m['raw'][p][:12]}",
                "fetch the full history (`git fetch --unshallow`) and check that RAW.json is unchanged")
        data = git("archive", "--format=tar", m["source_commit"], full, root=root, binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            t.extractall(root, filter="data")
    print(f"restored {len(todo)} of {len(m['raw'])} raw directories of {rel(run, root)}"
          + ("" if todo else " (all were present)"))


def cmd_check(a: argparse.Namespace, root: Path = ROOT) -> None:
    problems = []
    for f in sorted((root / RUNS).rglob(RAW)):
        run = f.parent
        m = load_raw(run)
        for p in m["raw"]:
            r = f"{rel(run, root)}/{p}"
            if git("ls-files", "--", r, root=root).strip():
                problems.append(f"{r} is tracked again. Fix: `git rm -r --cached {r}`; it stays in history (ADR-0055)")
            if subprocess.run(["git", "check-ignore", "-q", f"{r}/x"], cwd=root).returncode != 0:
                problems.append(f"{r} is not ignored. Fix: keep `/{p}/` in {rel(run, root)}/.gitignore")
    for p in problems:
        print(f"error: {p}")
    if problems:
        raise SystemExit(1)
    print("run records: every raw path is outside the tree")


# --- archives for records never committed ---

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_pack(a: argparse.Namespace) -> None:
    src = Path(a.dir)
    files = sorted(p for p in src.rglob("*") if p.is_file())
    if not files:
        die(f"{src} has no files", "give the run directory with its raw records")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as t:
        for p in files:
            info = tarfile.TarInfo(rel(p, src))
            info.size, info.mtime, info.mode, info.uid, info.gid = p.stat().st_size, 0, 0o644, 0, 0
            with p.open("rb") as f:
                t.addfile(info, f)
    out = Path(a.out)
    with out.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue())
    manifest = {"archive": out.name, "sha256": sha256_file(out), "url": a.url or "",
                "files": {rel(p, src): sha256_file(p) for p in files}}
    Path(a.manifest).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{out}: {len(files)} files, sha256 {manifest['sha256']}; commit {a.manifest}, upload {out.name} "
          "as a release asset and set its `url`")


def cmd_fetch(a: argparse.Namespace) -> None:
    m = json.loads(Path(a.manifest).read_text())
    if a.file:
        data = Path(a.file).read_bytes()
    elif m.get("url"):
        with urllib.request.urlopen(m["url"], timeout=300) as r:
            data = r.read()
    else:
        die(f"{a.manifest} has no `url`", "give the archive with --file, or set its release asset URL")
    if hashlib.sha256(data).hexdigest() != m["sha256"]:
        die("the archive's sha256 differs from the manifest", "fetch the asset the manifest names, unchanged")
    into = Path(a.into)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        t.extractall(into, filter="data")
    bad = [f for f, h in m["files"].items() if not (into / f).is_file() or sha256_file(into / f) != h]
    if bad:
        die(f"{len(bad)} file(s) differ from the manifest, e.g. {bad[0]}", "fetch the archive again")
    print(f"{len(m['files'])} files in {into}, every hash as recorded")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="run_archive", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split"); s.add_argument("run"); s.add_argument("--all-dirs", action="store_true")
    s.add_argument("--commit", default="HEAD"); s.set_defaults(f=cmd_split)
    s = sub.add_parser("restore"); s.add_argument("run"); s.set_defaults(f=cmd_restore)
    s = sub.add_parser("check"); s.set_defaults(f=cmd_check)
    s = sub.add_parser("pack"); s.add_argument("dir"); s.add_argument("--out", required=True)
    s.add_argument("--manifest", required=True); s.add_argument("--url"); s.set_defaults(f=cmd_pack)
    s = sub.add_parser("fetch"); s.add_argument("manifest"); s.add_argument("--into", required=True)
    s.add_argument("--file"); s.set_defaults(f=cmd_fetch)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    sys.exit(main())

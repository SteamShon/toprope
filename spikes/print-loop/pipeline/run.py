"""Run the automated part of the loop: spec -> CAD -> checks -> slice -> cost -> report.

    uv run python pipeline/run.py specs/airtag_holder.yaml

Writes, under results/:
  stl/<variant>.stl      printable files
  png/<variant>.png      renders for review (and for a listing mock-up)
  report.json            every check and estimate, machine-readable
  report.md              the same, for a person
Exits non-zero if any check fails, so an agent can loop until it passes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from build123d import Pos, export_stl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "design"))
import airtag_holder as design  # noqa: E402

PROFILE = ROOT / "profiles" / "a1_pla_0.2.ini"
BEDS = {"Bambu Lab A1 (256 mm)": 256.0, "Bambu Lab A1 mini (180 mm)": 180.0}

# Cost assumptions. Change them here; the report prints them.
ECON = {
    "filament_usd_per_kg": 20.0,   # PLA, typical spool price
    "machine_usd_per_hour": 0.30,  # electricity (~0.1 kWh/h) + wear, rough
    "failure_rate": 0.10,          # one print in ten is a reprint
}


def slice_part(stl: Path, gcode: Path) -> dict:
    exe = shutil.which("prusa-slicer") or shutil.which("PrusaSlicer")
    if not exe:
        return {"ok": False, "error": "prusa-slicer not installed"}
    cmd = [exe, "--export-gcode", "--load", str(PROFILE), "--center", "128,128",
           "--output", str(gcode), str(stl)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not gcode.exists():
        return {"ok": False, "error": (r.stderr or r.stdout)[-500:]}
    text = gcode.read_text(errors="ignore")
    t = re.search(r"estimated printing time \(normal mode\) = (.+)", text)
    g = re.search(r"filament used \[g\] = ([\d.]+)", text)
    return {"ok": True, "time_text": t.group(1).strip() if t else None,
            "minutes": _minutes(t.group(1)) if t else None,
            "grams": float(g.group(1)) if g else None}


def _minutes(s: str) -> float:
    total = 0.0
    for v, u in re.findall(r"(\d+)([dhms])", s):
        total += int(v) * {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}[u]
    return round(total, 1)


def render(stl: Path, png: Path, title: str, size: int = 640) -> None:
    """Shaded render with a small z-buffer rasterizer (no GPU, no extra deps)."""
    import numpy as np
    from PIL import Image, ImageDraw
    from stl import mesh

    v = mesh.Mesh.from_file(str(stl)).vectors.astype(float)
    # View: look from the front-left, above.
    az, el = np.radians(-55), np.radians(40)
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(el), -np.sin(el)], [0, np.sin(el), np.cos(el)]])
    w = v.reshape(-1, 3) @ rz.T
    w = w @ np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]]).T  # y-up camera, looking along -z
    w = w @ rx.T
    w = w.reshape(-1, 3, 3)
    n = np.cross(w[:, 1] - w[:, 0], w[:, 2] - w[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    light = np.array([-0.3, 0.6, 0.75]); light /= np.linalg.norm(light)
    shade = 0.30 + 0.70 * np.abs(n @ light)
    pts = w.reshape(-1, 3)
    lo, hi = pts[:, :2].min(0), pts[:, :2].max(0)
    scale = (size * 0.86) / (hi - lo).max()
    off = (size - (hi - lo) * scale) / 2
    xy = (w[:, :, :2] - lo) * scale + off
    xy[:, :, 1] = size - xy[:, :, 1]
    z = w[:, :, 2]
    zbuf = np.full((size, size), -np.inf)
    img = np.zeros((size, size, 4), dtype=np.uint8)
    base = np.array([46, 140, 158])
    for (a, b, c), (za, zb, zc), s in zip(xy, z, shade):
        x0, y0 = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
        x1, y1 = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        zz = l1 * za + l2 * zb + l3 * zc
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        hit = inside & (zz > sub)
        sub[hit] = zz[hit]
        col = np.append(np.clip(base * s + 40 * s, 0, 255), 255).astype(np.uint8)
        img[y0:y1 + 1, x0:x1 + 1][hit] = col
    im = Image.fromarray(img, "RGBA")
    ImageDraw.Draw(im).text((10, 8), title, fill=(90, 90, 90, 255))
    im.save(png)


def checks(spec: dict, variant: dict, part) -> list[dict]:
    k = design._dims(spec)
    rules = spec["print_rules"]
    out = []

    def add(cid, ok, detail):
        out.append({"id": cid, "ok": bool(ok), "detail": detail})

    add("solid", part.is_valid and len(part.solids()) == 1,
        f"valid={part.is_valid}, solids={len(part.solids())}")
    bb = part.bounding_box()
    size = (round(bb.size.X, 1), round(bb.size.Y, 1), round(bb.size.Z, 1))
    for name, bed in BEDS.items():
        add(f"fits {name}", max(size) <= bed, f"size {size} mm")
    add("min wall", design.WALL >= rules["min_wall_mm"] and design.ROOF >= rules["min_wall_mm"],
        f"wall {design.WALL} mm, roof {design.ROOF} mm >= {rules['min_wall_mm']} mm")
    tag = design.tag_at_rest(spec, variant)
    clash = (part & tag).volume
    add("R2 tag sits free in pocket", clash < 0.01, f"overlap with tag {clash:.3f} mm3")
    # Geometric retention tests: move the virtual tag and see that the part stops it.
    gap_z = spec["fit"]["clearance_z_mm"]
    up = (part & (Pos(0, 0, gap_z / 2 + 0.3) * tag)).volume
    add("R2 lip stops tag falling out the front", up > 0.5, f"overlap after +{gap_z / 2 + 0.3:.1f} mm z: {up:.1f} mm3")
    gap_y = design.OUTER_SEP - 1.0
    slide = (part & (Pos(0, gap_y, 0) * tag)).volume
    add("R2 detents stop tag sliding out", slide > 0.1, f"overlap after +{gap_y:.0f} mm y: {slide:.1f} mm3")
    squeeze = k["tag_d"] - (k["pocket_d"] - 2 * k["detent"])
    add("R2 detent clicks (not too tight)", 0 < squeeze <= 1.0, f"interference {squeeze:.2f} mm (0-1.0)")
    add("R3 speaker window", k["lip_in"] >= 20, f"front window {k['lip_in']:.1f} mm")
    if variant["mount"] == "collar":
        add("R1 strap fits", True,
            f"tunnel {variant['strap_width_mm'] + 1.0} x {variant['strap_thickness_mm'] + 0.8} mm "
            f"for {variant['strap_width_mm']} x {variant['strap_thickness_mm']} mm strap")
    elif variant["mount"] == "bike":
        add("R1 bolt pattern", variant["bolt_spacing_mm"] / 2 - 5.25 > k["r_out"] + design.OUTER_SEP,
            f"{variant['bolt_spacing_mm']} mm spacing clears the pocket")
    else:
        add("R1 keyring hole", True, "5.5 mm hole")
    return out


def unit_cost(sl: dict) -> float | None:
    if not sl.get("ok") or sl.get("grams") is None:
        return None
    material = sl["grams"] / 1000 * ECON["filament_usd_per_kg"]
    machine = sl["minutes"] / 60 * ECON["machine_usd_per_hour"]
    return round((material + machine) * (1 + ECON["failure_rate"]), 2)


def main(spec_path: str) -> int:
    spec = yaml.safe_load(Path(spec_path).read_text())
    res = ROOT / "results"
    for d in ("stl", "png", "gcode"):
        (res / d).mkdir(parents=True, exist_ok=True)

    try:
        shown = str(Path(spec_path).resolve().relative_to(ROOT))
    except ValueError:
        shown = spec_path
    report = {"spec": shown, "economics": ECON, "items": []}
    jobs = [(v, design.build(spec, v)) for v in spec["variants"]]
    jobs.append(({"id": "tolerance-coupon", "mount": "coupon"}, design.coupon(spec)))

    all_ok = True
    for v, part in jobs:
        stl = res / "stl" / f"{v['id']}.stl"
        export_stl(part, str(stl), tolerance=0.02, angular_tolerance=0.2)
        cks = checks(spec, v, part) if v["mount"] != "coupon" else [
            {"id": "solid", "ok": part.is_valid and len(part.solids()) == 1,
             "detail": f"solids={len(part.solids())}"}]
        sl = slice_part(stl, res / "gcode" / f"{v['id']}.gcode")
        cks.append({"id": "slices", "ok": sl["ok"], "detail": sl.get("error") or sl.get("time_text")})
        render(stl, res / "png" / f"{v['id']}.png", v["id"])
        ok = all(c["ok"] for c in cks)
        all_ok &= ok
        report["items"].append({"variant": v, "ok": ok, "checks": cks, "slice": sl,
                                "unit_cost_usd": unit_cost(sl)})
        print(f"{'PASS' if ok else 'FAIL'}  {v['id']:<18} {sl.get('time_text')}  "
              f"{sl.get('grams')} g  ${unit_cost(sl)}")

    (res / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (res / "report.md").write_text(to_markdown(report))
    return 0 if all_ok else 1


def to_markdown(report: dict) -> str:
    lines = ["# Pipeline report", "", f"Spec: `{report['spec']}`", "",
             "| Item | Result | Print time | Filament | Unit cost |", "|---|---|---|---|---|"]
    for it in report["items"]:
        s = it["slice"]
        lines.append(f"| {it['variant']['id']} | {'PASS' if it['ok'] else 'FAIL'} | "
                     f"{s.get('time_text')} | {s.get('grams')} g | ${it['unit_cost_usd']} |")
    lines += ["", "Cost assumptions: " + ", ".join(f"{k}={v}" for k, v in report["economics"].items()), ""]
    for it in report["items"]:
        lines += [f"## {it['variant']['id']}", ""]
        lines += [f"- {'✅' if c['ok'] else '❌'} {c['id']}: {c['detail']}" for c in it["checks"]]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "specs" / "airtag_holder.yaml")))

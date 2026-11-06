"""Parametric AirTag holder, generated from specs/airtag_holder.yaml.

Every dimension comes from the spec, so a new variant (another strap width, another
name) is a new YAML entry, not new code. The part prints flat, back plate on the bed,
with no supports.

Coordinates: the tag pocket is centred on the origin, the bed is z=0, and the tag
slides in and out along +y.
"""

from __future__ import annotations

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Circle,
    Cylinder,
    Locations,
    Mode,
    Part,
    Plane,
    Pos,
    Rectangle,
    SlotCenterToCenter,
    RectangleRounded,
    Text,
    add,
    extrude,
)

WALL = 2.0          # ring wall around the pocket
LIP = 1.2           # front lip thickness (6 layers)
BACK = 2.0          # back plate thickness for keyring variant
TEXT_H = 0.6        # raised label height (3 layers)
FLOOR = 0.6         # material under a strap tunnel
ROOF = 1.2          # material over a strap tunnel


def _dims(spec: dict) -> dict:
    tag, fit = spec["host_product"], spec["fit"]
    d = tag["diameter_mm"] + fit["clearance_mm"]
    h = tag["height_mm"] + fit["clearance_z_mm"]
    return {
        "tag_d": tag["diameter_mm"],
        "tag_h": tag["height_mm"],
        "pocket_d": d,
        "pocket_h": h,
        "r_out": d / 2 + WALL,
        "lip_in": d - 2 * fit["lip_overlap_mm"],
        "detent": fit["detent_mm"],
    }


OUTER_SEP = 8.0      # how far the straight rails of the U run past the pocket centre


def _outer(r: float, s_o: float):
    """Outline of the holder body: a circle around the pocket with straight rails that
    end flat at y = s_o (a rounded end would leave thin, fragile horns)."""
    with BuildSketch() as sk:
        with Locations((0, s_o)):
            SlotCenterToCenter(2 * s_o, 2 * r, rotation=90)
        with Locations((0, (s_o - r - 1) / 2)):
            Rectangle(2 * r + 2, s_o + r + 1, mode=Mode.INTERSECT)
    return sk.sketch


def _channel(width: float, r: float, s_o: float):
    """Pocket or lip opening: round at the bottom, open through the +y end."""
    sep = 2 * (s_o + r + 2)
    with BuildSketch() as sk:
        with Locations((0, sep / 2)):
            SlotCenterToCenter(sep, width, rotation=90)
    return sk.sketch


def plate_thickness(variant: dict) -> float:
    if variant["mount"] == "collar":
        return FLOOR + variant["strap_thickness_mm"] + 0.8 + ROOF
    if variant["mount"] == "bike":
        return 4.5
    return BACK


def build(spec: dict, variant: dict) -> Part:
    k = _dims(spec)
    r = k["r_out"]
    t = plate_thickness(variant)
    label = variant.get("label", "")
    label_len = 11.0 if label else 0.0
    top = t + k["pocket_h"] + LIP

    s_o = OUTER_SEP
    # 2D outlines are made before the part, outside any builder, then added.
    outer = _outer(r, s_o)
    pocket = _channel(k["pocket_d"], r, s_o)
    window = _channel(k["lip_in"], r, s_o)
    with BuildPart() as p:
        # 1. Back plate, shaped by the mount type. Every outline is drawn in 2D and
        #    extruded: 3D booleans between tangent faces are unreliable in OCC.
        with BuildSketch():
            add(outer)
            if variant["mount"] == "keyring":
                tab_len = label_len + 12.0
                with Locations((0, -r - tab_len / 2 + 2)):
                    RectangleRounded(2 * r if label else 14.0, tab_len + 4, 4.0)
            elif variant["mount"] == "collar":
                h = max(2 * r, variant["strap_width_mm"] + 2 * WALL + 4) + label_len
                with Locations((0, -label_len / 2)):
                    RectangleRounded(2 * r, h, 4.0)
            elif variant["mount"] == "bike":
                RectangleRounded(2 * r, variant["bolt_spacing_mm"] + 14.0, 4.0)
        extrude(amount=t)

        # 2. U-shaped wall: outer outline minus the pocket, which runs out through +y
        #    so the tag slides in and out.
        with BuildSketch(Plane.XY.offset(t)):
            add(outer)
            add(pocket, mode=Mode.SUBTRACT)
        extrude(amount=k["pocket_h"])

        # 3. Front lip: holds the tag in; its opening is the speaker window.
        with BuildSketch(Plane.XY.offset(t + k["pocket_h"])):
            add(outer)
            add(window, mode=Mode.SUBTRACT)
        extrude(amount=LIP)

        # 4. Detents near the slot mouth: the tag clicks past them.
        dz = k["pocket_h"] * 0.6
        for sx in (-1, 1):
            x = sx * (k["pocket_d"] / 2 - k["detent"] / 2 + 0.1)
            with Locations(Pos(x, s_o - 1.0, t)):
                Box(k["detent"] + 0.2, 1.5, dz, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 5. Mount features.
        if variant["mount"] == "keyring":
            y_hole = -r - label_len - 6.0
            with Locations(Pos(0, y_hole, 0)):
                Cylinder(2.75, t, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        if variant["mount"] in ("keyring", "bike"):
            # Back window: lighter part, and the speaker is not boxed in.
            Cylinder((k["pocket_d"] - 10) / 2, t,
                     align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        if variant["mount"] == "collar":
            tunnel_h = variant["strap_thickness_mm"] + 0.8
            with Locations(Pos(0, 0, FLOOR)):
                Box(2 * r + 2, variant["strap_width_mm"] + 1.0, tunnel_h,
                    align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        if variant["mount"] == "bike":
            s = variant["bolt_spacing_mm"] / 2
            for y in (-s, s):
                with Locations(Pos(0, y, 0)):
                    Cylinder(variant["bolt_diameter_mm"] / 2 + 0.25, t,
                             align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
                with Locations(Pos(0, y, t - 3.0)):
                    Cylinder(5.25, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN),
                             mode=Mode.SUBTRACT)

        # 6. Raised label on the plate below the pocket.
        if label:
            with BuildSketch(Pos(0, -r - label_len / 2 + 0.5, t)):
                Text(label, font_size=7.0)
            extrude(amount=TEXT_H)

    part = p.part
    part.label = variant["id"]
    part.top_z = top  # type: ignore[attr-defined]
    return part


def tag_at_rest(spec: dict, variant: dict) -> Part:
    """The tag as a plain cylinder, sitting in the pocket. Used by the fit check."""
    k = _dims(spec)
    z = plate_thickness(variant) + (k["pocket_h"] - k["tag_h"]) / 2
    return Pos(0, 0, z) * Cylinder(k["tag_d"] / 2, k["tag_h"],
                                   align=(Align.CENTER, Align.CENTER, Align.MIN))


def coupon(spec: dict, clearances=(0.2, 0.3, 0.4, 0.5, 0.6)) -> Part:
    """Tolerance coupon: shallow rings, one per clearance. Print it before anything else."""
    tag_d = spec["host_product"]["diameter_mm"]
    pitch = tag_d + 0.6 + 2 * 1.2 + 3.0
    n = len(clearances)
    base = 1.0
    with BuildPart() as p:
        with BuildSketch():
            Rectangle(n * pitch + 4, pitch + 10)
        extrude(amount=base)
        for i, c in enumerate(clearances):
            x = (i - (n - 1) / 2) * pitch
            d = tag_d + c
            with Locations(Pos(x, 3, base)):
                Cylinder(d / 2 + 1.2, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
                Cylinder(d / 2, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
            with BuildSketch(Pos(x, -pitch / 2 + 1, base)):
                Text(f"{c:.1f}", font_size=5.0)
            extrude(amount=TEXT_H)
    part = p.part
    part.label = "tolerance-coupon"
    return part

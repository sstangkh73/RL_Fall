"""Build the v1.0 SMPL-topology humanoid MJCF from configs/research/body_v1_0_female.json.

24 bodies (pelvis root + 23 children) with three hinge joints each (x, y, z) = 69 DoF.
Segment masses, centre-of-mass positions and inertias come from de Leva (1996)
scaled to the reference person; collision shapes from ANSUR II; joint ranges from
the spec. Run from the repository root:

  python scripts/build_body_v1.py   # writes assets/body_v1_0_female.xml
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "configs" / "research" / "body_v1_0_female.json"
OUTPUT = ROOT / "assets" / "body_v1_0_female.xml"
AXES = {"x": "1 0 0", "y": "0 1 0", "z": "0 0 1"}


def fmt(*values: float) -> str:
    return " ".join(f"{value:.5g}" for value in values)


def inertial(spec: dict, segment: str, mass_kg: float, com: tuple[float, float, float],
             long_axis: str = "z") -> str:
    seg = spec["segments"][segment]
    length = seg["length_m"]
    sag, trans, long_ = (mass_kg * (r * length) ** 2 for r in seg["r"])
    # de Leva radii: sagittal = about the antero-posterior axis (x), transverse =
    # about the medio-lateral axis (y), longitudinal = about the segment axis.
    if long_axis == "z":
        diag = (sag, trans, long_)
    else:  # foot segments lie along x
        diag = (long_, trans, sag)
    return f'<inertial pos="{fmt(*com)}" mass="{mass_kg:.5g}" diaginertia="{fmt(*diag)}"/>'


def joints(spec: dict, segment: str, name: str, side: str) -> list[str]:
    rom = spec["joint_rom_deg"][segment]
    lines = []
    for axis in ("x", "y", "z"):
        low, high = rom[axis]
        if side == "R" and axis in ("x", "z"):  # mirror the left-side ranges
            low, high = -high, -low
        lines.append(
            f'<joint name="{name}_{axis}" type="hinge" axis="{AXES[axis]}" '
            f'range="{math.radians(low):.4f} {math.radians(high):.4f}"/>'
        )
    return lines


def build(spec: dict) -> str:
    person = spec["reference_person"]
    mass = person["mass_kg"]
    seg = spec["segments"]
    geo = spec["geometry_m"]
    h = spec["landmark_heights_m"]
    lat = spec["lateral_offsets_m"]
    foot = spec["foot"]

    def m(segment: str) -> float:
        return seg[segment]["mass_frac"] * mass

    def length(segment: str) -> float:
        return seg[segment]["length_m"]

    def com_up(segment: str) -> tuple[float, float, float]:
        return (0.0, 0.0, seg[segment]["com_frac"] * length(segment))

    def com_down(segment: str) -> tuple[float, float, float]:
        return (0.0, 0.0, -seg[segment]["com_frac"] * length(segment))

    out: list[str] = []
    add = out.append

    def leg(side: str) -> None:
        sign = 1.0 if side == "L" else -1.0
        thigh, shank = length("Hip"), length("Knee")
        heel_to_ankle = foot["heel_to_ankle_m"]
        ball = foot["ball_length_m"]
        ankle_h = h["ankle_joint"]
        foot_half_len = ball / 2.0
        foot_center_x = ball / 2.0 - heel_to_ankle
        toe_len = foot["length_m"] - ball
        add(f'<body name="{side}_Hip" pos="0 {sign * lat["hip_joint_half_spacing"]:.4f} 0">')
        out.extend(joints(spec, "Hip", f"{side}_Hip", side))
        add(inertial(spec, "Hip", m("Hip"), com_down("Hip")))
        add(f'<geom name="{side}_thigh" type="capsule" fromto="0 0 0 0 0 {-thigh:.4f}" '
            f'size="{geo["thigh_radius"]}"/>')
        add(f'<body name="{side}_Knee" pos="0 0 {-thigh:.4f}">')
        out.extend(joints(spec, "Knee", f"{side}_Knee", side))
        add(inertial(spec, "Knee", m("Knee"), com_down("Knee")))
        add(f'<geom name="{side}_shank" type="capsule" '
            f'fromto="0 0 0 0 0 {-(shank - geo["shank_radius"]):.4f}" size="{geo["shank_radius"]}"/>')
        add(f'<body name="{side}_Ankle" pos="0 0 {-shank:.4f}">')
        out.extend(joints(spec, "Ankle", f"{side}_Ankle", side))
        add(inertial(spec, "Ankle", m("Ankle"),
                     (foot_center_x, 0.0, -ankle_h / 2.0), long_axis="x"))
        add(f'<geom name="{side}_foot" type="box" pos="{foot_center_x:.4f} 0 {-(ankle_h - 0.02):.4f}" '
            f'size="{foot_half_len:.4f} {foot["breadth_m"] / 2:.4f} 0.02"/>')
        toe_joint_z = -(ankle_h - 0.02)
        add(f'<body name="{side}_Toe" pos="{ball - heel_to_ankle:.4f} 0 {toe_joint_z:.4f}">')
        out.extend(joints(spec, "Toe", f"{side}_Toe", side))
        tb = geo["toe_box_half"]
        toe_center = (toe_len / 2.0, 0.0, -(0.02 - tb[2]))
        add(inertial(spec, "Toe", m("Toe"), toe_center, long_axis="x"))
        add(f'<geom name="{side}_toe_foot" type="box" pos="{fmt(*toe_center)}" '
            f'size="{toe_len / 2:.4f} {tb[1]} {tb[2]}"/>')
        add("</body></body></body></body>")

    def arm(side: str) -> None:
        sign = 1.0 if side == "L" else -1.0
        sc = lat["sternoclavicular_half_spacing"]
        thorax_z = h["suprasternale"] - 0.01 - h["xyphion"]
        to_shoulder_y = lat["shoulder_joint_half_spacing"] - sc
        to_shoulder_z = h["shoulder_joint"] - (h["suprasternale"] - 0.01)
        add(f'<body name="{side}_Thorax" pos="0 {sign * sc:.4f} {thorax_z:.4f}">')
        out.extend(joints(spec, "Thorax", f"{side}_Thorax", side))
        add(inertial(spec, "Thorax", m("Thorax"),
                     (0.0, sign * to_shoulder_y / 2, to_shoulder_z / 2)))
        add(f'<geom name="{side}_collar" type="capsule" '
            f'fromto="0 0 0 0 {sign * to_shoulder_y:.4f} {to_shoulder_z:.4f}" size="{geo["collar_radius"]}"/>')
        add(f'<body name="{side}_Shoulder" pos="0 {sign * to_shoulder_y:.4f} {to_shoulder_z:.4f}">')
        out.extend(joints(spec, "Shoulder", f"{side}_Shoulder", side))
        upper, fore = length("Shoulder"), length("Elbow")
        add(inertial(spec, "Shoulder", m("Shoulder"), com_down("Shoulder")))
        add(f'<geom name="{side}_upper_arm" type="capsule" fromto="0 0 0 0 0 {-upper:.4f}" '
            f'size="{geo["upper_arm_radius"]}"/>')
        add(f'<body name="{side}_Elbow" pos="0 0 {-upper:.4f}">')
        out.extend(joints(spec, "Elbow", f"{side}_Elbow", side))
        add(inertial(spec, "Elbow", m("Elbow"), com_down("Elbow")))
        add(f'<geom name="{side}_forearm" type="capsule" fromto="0 0 0 0 0 {-fore:.4f}" '
            f'size="{geo["forearm_radius"]}"/>')
        add(f'<body name="{side}_Wrist" pos="0 0 {-fore:.4f}">')
        out.extend(joints(spec, "Wrist", f"{side}_Wrist", side))
        palm = length("Wrist")
        add(inertial(spec, "Wrist", m("Wrist"), com_down("Wrist")))
        pb = geo["palm_box_half"]
        add(f'<geom name="{side}_palm" type="box" pos="0 0 {-palm / 2:.4f}" '
            f'size="{pb[1]} {pb[0]} {pb[2]}"/>')
        add(f'<body name="{side}_Hand" pos="0 0 {-palm:.4f}">')
        out.extend(joints(spec, "Hand", f"{side}_Hand", side))
        fingers = length("Hand")
        add(inertial(spec, "Hand", m("Hand"), com_down("Hand")))
        add(f'<geom name="{side}_fingers" type="capsule" '
            f'fromto="0 0 0 0 0 {-(fingers - geo["finger_radius"]):.4f}" size="{geo["finger_radius"]}"/>')
        add("</body></body></body></body></body>")

    pelvis_len = length("Pelvis")
    waist_len = length("Torso")
    chest_len = length("Chest")
    pb = geo["pelvis_box_half"]
    wb = geo["waist_box_half"]
    cb = geo["chest_box_half"]
    neck_len = h["head_joint"] - h["neck_base"]

    add('<mujoco model="rl_fall_v1_0_female">')
    add("<!-- Generated by scripts/build_body_v1.py from configs/research/body_v1_0_female.json;"
        " do not edit by hand. SMPL topology, de Leva female 1.60 m / 60 kg. -->")
    add('<compiler angle="radian" autolimits="true"/>')
    add('<option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast" iterations="50"/>')
    add("<default>")
    add('<joint damping="1.0" armature="0.01"/>')
    add('<geom friction="0.8 0.02 0.002" solref="0.02 1" solimp="0.9 0.95 0.001" '
        'contype="1" conaffinity="1" rgba="0.75 0.62 0.52 1"/>')
    add("</default>")
    add("<worldbody>")
    add('<geom name="floor" type="plane" size="20 20 0.1" rgba="0.25 0.28 0.30 1"/>')
    add(f'<body name="Pelvis" pos="0 0 {h["hip_joint"] + 0.002:.4f}">')
    add('<freejoint name="root"/>')
    add(inertial(spec, "Pelvis", m("Pelvis"), com_up("Pelvis")))
    add(f'<geom name="pelvis" type="box" pos="0 0 {pb[2]:.4f}" size="{fmt(*pb)}"/>')
    leg("L")
    leg("R")
    add(f'<body name="Torso" pos="0 0 {pelvis_len:.4f}">')
    out.extend(joints(spec, "Torso", "Torso", "L"))
    add(inertial(spec, "Torso", m("Torso"), com_up("Torso")))
    add(f'<geom name="torso" type="box" pos="0 0 {waist_len / 2:.4f}" size="{wb[0]} {wb[1]} {waist_len / 2:.4f}"/>')
    add(f'<body name="Spine" pos="0 0 {waist_len:.4f}">')
    out.extend(joints(spec, "Spine", "Spine", "L"))
    add(inertial(spec, "Spine", m("Spine"), com_up("Spine")))
    add(f'<geom name="spine" type="box" pos="0 0 {waist_len / 2:.4f}" size="{wb[0]} {wb[1]} {waist_len / 2:.4f}"/>')
    add(f'<body name="Chest" pos="0 0 {waist_len:.4f}">')
    out.extend(joints(spec, "Chest", "Chest", "L"))
    add(inertial(spec, "Chest", m("Chest"), com_up("Chest")))
    add(f'<geom name="chest" type="box" pos="0 0 {chest_len / 2:.4f}" size="{cb[0]} {cb[1]} {chest_len / 2:.4f}"/>')
    add(f'<body name="Neck" pos="0 0 {h["neck_base"] - h["xyphion"]:.4f}">')
    out.extend(joints(spec, "Neck", "Neck", "L"))
    add(inertial(spec, "Neck", m("Neck"), (0.0, 0.0, neck_len / 2)))
    add(f'<geom name="neck" type="capsule" fromto="0 0 0 0 0 {neck_len:.4f}" size="{geo["neck_radius"]}"/>')
    add(f'<body name="Head" pos="0 0 {neck_len:.4f}">')
    out.extend(joints(spec, "Head", "Head", "L"))
    head_com = h["vertex"] - h["head_joint"] - geo["head_ellipsoid"][2]
    add(inertial(spec, "Head", m("Head"), (0.0, 0.0, head_com)))
    add(f'<geom name="head" type="ellipsoid" pos="0 0 {head_com:.4f}" size="{fmt(*geo["head_ellipsoid"])}"/>')
    add("</body></body>")
    arm("L")
    arm("R")
    add("</body></body></body></body>")
    add("</worldbody>")
    # Rest-pose overlaps only (arms hang beside the chest; collars meet the neck).
    add("<contact>")
    for side in ("L", "R"):
        for body in ("Chest", "Neck", "R_Thorax" if side == "L" else "L_Thorax"):
            add(f'<exclude body1="{side}_Thorax" body2="{body}"/>')
        for body in ("Chest", "Spine"):
            add(f'<exclude body1="{side}_Shoulder" body2="{body}"/>')
    add("</contact>")
    add("</mujoco>")
    return "\n".join(out) + "\n"


def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    OUTPUT.write_text(build(spec), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

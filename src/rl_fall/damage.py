"""Persistent engineering damage proxy and functional impairment rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

PARTS = (
    "head",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
)
PART_INDEX = {name: index for index, name in enumerate(PARTS)}


@dataclass(frozen=True)
class DamageParameters:
    """Locked development parameters; loads are contact-force proxies in newtons."""

    threshold_n: Mapping[str, float] = field(
        default_factory=lambda: {name: 250.0 for name in PARTS}
    )
    rate_per_second: float = 0.12
    exponent: float = 2.0


class DamageModel:
    def __init__(self, parameters: DamageParameters | None = None) -> None:
        self.parameters = parameters or DamageParameters()
        self.damage = np.zeros(len(PARTS), dtype=np.float64)

    def reset(self, values: np.ndarray | None = None) -> np.ndarray:
        if values is None:
            self.damage.fill(0.0)
        else:
            values = np.asarray(values, dtype=np.float64)
            if values.shape != self.damage.shape:
                raise ValueError(f"damage must have shape {self.damage.shape}")
            self.damage[:] = np.clip(values, 0.0, 1.0)
        return self.damage.copy()

    def update(self, loads_n: Mapping[str, float], dt: float) -> np.ndarray:
        """Accumulate damage once for a physical duration, making frequency explicit."""
        before = self.damage.copy()
        for name, index in PART_INDEX.items():
            threshold = self.parameters.threshold_n[name]
            load = max(0.0, float(loads_n.get(name, 0.0)))
            excess_ratio = max(0.0, load / threshold - 1.0)
            increment = (
                self.parameters.rate_per_second
                * excess_ratio**self.parameters.exponent
                * float(dt)
            )
            self.damage[index] = min(1.0, self.damage[index] + increment)
        return self.damage - before

    @property
    def health(self) -> np.ndarray:
        return 1.0 - self.damage


def apply_functional_limits(
    requested_torque: np.ndarray,
    base_limits: np.ndarray,
    damage: np.ndarray,
    impairment_enabled: bool,
    joint_parts: tuple[str, ...] | None = None,
) -> np.ndarray:
    """Apply limb torque loss, then the torso's normalized total-actuation budget."""
    requested = np.asarray(requested_torque, dtype=np.float64)
    limits = np.asarray(base_limits, dtype=np.float64)
    damage = np.asarray(damage, dtype=np.float64)
    if requested.ndim != 1 or limits.shape != requested.shape or damage.shape != (6,):
        raise ValueError("expected matching 1-D torque/limits and damage shape (6,)")

    if joint_parts is None:
        joint_parts = (
            "left_arm", "left_arm", "right_arm", "right_arm",
            "left_leg", "left_leg", "right_leg", "right_leg",
        )
    if len(joint_parts) != len(requested):
        raise ValueError("joint_parts length must match torque length")
    if any(part not in PART_INDEX for part in joint_parts):
        raise ValueError("joint_parts contains an unknown damage part")

    if not impairment_enabled:
        return np.clip(requested, -limits, limits)

    effective_limits = limits.copy()
    for joint, part in enumerate(joint_parts):
        effective_limits[joint] *= 1.0 - damage[PART_INDEX[part]]
    torque = np.clip(requested, -effective_limits, effective_limits)

    torso_budget = 1.0 - damage[PART_INDEX["torso"]]
    normalized_sum = float(np.sum(np.abs(torque) / limits))
    max_normalized_sum = torso_budget * len(torque)
    if normalized_sum > max_normalized_sum and normalized_sum > 0.0:
        torque *= max_normalized_sum / normalized_sum
    return torque


def target_sensor(
    relative_target: np.ndarray,
    head_damage: float,
    impairment_enabled: bool,
    rng: np.random.Generator,
) -> tuple[np.ndarray, float]:
    """Return target data and an explicit validity bit; invalid data is all zero."""
    dropout_probability = float(np.clip(head_damage, 0.0, 1.0)) if impairment_enabled else 0.0
    valid = float(rng.random() >= dropout_probability)
    sensed = np.asarray(relative_target, dtype=np.float32) * valid
    return sensed, valid

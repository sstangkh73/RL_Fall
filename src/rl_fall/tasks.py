"""Alternating locomotion/reach task generator with independent randomness."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MOVE = 0
REACH = 1


@dataclass(frozen=True)
class TaskParameters:
    move_tolerance_m: float = 0.10
    reach_tolerance_m: float = 0.08
    hold_seconds: float = 0.40
    shaping_scale: float = 0.20


class AlternatingTask:
    def __init__(self, control_dt: float, rng: np.random.Generator,
                 parameters: TaskParameters | None = None) -> None:
        self.control_dt = float(control_dt)
        self.rng = rng
        self.parameters = parameters or TaskParameters()
        self.kind = MOVE
        self.target = np.zeros(2, dtype=np.float64)
        self.hold_steps = 0
        self.successes = 0

    @property
    def required_hold_steps(self) -> int:
        return round(self.parameters.hold_seconds / self.control_dt)

    def reset(self, torso_xz: np.ndarray) -> None:
        self.kind = MOVE
        self.hold_steps = 0
        self.successes = 0
        self._sample_target(np.asarray(torso_xz, dtype=np.float64))

    def _sample_target(self, torso_xz: np.ndarray) -> None:
        direction = self.rng.choice(np.array([-1.0, 1.0]))
        if self.kind == MOVE:
            offset = direction * self.rng.uniform(0.25, 0.55)
            self.target[:] = (torso_xz[0] + offset, 0.0)
        else:
            self.target[:] = (
                torso_xz[0] + direction * self.rng.uniform(0.18, 0.38),
                torso_xz[1] + self.rng.uniform(0.05, 0.40),
            )

    def distance(self, torso_xz: np.ndarray, hand_xz: np.ndarray) -> float:
        if self.kind == MOVE:
            return abs(float(torso_xz[0] - self.target[0]))
        distances = np.linalg.norm(hand_xz - self.target[None, :], axis=1)
        return float(np.min(distances))

    def advance(self, torso_xz: np.ndarray, hand_xz: np.ndarray) -> tuple[float, bool]:
        distance = self.distance(torso_xz, hand_xz)
        tolerance = (
            self.parameters.move_tolerance_m
            if self.kind == MOVE
            else self.parameters.reach_tolerance_m
        )
        self.hold_steps = self.hold_steps + 1 if distance <= tolerance else 0
        success = self.hold_steps >= self.required_hold_steps
        if success:
            self.successes += 1
            self.kind = REACH if self.kind == MOVE else MOVE
            self.hold_steps = 0
            self._sample_target(np.asarray(torso_xz, dtype=np.float64))
        return distance, success

    def kind_one_hot(self) -> np.ndarray:
        result = np.zeros(2, dtype=np.float32)
        result[self.kind] = 1.0
        return result


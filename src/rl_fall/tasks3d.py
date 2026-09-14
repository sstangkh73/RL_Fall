"""Three-dimensional alternating locomotion and reach tasks."""

from __future__ import annotations

import numpy as np

from .tasks import MOVE, REACH, TaskParameters


class SpatialAlternatingTask:
    def __init__(self, control_dt: float, rng: np.random.Generator,
                 parameters: TaskParameters | None = None) -> None:
        self.control_dt = float(control_dt)
        self.rng = rng
        self.parameters = parameters or TaskParameters()
        self.kind = MOVE
        self.target = np.zeros(3, dtype=np.float64)
        self.hold_steps = 0
        self.successes = 0

    @property
    def required_hold_steps(self) -> int:
        return round(self.parameters.hold_seconds / self.control_dt)

    def reset(self, torso_xyz: np.ndarray) -> None:
        self.kind = MOVE
        self.hold_steps = 0
        self.successes = 0
        self._sample_target(np.asarray(torso_xyz, dtype=np.float64))

    def _horizontal_offset(self, low: float, high: float) -> np.ndarray:
        angle = self.rng.uniform(-np.pi, np.pi)
        radius = self.rng.uniform(low, high)
        return radius * np.array([np.cos(angle), np.sin(angle)])

    def _sample_target(self, torso_xyz: np.ndarray) -> None:
        if self.kind == MOVE:
            self.target[:2] = torso_xyz[:2] + self._horizontal_offset(0.25, 0.55)
            self.target[2] = 0.0
        else:
            self.target[:2] = torso_xyz[:2] + self._horizontal_offset(0.18, 0.38)
            self.target[2] = torso_xyz[2] + self.rng.uniform(0.05, 0.40)

    def distance(self, torso_xyz: np.ndarray, hand_xyz: np.ndarray) -> float:
        if self.kind == MOVE:
            return float(np.linalg.norm(torso_xyz[:2] - self.target[:2]))
        return float(np.min(np.linalg.norm(hand_xyz - self.target[None, :], axis=1)))

    def advance(self, torso_xyz: np.ndarray, hand_xyz: np.ndarray) -> tuple[float, bool]:
        distance = self.distance(torso_xyz, hand_xyz)
        tolerance = (self.parameters.move_tolerance_m if self.kind == MOVE
                     else self.parameters.reach_tolerance_m)
        self.hold_steps = self.hold_steps + 1 if distance <= tolerance else 0
        success = self.hold_steps >= self.required_hold_steps
        if success:
            self.successes += 1
            self.kind = REACH if self.kind == MOVE else MOVE
            self.hold_steps = 0
            self._sample_target(np.asarray(torso_xyz, dtype=np.float64))
        return distance, success

    def kind_one_hot(self) -> np.ndarray:
        result = np.zeros(2, dtype=np.float32)
        result[self.kind] = 1.0
        return result

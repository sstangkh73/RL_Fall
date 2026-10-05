"""Watch a 3D policy: live MuJoCo viewer or an offscreen MP4/PNG recording.

Runs in its own process, so it never slows training. PATH may be a run directory
or any parent (e.g. results/stage1); the newest checkpoint*.zip under it is used,
and in live mode a newer checkpoint is picked up between episodes.

  python scripts/watch_policy.py results/stage1                # live viewer
  python scripts/watch_policy.py RUN_DIR --impulse 0.12        # fixed push size
  python scripts/watch_policy.py RUN_DIR --passive             # stance, no policy
  python scripts/watch_policy.py RUN_DIR --record s1.mp4 --episodes 4
Recording needs imageio (pip install "imageio[ffmpeg]").
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mujoco
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_fall.env3d import RLFall3DEnv

SEED_BASE = 20000  # disjoint from training and evaluation seeds
FRAME_EVERY = 2    # control steps per video frame (25 fps at 50 Hz control)


def newest_checkpoint(path: Path) -> Path:
    if path.is_file():
        return path
    candidates = list(path.rglob("checkpoint*.zip"))
    if not candidates:
        raise SystemExit(f"no checkpoint*.zip under {path}")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def normalizer_for(checkpoint: Path) -> Path:
    return checkpoint.with_name(checkpoint.stem.replace("checkpoint", "vecnormalize") + ".pkl")


def env_kwargs_for(checkpoint: Path) -> dict[str, object]:
    manifest = checkpoint.parent / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    return {
        "condition": data.get("condition", "A"),
        "body": data.get("body", "v0_2"),
        "mode": data.get("mode", "balance"),
        "max_push_impulse": float(data.get("max_push_impulse", 0.12)),
    }


def fix_impulse(env: RLFall3DEnv, impulse: float) -> None:
    mass = float(np.sum(env.model.body_mass))
    direction = env.push_force_world / max(float(np.linalg.norm(env.push_force_world)), 1e-9)
    env.push_force_world = impulse * mass * np.sqrt(9.81 * 1.2) / env.push_duration * direction
    env.push_impulse = impulse


class Episode:
    """One episode on a shared env, driven by a saved policy or the zero (stance) action."""

    def __init__(self, env: RLFall3DEnv, checkpoint: Path, seed: int,
                 impulse: float | None, passive: bool) -> None:
        self.env = env
        self.passive = passive
        if passive:
            self.observation = env.reset(seed=seed)[0]
        else:
            self.model = PPO.load(checkpoint, device="cpu")
            self.venv = VecNormalize.load(str(normalizer_for(checkpoint)),
                                          DummyVecEnv([lambda: env]))
            self.venv.training = False
            self.venv.seed(seed)
            self.observation = self.venv.reset()
        if impulse is not None:
            fix_impulse(env, impulse)
        self.final_qpos = env.data.qpos.copy()
        # Read now: the vec env auto-resets (and resamples the push) on termination.
        self.push_impulse, self.push_start = env.push_impulse, env.push_start
        self.info: dict[str, object] = {}
        self.done = False

    def step(self) -> None:
        if self.passive:
            _, _, terminated, truncated, self.info = self.env.step(
                np.zeros(self.env.action_space.shape, dtype=np.float32))
            self.done = terminated or truncated
        else:
            action, _ = self.model.predict(self.observation, deterministic=True)
            self.observation, _, done, infos = self.venv.step(action)
            self.info, self.done = infos[0], bool(done[0])
            if self.done:
                # DummyVecEnv auto-resets; show the terminal pose instead.
                self.env.data.qpos[:] = self.final_qpos
            else:
                self.final_qpos = self.env.data.qpos.copy()

    def summary(self) -> str:
        outcome = "FELL" if self.info.get("fallen") else "stood"
        seconds = int(self.info.get("elapsed_control_steps", 0)) * self.env.config.control_dt
        return (f"{outcome} after {seconds:.1f} s, push impulse "
                f"{self.push_impulse:.3f} at {self.push_start:.1f} s")


def tracking_camera(env: RLFall3DEnv, camera: mujoco.MjvCamera) -> None:
    camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
    camera.trackbodyid = env.torso_body_id
    camera.distance, camera.elevation, camera.azimuth = 2.6, -12.0, 135.0


def make_env(checkpoint: Path) -> RLFall3DEnv:
    env = RLFall3DEnv(seed=SEED_BASE, **env_kwargs_for(checkpoint))
    # Viewing only: brighter headlight; the asset has no lights of its own.
    env.model.vis.headlight.ambient[:] = 0.45
    env.model.vis.headlight.diffuse[:] = 0.75
    return env


def live(args: argparse.Namespace) -> None:
    import mujoco.viewer

    checkpoint = newest_checkpoint(args.path)
    env = make_env(checkpoint)
    with mujoco.viewer.launch_passive(env.model, env.data) as viewer:
        tracking_camera(env, viewer.cam)
        index = 0
        while viewer.is_running() and (args.episodes <= 0 or index < args.episodes):
            checkpoint = newest_checkpoint(args.path)  # follow training progress
            print(f"episode {index}: {'passive stance' if args.passive else checkpoint}")
            episode = Episode(env, checkpoint, SEED_BASE + index, args.impulse, args.passive)
            while viewer.is_running() and not episode.done:
                started = time.perf_counter()
                episode.step()
                viewer.sync()
                time.sleep(max(0.0, env.config.control_dt / args.speed
                               - (time.perf_counter() - started)))
            print("  " + episode.summary())
            time.sleep(1.0)
            index += 1


def record(args: argparse.Namespace) -> None:
    import imageio.v2 as imageio

    checkpoint = newest_checkpoint(args.path)
    env = make_env(checkpoint)
    renderer = mujoco.Renderer(env.model, args.height, args.width)
    camera = mujoco.MjvCamera()
    tracking_camera(env, camera)
    frames: list[np.ndarray] = []
    for index in range(max(args.episodes, 1)):
        episode = Episode(env, checkpoint, SEED_BASE + index, args.impulse, args.passive)
        step = 0
        while not episode.done:
            episode.step()
            if step % FRAME_EVERY == 0 or episode.done:
                if episode.done:
                    mujoco.mj_forward(env.model, env.data)
                renderer.update_scene(env.data, camera)
                frames.append(renderer.render().copy())
            step += 1
        # Hold the last frame for half a second so falls are easy to see.
        frames.extend([frames[-1]] * 12)
        print(f"episode {index}: " + episode.summary())
    renderer.close()
    if args.record.suffix.lower() == ".png":
        imageio.imwrite(args.record, frames[len(frames) // 2])
    else:
        imageio.mimwrite(args.record, frames, fps=50 // FRAME_EVERY)
    print(f"wrote {args.record} ({len(frames)} frames) from {checkpoint}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--impulse", type=float, default=None,
                        help="fixed push impulse; default samples like training")
    parser.add_argument("--passive", action="store_true", help="zero action (stance)")
    parser.add_argument("--episodes", type=int, default=0, help="0 = until closed (live)")
    parser.add_argument("--speed", type=float, default=1.0, help="live playback speed")
    parser.add_argument("--record", type=Path, default=None, help="write .mp4/.gif/.png")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()
    if args.record is not None:
        record(args)
    else:
        live(args)


if __name__ == "__main__":
    main()

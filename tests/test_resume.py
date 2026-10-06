import csv
import json

from rl_fall.train import run_training


def test_interrupted_run_resumes_from_newest_checkpoint(tmp_path):
    common = dict(device="cpu", condition="B", seed=5, n_envs=1, wrapper="dummy",
                  threads=1, warmup_updates=0, evaluation_scenarios=1,
                  stage="smoke", environment="planar")
    first = run_training(tmp_path, measured_updates=1, checkpoint_updates=(1,), **common)
    run_dir = tmp_path / first["run_id"]
    (run_dir / "manifest.json").unlink()  # as if power failed before the run finished

    resumed = run_training(tmp_path, measured_updates=2, checkpoint_updates=(1, 2),
                           resume_dir=run_dir, **common)

    assert resumed["status"] == "complete"
    assert resumed["run_id"] == first["run_id"]
    assert resumed["resumed_from_update"] == 1
    with (run_dir / "updates.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [int(row["global_update"]) for row in rows] == [0, 1]
    evaluations = json.loads((run_dir / "evaluations.json").read_text(encoding="utf-8"))
    assert [row["update"] for row in evaluations] == [1, 2]
    assert (run_dir / "resume_1" / "source_snapshot").is_dir()

from benchmarks.report import reconcile_training_manifests


def test_manifest_reconciliation_accounts_for_every_training_manifest():
    rows = [
        {
            "run_id": "included", "status": "complete", "stage": "P2_screening",
            "asset_sha256": "asset", "config_sha256": "config",
            "environment_dimension": "3d",
        },
        {
            "run_id": "smoke", "status": "complete", "stage": "smoke",
            "asset_sha256": "asset", "config_sha256": "config",
            "environment_dimension": "3d",
        },
        {
            "run_id": "failed", "status": "failed", "stage": "P2_screening",
            "asset_sha256": "asset", "config_sha256": "config",
            "environment_dimension": "3d",
        },
    ]
    included, excluded, incomplete = reconcile_training_manifests(
        rows, "asset", "config", "3d", include_smoke=False
    )
    assert len(rows) == len(included) + len(excluded) + len(incomplete)
    assert [row["run_id"] for row in included] == ["included"]
    assert excluded[0][0]["run_id"] == "smoke"
    assert excluded[0][1] == ["stage smoke is excluded"]
    assert [row["run_id"] for row in incomplete] == ["failed"]

for d in results/stage1_v1_0/seed_6300*/push_0.12_hard0.5_posture1.0_natural4_r2/3d_*; do echo "== $d"; python scripts/diag_fall_damage.py $d --episodes 12; done

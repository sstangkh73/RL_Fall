while pgrep -f run_stage2_pilot.sh >/dev/null; do sleep 60; done; bash scripts/run_stage2_eval.sh 63001 63002 63003

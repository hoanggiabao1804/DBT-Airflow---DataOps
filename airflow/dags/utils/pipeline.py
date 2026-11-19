"""Building blocks shared by the DataOps DAGs (dbt_transform, ge_data_quality).

Keeping them here means the preflight check and the runner contract with
``scripts/run_airflow_quality_task.py`` are defined exactly once.
"""

import hashlib
import json
import os
from pathlib import Path

LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
RUNNER = "python /opt/airflow/scripts/run_airflow_quality_task.py "
EVIDENCE_ROOT = "/opt/airflow/quality_evidence"


def resolve_schedule(value, default):
    """Map an env value to an Airflow schedule: ''/unset -> default, manual/none/off -> None."""
    value = (value or "").strip()
    if not value:
        return default
    if value.lower() in ("manual", "none", "off"):
        return None
    return value


def dbt_target():
    return os.environ.get("DATAOPS_DBT_TARGET", "dev")


def ge_schema():
    return os.environ.get("DATAOPS_GE_SCHEMA", "silver")


def runner_env():
    """Environment for a runner task; Jinja templates are rendered by Airflow."""
    return {
        "DATAOPS_DAG_ID": "{{ dag.dag_id }}",
        "DATAOPS_RUN_ID": "{{ run_id }}",
        "DATAOPS_TASK_ID": "{{ task.task_id }}",
        "DATAOPS_TRY_NUMBER": "{{ ti.try_number }}",
        "DATAOPS_DBT_TARGET": dbt_target(),
        "DATAOPS_GE_SCHEMA": ge_schema(),
    }


# Fail fast with a clear message when the stack is not up, instead of letting
# the first dbt/GX task fail with a Docker error. dbt debug also proves the SQL
# Server login works.
CHECK_RUNTIME = r"""
set -euo pipefail
: "${DATAOPS_COMPOSE_PROJECT:?DATAOPS_COMPOSE_PROJECT is not set}"
for service in dbt ge-worker; do
  ids=$(docker ps -q --filter "label=com.docker.compose.project=${DATAOPS_COMPOSE_PROJECT}" \
        --filter "label=com.docker.compose.service=${service}" --filter status=running)
  count=$(printf '%s' "$ids" | grep -c . || true)
  if [ "$count" -ne 1 ]; then
    echo "Service ${service}: expected 1 running container, found ${count}"; exit 1
  fi
  echo "Service ${service}: running (${ids})"
done
dbt_id=$(docker ps -q --filter "label=com.docker.compose.project=${DATAOPS_COMPOSE_PROJECT}" \
         --filter "label=com.docker.compose.service=dbt" --filter status=running)
if docker exec -w /usr/app/dbt "$dbt_id" dbt debug --target "${DATAOPS_DBT_TARGET}" > /tmp/dbt_debug.log 2>&1; then
  echo "dbt debug: OK (target ${DATAOPS_DBT_TARGET})"
else
  echo "dbt debug: FAILED (target ${DATAOPS_DBT_TARGET}) - SQL Server down or profile invalid"
  grep -E "Connection test|ERROR|Error" /tmp/dbt_debug.log | head -5 || true
  exit 1
fi
"""


def run_key(dag_id, run_id):
    """Same key as run_airflow_quality_task.py uses for the evidence folder."""
    return hashlib.sha256((dag_id + "\n" + run_id).encode()).hexdigest()[:20]


def latest_task_summary(dag_id, run_id, task_id, root=None):
    """Return (summary dict, folder) of the newest attempt of a runner task, or (None, None)."""
    base = Path(root or os.environ.get("DATAOPS_EVIDENCE_ROOT", EVIDENCE_ROOT)) / "airflow"
    folder = base / run_key(dag_id, run_id) / task_id
    candidates = []
    for path in folder.glob("try-*/task_summary.json"):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        candidates.append((summary.get("attempt") or 0, summary.get("finished_at_utc") or "", summary, path.parent))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2], candidates[-1][3]

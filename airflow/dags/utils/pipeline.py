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


# Preflight script (scripts/check_runtime.sh, mounted at /opt/airflow/scripts).
# The trailing space stops Airflow from treating a command ending in ".sh" as a
# Jinja template file to load.
CHECK_RUNTIME = "bash /opt/airflow/scripts/check_runtime.sh "

# Runner exit codes: 1 = data/validation failure (deterministic), 2 = execution error.
DATA_FAILURE_EXIT_CODE = 1


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

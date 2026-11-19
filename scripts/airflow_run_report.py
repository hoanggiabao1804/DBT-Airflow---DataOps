"""Print a JSON report of one Airflow DAG run (states, attempts, durations).

Run inside the Airflow scheduler container, where ``scripts/`` is mounted:

    docker compose ... exec -T airflow-scheduler \
        python /opt/airflow/scripts/airflow_run_report.py dbt_transform <run_id>

Without ``run_id`` the most recent run of the DAG is reported. The report reads
Airflow's metadata database through the ORM; it never prints connections,
variables or log contents, only identifiers, states and timings, so it is safe
to commit as evidence under ``docs/evidence/``.
"""

import argparse
import json
import sys

from airflow.models import DagRun, TaskInstance
from airflow.utils.session import create_session


def iso(value):
    return value.isoformat() if value else None


def seconds(start, end):
    if start and end:
        return round((end - start).total_seconds(), 3)
    return None


def build_report(dag_id, run_id=None):
    with create_session() as session:
        query = session.query(DagRun).filter(DagRun.dag_id == dag_id)
        if run_id:
            query = query.filter(DagRun.run_id == run_id)
        dag_run = query.order_by(DagRun.execution_date.desc()).first()
        if dag_run is None:
            return None
        tis = (
            session.query(TaskInstance)
            .filter(TaskInstance.dag_id == dag_id, TaskInstance.run_id == dag_run.run_id)
            .order_by(TaskInstance.start_date.asc().nullslast(), TaskInstance.task_id)
            .all()
        )
        tasks = [
            {
                "task_id": ti.task_id,
                "state": ti.state,
                # _try_number is the attempt that last ran (try_number points to the next one).
                "attempts": ti._try_number,  # pylint: disable=protected-access
                "max_tries": ti.max_tries,
                "operator": ti.operator,
                "start_date": iso(ti.start_date),
                "end_date": iso(ti.end_date),
                "duration_seconds": round(ti.duration, 3) if ti.duration is not None else None,
            }
            for ti in tis
        ]
        states = {}
        for task in tasks:
            states[task["state"] or "none"] = states.get(task["state"] or "none", 0) + 1
        return {
            "dag_id": dag_id,
            "run_id": dag_run.run_id,
            "run_type": str(dag_run.run_type),
            "state": dag_run.state,
            "queued_at": iso(dag_run.queued_at),
            "start_date": iso(dag_run.start_date),
            "end_date": iso(dag_run.end_date),
            "duration_seconds": seconds(dag_run.start_date, dag_run.end_date),
            "task_state_counts": states,
            "tasks": tasks,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dag_id")
    parser.add_argument("run_id", nargs="?")
    args = parser.parse_args()
    report = build_report(args.dag_id, args.run_id)
    if report is None:
        print("No DAG run found", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

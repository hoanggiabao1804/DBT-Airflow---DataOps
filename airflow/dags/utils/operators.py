"""Operators shared by the DataOps DAGs."""

import re

from airflow.exceptions import AirflowException, AirflowFailException
from airflow.operators.bash import BashOperator

_EXIT_CODE = re.compile(r"non-zero exit code (\d+)")


class QualityStepOperator(BashOperator):
    """BashOperator that does not retry deterministic failures.

    ``run_airflow_quality_task.py`` distinguishes *data* failures (exit 1, e.g.
    a GX expectation failed) from *execution* errors (exit 2, e.g. container
    missing). Retrying a data failure only delays the alert and produces a
    misleading "retry" warning, so exit codes in ``no_retry_exit_codes`` are
    re-raised as ``AirflowFailException``: the task fails at once, callbacks
    and alerts still run. Every other non-zero code keeps the normal retries.
    """

    def __init__(self, *, no_retry_exit_codes=(), **kwargs):
        super().__init__(**kwargs)
        self.no_retry_exit_codes = tuple(no_retry_exit_codes)

    def execute(self, context):
        try:
            return super().execute(context)
        except AirflowFailException:
            raise
        except AirflowException as error:
            match = _EXIT_CODE.search(str(error))
            if match and int(match.group(1)) in self.no_retry_exit_codes:
                raise AirflowFailException(
                    "Exit code {} is a deterministic failure; not retrying.".format(match.group(1))
                ) from error
            raise

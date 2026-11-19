#!/usr/bin/env bash
# Preflight for the DataOps DAGs (task check_runtime), run inside the Airflow
# container. Fails fast with a readable message when the stack is not ready:
#   - exactly one running container for the Compose services dbt and ge-worker
#   - dbt can log in to SQL Server (dbt debug)
# Required env: DATAOPS_COMPOSE_PROJECT. Optional: DATAOPS_DBT_TARGET (dev).
set -euo pipefail

: "${DATAOPS_COMPOSE_PROJECT:?DATAOPS_COMPOSE_PROJECT is not set}"
target="${DATAOPS_DBT_TARGET:-dev}"

container_of() {
    docker ps -q --filter "label=com.docker.compose.project=${DATAOPS_COMPOSE_PROJECT}" \
        --filter "label=com.docker.compose.service=$1" --filter status=running
}

for service in dbt ge-worker; do
    ids=$(container_of "$service")
    count=$(printf '%s' "$ids" | grep -c . || true)
    if [ "$count" -ne 1 ]; then
        echo "Service ${service}: expected 1 running container, found ${count}"
        exit 1
    fi
    echo "Service ${service}: running (${ids})"
done

log=$(mktemp)
trap 'rm -f "$log"' EXIT
# A dead SQL Server makes dbt debug wait ~65 s for the ODBC login timeout; 30 s is
# plenty for a healthy server (~3 s) and makes failure alerts arrive sooner.
if timeout 30 docker exec -w /usr/app/dbt "$(container_of dbt)" dbt debug --target "$target" >"$log" 2>&1; then
    echo "dbt debug: OK (target ${target})"
else
    echo "dbt debug: FAILED or >30 s (target ${target}) - SQL Server down or profile invalid"
    grep -E "Connection test|ERROR|Error" "$log" | head -5 || true
    exit 1
fi

#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENVIRONMENT="${1:-}"
RELEASE_INPUT="${2:-}"
CONFIRM_FLAG="${3:-}"

case "$ENVIRONMENT" in
    dev) TARGET=dev ;;
    staging) TARGET=staging ;;
    production) TARGET=prod ;;
    *)
        echo "Usage: $0 {dev|staging|production} <release_dir> [--yes]" >&2
        exit 2
        ;;
esac
if [[ -z "$RELEASE_INPUT" || ( -n "$CONFIRM_FLAG" && "$CONFIRM_FLAG" != --yes ) ]]; then
    echo "Usage: $0 {dev|staging|production} <release_dir> [--yes]" >&2
    exit 2
fi
if [[ "$ENVIRONMENT" == staging && -z "${STAGING_SQL_PASSWORD:-}" ]]; then
    echo "STAGING_SQL_PASSWORD is required." >&2
    exit 2
fi
if [[ "$ENVIRONMENT" == production && ( -z "${PROD_SQL_SERVER:-}" || -z "${PROD_SQL_USER:-}" || -z "${PROD_SQL_PASSWORD:-}" ) ]]; then
    echo "PROD_SQL_SERVER, PROD_SQL_USER, and PROD_SQL_PASSWORD are required." >&2
    exit 2
fi

RELEASE_DIR="$(realpath -e -- "$RELEASE_INPUT")"
case "$RELEASE_DIR" in
    "$PROJECT_ROOT/backups/"*) ;;
    *)
        echo "Release must be inside $PROJECT_ROOT/backups" >&2
        exit 2
        ;;
esac
python3 "$PROJECT_ROOT/scripts/release_snapshot.py" verify "$RELEASE_DIR" "$ENVIRONMENT"

echo "Restore dbt version from $RELEASE_DIR into $ENVIRONMENT?"
if [[ "$CONFIRM_FLAG" != --yes ]]; then
    read -r -p "Type yes to continue: " answer
    if [[ "$answer" != yes ]]; then
        echo "Rollback cancelled."
        exit 1
    fi
fi

# The active source tree is never replaced. The old release is run from a
# temporary project under the dbt bind mount, then removed on exit.
mkdir -p "$PROJECT_ROOT/dbt/.release_work"
WORK_DIR="$(mktemp -d "$PROJECT_ROOT/dbt/.release_work/$ENVIRONMENT.XXXXXX")"
if [[ "$ENVIRONMENT" == dev ]]; then
    DBT_PROJECT_ARG="/usr/app/dbt/.release_work/$(basename "$WORK_DIR")"
    DBT_PROFILES_ARG=/usr/app/dbt
    run_dbt() {
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T \
            -e DBT_LOG_PATH=/tmp/dbt-rollback-logs dbt dbt "$@"
    }
else
    DBT_PROJECT_ARG="$WORK_DIR"
    DBT_PROFILES_ARG="$PROJECT_ROOT/dbt"
    mkdir -p "$PROJECT_ROOT/backups/logs/$ENVIRONMENT"
    run_dbt() {
        DBT_LOG_PATH="$PROJECT_ROOT/backups/logs/$ENVIRONMENT" dbt "$@"
    }
fi

cleanup() {
    local status=$?
    trap - EXIT
    if [[ "$ENVIRONMENT" == dev ]]; then
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T dbt \
            rm -rf -- "$DBT_PROJECT_ARG" || status=1
    else
        rm -rf -- "$WORK_DIR" || status=1
    fi
    exit "$status"
}
trap cleanup EXIT
cp -a "$RELEASE_DIR/dbt/." "$WORK_DIR/"

dbt_step() {
    local command="$1"
    echo "Running rollback dbt $command for $ENVIRONMENT"
    run_dbt "$command" --project-dir "$DBT_PROJECT_ARG" \
        --profiles-dir "$DBT_PROFILES_ARG" --target "$TARGET"
}

dbt_step deps
dbt_step debug
dbt_step run
dbt_step test

if [[ "$ENVIRONMENT" == dev ]]; then
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T dbt \
        python - --from-dbt-profile /usr/app/dbt < "$PROJECT_ROOT/scripts/smoke_tests.py"
else
    if [[ "$ENVIRONMENT" == staging ]]; then
        export SMOKE_SQL_SERVER="${STAGING_SQL_SERVER:-localhost}"
        export SMOKE_SQL_DATABASE="${STAGING_SQL_DATABASE:-AdventureWorks2014_Staging}"
        export SMOKE_SQL_USER="${STAGING_SQL_USER:-sa}"
        export SMOKE_SQL_PASSWORD="${STAGING_SQL_PASSWORD:-}"
    else
        export SMOKE_SQL_SERVER="${PROD_SQL_SERVER:-localhost}"
        export SMOKE_SQL_DATABASE=AdventureWorks2014_Prod
        export SMOKE_SQL_USER="${PROD_SQL_USER:-sa}"
        export SMOKE_SQL_PASSWORD="${PROD_SQL_PASSWORD:-}"
    fi
    if [[ -z "$SMOKE_SQL_PASSWORD" ]]; then
        echo "Missing SQL password for rollback smoke tests." >&2
        exit 2
    fi
    python3 "$PROJECT_ROOT/scripts/smoke_tests.py"
fi

echo "Rollback to $RELEASE_DIR passed dbt tests and smoke tests."

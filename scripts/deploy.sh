#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$PROJECT_ROOT/dbt"
ENVIRONMENT="${1:-}"
TARGET="${2:-}"

case "$ENVIRONMENT/$TARGET" in
    dev/dev|staging/staging|production/prod) ;;
    *)
        echo "Usage: $0 {dev dev|staging staging|production prod}" >&2
        exit 2
        ;;
esac

if [[ "$ENVIRONMENT" == production && "${SKIP_PRE_DEPLOY_TESTS:-0}" == 1 ]]; then
    echo "Pre-deployment tests cannot be skipped for production." >&2
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

mkdir -p "$PROJECT_ROOT/backups/logs/$ENVIRONMENT"
if [[ "$ENVIRONMENT" == dev ]]; then
    DBT_PROJECT_ARG=/usr/app/dbt
    DBT_PROFILES_ARG=/usr/app/dbt
    run_dbt() {
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T \
            -e DBT_LOG_PATH=/tmp/dbt-deploy-logs dbt dbt "$@"
    }
else
    DBT_PROJECT_ARG="$PROJECT_DIR"
    DBT_PROFILES_ARG="$PROJECT_DIR"
    run_dbt() {
        DBT_LOG_PATH="$PROJECT_ROOT/backups/logs/$ENVIRONMENT" dbt "$@"
    }
fi

dbt_step() {
    local command="$1"
    shift
    echo "Running dbt $command for $ENVIRONMENT"
    if [[ "$command" == docs ]]; then
        run_dbt docs generate --project-dir "$DBT_PROJECT_ARG" \
            --profiles-dir "$DBT_PROFILES_ARG" --target "$TARGET"
    else
        run_dbt "$command" --project-dir "$DBT_PROJECT_ARG" \
            --profiles-dir "$DBT_PROFILES_ARG" --target "$TARGET" "$@"
    fi
}

source_fingerprint="$(python3 "$PROJECT_ROOT/scripts/release_snapshot.py" fingerprint "$PROJECT_DIR")"
echo "Starting deployment to $ENVIRONMENT"
dbt_step deps
dbt_step debug
dbt_step compile

if [[ "${SKIP_PRE_DEPLOY_TESTS:-0}" == 1 ]]; then
    echo "Skipping pre-deployment tests for the initial $ENVIRONMENT deployment."
else
    dbt_step test
fi

dbt_step run
dbt_step test

# The GitHub runner supplies these through environment variables, never CLI args.
if [[ "$ENVIRONMENT" == staging ]]; then
    export SMOKE_SQL_SERVER="${STAGING_SQL_SERVER:-localhost}"
    export SMOKE_SQL_DATABASE="${STAGING_SQL_DATABASE:-AdventureWorks2014_Staging}"
    export SMOKE_SQL_USER="${STAGING_SQL_USER:-sa}"
    export SMOKE_SQL_PASSWORD="${STAGING_SQL_PASSWORD:-}"
elif [[ "$ENVIRONMENT" == production ]]; then
    export SMOKE_SQL_SERVER="${PROD_SQL_SERVER:-localhost}"
    export SMOKE_SQL_DATABASE=AdventureWorks2014_Prod
    export SMOKE_SQL_USER="${PROD_SQL_USER:-sa}"
    export SMOKE_SQL_PASSWORD="${PROD_SQL_PASSWORD:-}"
fi

if [[ "$ENVIRONMENT" == dev ]]; then
    echo "Running smoke tests in the dbt container"
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T dbt \
        python - --from-dbt-profile /usr/app/dbt < "$PROJECT_ROOT/scripts/smoke_tests.py"
else
    if [[ -z "$SMOKE_SQL_PASSWORD" ]]; then
        echo "Missing SQL password for post-deployment smoke tests." >&2
        exit 2
    fi
    python3 "$PROJECT_ROOT/scripts/smoke_tests.py"
fi

dbt_step docs

# A release exists only after every deployment check has passed.
release_dir="$(python3 "$PROJECT_ROOT/scripts/release_snapshot.py" \
    create "$PROJECT_DIR" "$PROJECT_ROOT/backups" "$ENVIRONMENT" \
    --expected-fingerprint "$source_fingerprint")"
echo "Deployment passed. Release: $release_dir"

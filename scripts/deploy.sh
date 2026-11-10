#!/bin/bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENVIRONMENT=${1:-}
TARGET=${2:-}

if [ -z "$ENVIRONMENT" ] || [ -z "$TARGET" ]; then
    echo -e "${RED}Usage: ./deploy.sh <environment> <target>${NC}"
    echo "Example: ./deploy.sh staging staging"
    exit 1
fi

echo -e "${GREEN}🚀 Starting deployment to $ENVIRONMENT environment...${NC}"

if [[ "$ENVIRONMENT" == dev && "$TARGET" == dev ]]; then
    run_dbt() {
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T dbt dbt "$@"
    }
    echo "Using the dbt Docker Compose service for dev."
else
    run_dbt() {
        dbt "$@"
    }
    echo "Using the dbt CLI for $ENVIRONMENT."
fi

# 1. Pre-deployment checks
echo -e "${YELLOW}📋 Running pre-deployment checks...${NC}"
cd "$PROJECT_ROOT/dbt"

# Install dependencies
echo "Installing DBT dependencies..."
run_dbt deps --target "$TARGET"

# Compile models
echo "Compiling DBT models..."
if ! run_dbt compile --target "$TARGET"; then
    echo -e "${RED}❌ Compilation failed${NC}"
    exit 1
fi

# 2. Run tests on current state when models already exist.
if [[ "${SKIP_PRE_DEPLOY_TESTS:-0}" == "1" ]]; then
    echo "Skipping pre-deployment tests for the initial staging deployment."
else
    echo -e "${YELLOW}🧪 Running tests...${NC}"
    if ! run_dbt test --target "$TARGET"; then
        echo -e "${RED}❌ Tests failed${NC}"
        exit 1
    fi
fi

# 3. Backup current state
echo -e "${YELLOW}💾 Creating backup...${NC}"
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir="$PROJECT_ROOT/backups/${ENVIRONMENT}_${timestamp}"
mkdir -p "$backup_dir"
cp -r target/ "$backup_dir/"

echo "Backup created at: $backup_dir"

# 4. Deploy models
echo -e "${YELLOW}🔨 Deploying models...${NC}"
if ! run_dbt run --target "$TARGET"; then
    echo -e "${RED}❌ Deployment failed${NC}"
    exit 1
fi

# 5. Run post-deployment tests
echo -e "${YELLOW}✅ Running post-deployment tests...${NC}"
if ! run_dbt test --target "$TARGET"; then
    echo -e "${RED}❌ Post-deployment tests failed${NC}"
    exit 1
fi

# 6. Generate documentation
echo -e "${YELLOW}📚 Generating documentation...${NC}"
run_dbt docs generate --target "$TARGET"

# 7. Success message
echo -e "${GREEN}✨ Deployment to $ENVIRONMENT completed successfully!${NC}"
echo ""
echo "Summary:"
echo "  Environment: $ENVIRONMENT"
echo "  Target: $TARGET"
echo "  Time: $(date)"
echo "  Backup: $backup_dir"

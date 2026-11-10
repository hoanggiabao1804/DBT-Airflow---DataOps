#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVIRONMENT=$1
BACKUP_DIR=$2

if [ -z "$ENVIRONMENT" ] || [ -z "$BACKUP_DIR" ]; then
    echo -e "${RED}Usage: ./rollback.sh <environment> <backup_directory>${NC}"
    echo "Example: ./rollback.sh staging backups/staging_20240101_120000"
    exit 1
fi

if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}❌ Backup directory not found: $BACKUP_DIR${NC}"
    exit 1
fi

echo -e "${YELLOW}⚠️  WARNING: This will rollback to a previous state${NC}"
echo "Environment: $ENVIRONMENT"
echo "Backup: $BACKUP_DIR"
echo ""
read -p "Are you sure you want to proceed? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Rollback cancelled"
    exit 0
fi

echo -e "${GREEN}🔄 Starting rollback...${NC}"

# Restore backup
echo "Restoring from backup..."
cd dbt
rm -rf target/
cp -r ../$BACKUP_DIR/target/ ./

# Re-run models from backup state
echo "Re-deploying previous state..."
dbt run --target $ENVIRONMENT

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Rollback failed${NC}"
    exit 1
fi

# Run tests
echo "Running tests..."
dbt test --target $ENVIRONMENT

echo -e "${GREEN}✅ Rollback completed successfully${NC}"

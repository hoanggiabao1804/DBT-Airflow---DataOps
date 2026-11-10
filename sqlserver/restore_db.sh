#!/bin/bash
set -euo pipefail

password="${SA_PASSWORD:-YourStrong@Passw0rd}"
sqlcmd=/opt/mssql-tools/bin/sqlcmd

# SQL Server can take longer to start on a fresh GitHub runner.
ready=0
for attempt in {1..60}; do
    if "$sqlcmd" -S localhost -U sa -P "$password" -Q "SELECT 1" -b >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 2
done

if [[ "$ready" != 1 ]]; then
    echo "SQL Server did not become ready within 120 seconds" >&2
    exit 1
fi

"$sqlcmd" -S localhost -U sa -P "$password" -b -Q "RESTORE DATABASE AdventureWorks2014 FROM DISK = '/tmp/AdventureWorks2014.bak' WITH MOVE 'AdventureWorks2014_Data' TO '/var/opt/mssql/data/AdventureWorks2014.mdf', MOVE 'AdventureWorks2014_Log' TO '/var/opt/mssql/data/AdventureWorks2014_log.ldf', REPLACE"

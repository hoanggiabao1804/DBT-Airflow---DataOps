# Docker Commands for DBT Airflow Project

## 1. Container Management

### Starting Containers
```bash
# Start all containers in detached mode
docker-compose up -d

# Start specific services
docker-compose up -d airflow-webserver
docker-compose up -d airflow-scheduler
docker-compose up -d postgres
docker-compose up -d sqlserver
docker-compose up -d dbt
```

### Stopping Containers
```bash
# Stop all containers
docker-compose down

# Stop specific services
docker-compose stop airflow-webserver
docker-compose stop airflow-scheduler
```

### Viewing Container Status
```bash
# List all running containers
docker-compose ps

# View container logs
docker-compose logs
docker-compose logs -f  # Follow log output
docker-compose logs airflow-webserver  # View specific service logs
```

## 2. DBT Operations

### Running DBT Commands
```bash
# Install DBT dependencies
docker-compose exec dbt dbt deps

# Run DBT models
docker-compose exec dbt dbt run
docker-compose exec dbt dbt run --select stg_sales_orders  # Run specific model

# Run DBT tests
docker-compose exec dbt dbt test
docker-compose exec dbt dbt test --select stg_sales_orders  # Test specific model

# DBT debug
docker-compose exec dbt dbt debug
```

## 3. Database Operations

### SQL Server
```bash
# Connect to SQL Server container
docker-compose exec sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P YourStrong@Passw0rd

# Backup database
docker-compose exec sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P YourStrong@Passw0rd -Q "BACKUP DATABASE AdventureWorks TO DISK = '/var/opt/mssql/backup/AdventureWorks.bak'"
```

### PostgreSQL (Airflow Metadata)
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U airflow -d airflow

# Backup database
docker-compose exec postgres pg_dump -U airflow airflow > airflow_backup.sql
```

## 4. Airflow Operations

### Airflow CLI Commands
```bash
# Initialize Airflow database
docker-compose exec airflow-webserver airflow db init

# Create Airflow user
docker-compose exec airflow-webserver airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin

# List DAGs
docker-compose exec airflow-webserver airflow dags list

# Trigger DAG
docker-compose exec airflow-webserver airflow dags trigger dbt_transform
```

## 5. Maintenance Commands

### Container Maintenance
```bash
# Rebuild containers
docker-compose build

# Remove all containers and volumes
docker-compose down -v

# Clean up unused images
docker system prune

# View container resource usage
docker stats
```

### Network Operations
```bash
# List networks
docker network ls

# Inspect network
docker network inspect dbt_airflow_project_dbt_airflow_network
```

## 6. Troubleshooting Commands

### Debugging
```bash
# View container details
docker inspect <container_id>

# View container logs with timestamps
docker-compose logs --timestamps

# Execute shell in container
docker-compose exec dbt bash
docker-compose exec airflow-webserver bash
```

### Health Checks
```bash
# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}"

# Test network connectivity
docker-compose exec dbt ping sqlserver
docker-compose exec dbt ping postgres
```

## Important Notes

1. **Environment Variables**:
   - Default SQL Server password: YourStrong@Passw0rd
   - Default Airflow credentials: airflow/airflow
   - Default PostgreSQL credentials: airflow/airflow

2. **Ports**:
   - Airflow Web UI: http://localhost:8080
   - SQL Server: localhost:1433
   - PostgreSQL: localhost:5432

3. **Volume Mounts**:
   - DBT models: ./dbt:/usr/app/dbt
   - Airflow DAGs: ./airflow/dags:/opt/airflow/dags
   - Airflow logs: ./airflow/logs:/opt/airflow/logs

4. **Best Practices**:
   - Always use `docker-compose exec` for running commands in containers
   - Use `-d` flag for running containers in detached mode
   - Check logs when troubleshooting issues
   - Use specific service names when running commands 
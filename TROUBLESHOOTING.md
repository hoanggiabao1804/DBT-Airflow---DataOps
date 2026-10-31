# Troubleshooting Guide

## Error: "Failed to compute cache key" in Airflow

### Error Message
```
failed to solve: failed to compute cache key: failed to calculate checksum of ref 4cecef4a-37b6-49a4-949a-884ef834a77: /dbt/: not found
```

### Common Causes
1. **Missing Directory Structure**
   - The DBT directory is not properly mounted in the Airflow container
   - Directory permissions issues on the new computer
   - Incorrect file paths in docker-compose.yml

2. **Docker Volume Issues**
   - Volumes not properly created
   - Cached volumes from previous runs
   - Permission conflicts between host and container

3. **File System Differences**
   - Windows vs Linux path separators
   - Case sensitivity differences
   - Line ending differences (CRLF vs LF)

### Step-by-Step Solutions

1. **Clean Docker Environment First**
```bash
# Stop all containers
docker-compose down

# Remove all volumes
docker-compose down -v

# Clean Docker cache
docker system prune -a

# Remove any existing volumes
docker volume prune
```

2. **Check Directory Structure**
```bash
# Ensure these directories exist
mkdir -p ./dbt
mkdir -p ./airflow/dags
mkdir -p ./airflow/logs
mkdir -p ./airflow/plugins
```

3. **Fix Permissions**
```bash
# For Windows (PowerShell as Administrator):
icacls * /reset
icacls * /grant Everyone:F /t

# For Linux/Mac:
chmod -R 755 ./dbt
chmod -R 755 ./airflow
chmod 644 docker-compose.yml
```

4. **Verify docker-compose.yml Volume Mappings**
```yaml
services:
  airflow-webserver:
    volumes:
      - ./dbt:/opt/airflow/dbt
      - ./airflow/dags:/opt/airflow/dags
      - ./airflow/logs:/opt/airflow/logs
      - ./airflow/plugins:/opt/airflow/plugins

  dbt:
    volumes:
      - ./dbt:/dbt
```

5. **Rebuild and Start Services**
```bash
# Rebuild all containers
docker-compose build --no-cache

# Start services
docker-compose up -d
```

### Prevention Steps for Future Deployments

1. **Directory Structure Check**
```
project_root/
├── airflow/
│   ├── dags/
│   ├── logs/
│   └── plugins/
├── dbt/
│   ├── models/
│   └── profiles.yml
└── docker-compose.yml
```

2. **File Permission Requirements**
- All directories should be readable and executable (755)
- Configuration files should be readable (644)
- Ensure the current user has appropriate permissions

3. **Docker Configuration Best Practices**
- Use relative paths in volume mappings
- Avoid hardcoded absolute paths
- Use consistent naming for volumes

4. **Cross-Platform Compatibility**
- Use forward slashes (/) in paths, even on Windows
- Keep line endings consistent (preferably LF)
- Use lowercase for file and directory names

### Quick Verification Steps

1. **Check Container Status**
```bash
docker-compose ps
```

2. **Verify Volume Mounts**
```bash
docker-compose exec airflow-webserver ls -la /opt/airflow/dbt
```

3. **Check Logs**
```bash
docker-compose logs airflow-webserver
```

### Additional Considerations

1. **System Requirements**
- Ensure Docker Desktop has sufficient resources allocated
- Minimum 4GB RAM recommended
- Adequate disk space for volumes

2. **Network Configuration**
- Check if required ports are available
- Verify no firewall blocking
- Ensure Docker network driver is working

3. **Version Compatibility**
- Docker version compatibility
- Docker Compose version
- Host OS compatibility

### When Nothing Else Works

1. **Complete Reset**
```bash
# Stop and remove everything
docker-compose down -v
docker system prune -a --volumes

# Remove project directory
rm -rf ./project_directory

# Clone/copy fresh project
git clone <project_repo> or copy fresh files

# Follow setup guide from scratch
```

2. **Verify System Requirements**
- Check Docker Desktop settings
- Verify system resources
- Update Docker if needed

3. **Contact Support**
- Check project documentation
- Review issue tracker
- Consult with team members 
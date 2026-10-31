FROM apache/airflow:2.7.1-python3.9

# Switch to root to install system packages
USER root

# Debian 11 and its PGDG repository have moved to their archives.
# PostgreSQL client packages are already present in the base image.
RUN rm -f /etc/apt/sources.list.d/pgdg.list \
    && sed -i 's|http://deb.debian.org/debian-security bullseye-security|http://archive.debian.org/debian-security bullseye-security|' /etc/apt/sources.list \
    && rm -rf /var/lib/apt/lists/*

# Install ODBC driver and dependencies. The base image already configures
# Microsoft's Debian 11 repository (the same release as this Airflow image).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        unixodbc \
        unixodbc-dev \
        curl \
        gnupg2 \
        docker.io \
        git \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add airflow user to docker group
RUN usermod -aG docker airflow

# Switch back to airflow user
USER airflow

# Install Python packages
COPY requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt \
    && pip install apache-airflow-providers-docker \
    && pip install dbt-sqlserver

# Create DBT directory
RUN mkdir -p /opt/airflow/dbt

# Copy DAGs and plugins
COPY --chown=airflow:root dags/ /opt/airflow/dags/
COPY --chown=airflow:root plugins/ /opt/airflow/plugins/

# Copy DBT project - FIXED: Use a volume mount instead of COPY
# The DBT directory will be mounted at runtime via docker-compose.yml

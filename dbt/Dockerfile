FROM python:3.9-slim

WORKDIR /usr/app/dbt

# Install system dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Add Microsoft repository and install ODBC driver
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg apt-transport-https unixodbc && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/10/prod buster main" \
      > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends msodbcsql17 && \
    rm -rf /var/lib/apt/lists/*


    # Add Microsoft repo and install ODBC driver (no apt-key)
# RUN set -eux; \
#     apt-get update && \
#     apt-get install -y --no-install-recommends \
#         curl ca-certificates gnupg apt-transport-https unixodbc && \
#     mkdir -p /etc/apt/keyrings && \
#     curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
#       | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg && \
#     . /etc/os-release; \
#     echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/${ID}/${VERSION_ID}/prod ${VERSION_CODENAME:-} main" \
#       > /etc/apt/sources.list.d/mssql-release.list && \
#     apt-get update && \
#     ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
#         msodbcsql18 && \
#     rm -rf /var/lib/apt/lists/*


# Install specific version of dbt-core and related packages
RUN pip install --no-cache-dir \
    dbt-core==1.8.7 \
    dbt-sqlserver==1.8.7

# Copy dbt project files
COPY . .

# Initialize dbt project (with no packages)
RUN touch packages.yml && dbt deps

FROM python:3.9-slim

WORKDIR /usr/app/dbt

# Install system dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Use Microsoft's distro-specific repository package, including its signing key.
RUN set -eux; \
    . /etc/os-release; \
    curl -fsSL "https://packages.microsoft.com/config/${ID}/${VERSION_ID}/packages-microsoft-prod.deb" \
        -o /tmp/packages-microsoft-prod.deb; \
    dpkg -i /tmp/packages-microsoft-prod.deb; \
    rm /tmp/packages-microsoft-prod.deb; \
    apt-get update; \
    ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        msodbcsql17 unixodbc libgssapi-krb5-2; \
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

FROM mcr.microsoft.com/mssql/server:2019-latest

# Install curl and mssql-tools
USER root
RUN apt-get update && apt-get install -y curl gnupg2

# Install mssql-tools
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y mssql-tools unixodbc-dev && \
    echo 'export PATH="$PATH:/opt/mssql-tools/bin"' >> ~/.bashrc

# Download and install AdventureWorks database
RUN curl -L -o /tmp/AdventureWorks2014.bak https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2014.bak

# Create a script to restore the database
COPY restore_db.sh /tmp/restore_db.sh
RUN chmod +x /tmp/restore_db.sh

# Switch back to mssql user
USER mssql

# Start SQL Server and keep it running
CMD /opt/mssql/bin/sqlservr 
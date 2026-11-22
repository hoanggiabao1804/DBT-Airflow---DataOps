FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GX_ANALYTICS_ENABLED=false

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
        -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 unixodbc libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/* /tmp/packages-microsoft-prod.deb

COPY requirements.txt /tmp/ge-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ge-requirements.txt && pip check

WORKDIR /workspace
ENTRYPOINT ["python", "/workspace/scripts/run_ge_checkpoints.py"]

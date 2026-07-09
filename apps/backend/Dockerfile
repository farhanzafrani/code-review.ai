FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl unzip git default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# sonar-scanner CLI — only exercised when SONARQUBE_ENABLED=true, but
# installed unconditionally since it's baked into the image at build time.
ARG SONAR_SCANNER_VERSION=6.2.1.4610
RUN curl -sSLo /tmp/sonar-scanner.zip \
      "https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux-x64.zip" \
    && unzip -q /tmp/sonar-scanner.zip -d /opt \
    && mv "/opt/sonar-scanner-${SONAR_SCANNER_VERSION}-linux-x64" /opt/sonar-scanner \
    && rm /tmp/sonar-scanner.zip
ENV PATH="/opt/sonar-scanner/bin:${PATH}"
# sonar-scanner insists on a writable home for its cache even when unused.
ENV SONAR_SCANNER_OPTS="-Duser.home=/tmp"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
RUN uv sync --no-install-project

COPY . .
RUN uv sync

EXPOSE 8000

# --no-sync: the environment is already synced above at build time. Without
# it, `uv run` re-checks the project against the lockfile on every start and
# rebuilds the local package via hatchling — which needs PyPI reachable, so
# the container fails to boot at all on any network-restricted cluster.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

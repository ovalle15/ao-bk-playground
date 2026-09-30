# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements-e2e.txt ./
# BuildKit exposes the restored wheels for this RUN without storing them in an
# image layer. The checksum guard also lets manual builds use the package index.
RUN --mount=type=bind,source=.buildkite-cache/e2e-wheels,target=/wheels,readonly \
    if [ -f /wheels/.requirements-sha256 ] \
      && [ "$(sha256sum requirements-e2e.txt | cut -d ' ' -f 1)" = "$(cat /wheels/.requirements-sha256)" ]; then \
      python -m pip install --no-index --find-links=/wheels -r requirements-e2e.txt; \
    else \
      python -m pip install --no-cache-dir -r requirements-e2e.txt; \
    fi

COPY tests/ ./tests/

CMD ["python", "-m", "pytest", "-vv", "-s", "tests/test_e2e.py"]

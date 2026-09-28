FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements-e2e.txt ./
RUN python -m pip install --no-cache-dir -r requirements-e2e.txt

COPY tests/ ./tests/

CMD ["python", "-m", "pytest", "-vv", "-s", "tests/test_e2e.py"]

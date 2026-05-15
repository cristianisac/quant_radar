FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash radar
USER radar
ENV PATH="/home/radar/.local/bin:${PATH}"

COPY --chown=radar:radar pyproject.toml README.md SKILL.md ./
COPY --chown=radar:radar quant_radar/ ./quant_radar/

RUN pip install --user -e ".[dev]"

COPY --chown=radar:radar tests/ ./tests/
COPY --chown=radar:radar scripts/ ./scripts/

CMD ["pytest", "-q", "-p", "no:cacheprovider"]

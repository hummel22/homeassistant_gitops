ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache \
    git \
    openssh-client \
    python3 \
    py3-pip

RUN pip install --no-cache-dir uv==0.4.24

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
RUN uv sync --no-dev --project /app

ENV PATH="/app/.venv/bin:$PATH"

COPY rootfs /
COPY rootfs/app/gitignore_example /app/gitignore_example

EXPOSE 8099

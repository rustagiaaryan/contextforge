FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv==0.7.9
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "--no-sync", "contextforge"]
CMD ["--help"]


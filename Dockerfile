FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv==0.7.9
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 contextforge \
    && chown -R contextforge:contextforge /app
USER contextforge

ENTRYPOINT ["uv", "run", "--no-sync", "contextforge"]
CMD ["--help"]

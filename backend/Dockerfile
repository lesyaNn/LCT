# L4: multistage build — single source of versions is ``pyproject.toml``;
# test dependencies (pytest/ruff) live ONLY in the ``test`` stage and never
# reach the ``runtime`` image. Storage paths are canonical: /app/storage and
# /app/reports (``/code/var/files`` orphan removed; ``storage_root`` defaults
# stay under /app — see app/config.py).

FROM python:3.12-slim AS base
WORKDIR /code
# Cyrillic PDF runtime (P4-04-02): DejaVu Sans for reportlab. The PDF
# generator discovers these files at runtime and never ships font binaries.
RUN apt-get update \
  && apt-get install -y --no-install-recommends fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/* \
  && useradd -r -u 10001 appuser \
  && mkdir -p /app/storage /app/reports /tmp/rtk-imports \
  && chown -R appuser:appuser /code /app/storage /app/reports /tmp/rtk-imports
COPY pyproject.toml ./
# Runtime deps are installed from pyproject (no second pin list here).
RUN pip install --no-cache-dir .

FROM base AS test
RUN pip install --no-cache-dir "pytest==9.0.3" "ruff==0.15.13" "httpx==0.28.1"
COPY scripts ./scripts
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh && chown -R appuser:appuser /code
ENV PYTHONPATH=/code
USER appuser
CMD ["pytest", "tests", "-m", "not pg"]

FROM base AS runtime
COPY scripts ./scripts
COPY migrations ./migrations
COPY app ./app
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh && chown -R appuser:appuser /code
ENV PYTHONPATH=/code
EXPOSE 8000
USER appuser
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"
CMD ["./entrypoint.sh"]

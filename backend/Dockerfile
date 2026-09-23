FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml ./
# Cyrillic PDF runtime (P4-04-02): DejaVu Sans for reportlab. The PDF
# generator discovers these files at runtime and never ships font binaries.
RUN apt-get update \
  && apt-get install -y --no-install-recommends fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --no-cache-dir "fastapi" "uvicorn[standard]" sqlalchemy alembic "psycopg[binary]" pydantic pydantic-settings "python-jose[cryptography]" python-multipart redis minio httpx openpyxl xlrd reportlab python-dateutil pytest \
  && useradd -r -u 10001 appuser \
  && mkdir -p /code/var/files /tmp/rtk-imports /app/storage /app/reports \
  && chown -R appuser:appuser /code /tmp/rtk-imports /app/storage /app/reports
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

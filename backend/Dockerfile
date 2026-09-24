FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml ./
# Cyrillic PDF runtime (P4-04-02): DejaVu Sans for reportlab. The PDF
# generator discovers these files at runtime and never ships font binaries.
RUN apt-get update \
  && apt-get install -y --no-install-recommends fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --no-cache-dir "fastapi==0.116.1" "uvicorn[standard]==0.35.0" "sqlalchemy==2.0.43" "alembic==1.16.5" "psycopg[binary]==3.3.4" "pydantic==2.11.7" "pydantic-settings==2.10.1" "python-jose[cryptography]==3.5.0" "python-multipart==0.0.32" "redis==6.4.0" "minio==7.2.18" "httpx==0.28.1" "openpyxl==3.1.5" "xlrd==2.0.2" "reportlab==4.4.9" "python-dateutil==2.9.0.post0" pytest==9.0.3 \
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

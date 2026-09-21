FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml ./
# Full runtime set from pyproject.toml dependencies (P0-5: Dockerfile must
# stay a superset of pyproject — see tests/test_p0_docker_deps.py).
RUN pip install --no-cache-dir "fastapi" "uvicorn[standard]" sqlalchemy alembic "psycopg[binary]" pydantic pydantic-settings "python-jose[cryptography]" python-multipart redis minio httpx openpyxl xlrd reportlab python-dateutil pytest \
  && useradd -r -u 10001 appuser \
  && mkdir -p /code/var/files /tmp/rtk-imports /app/storage \
  && chown -R appuser:appuser /code /tmp/rtk-imports /app/storage
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

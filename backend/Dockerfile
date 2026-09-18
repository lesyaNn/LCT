FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi" "uvicorn[standard]" sqlalchemy alembic "psycopg[binary]" pydantic pydantic-settings "python-jose[cryptography]" python-multipart httpx pytest
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
ENV PYTHONPATH=/code
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"
CMD ["./entrypoint.sh"]

FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi" "uvicorn[standard]" sqlalchemy "psycopg[binary]" pydantic-settings "python-jose[cryptography]" python-multipart httpx pytest
COPY app ./app
ENV PYTHONPATH=/code
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

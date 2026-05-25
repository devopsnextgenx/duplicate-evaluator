FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DUPEVAL_CONFIG=/app/config.yml

COPY pyproject.toml config.yml README.md ./
COPY duplicate_evaluator ./duplicate_evaluator

RUN pip install --no-cache-dir -e .

EXPOSE 8765

CMD ["python", "-m", "duplicate_evaluator.main", "--host", "0.0.0.0", "--port", "8765"]

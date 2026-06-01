FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tashkent \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

# Avval dependencies
COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=120 --retries=10 -r requirements.txt

# Kod
COPY bot ./bot

# SQLite data va log papkalar
RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "bot.main"]
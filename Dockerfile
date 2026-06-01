FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tashkent

WORKDIR /app

# Avval dependencies (kesh uchun)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kod
COPY bot ./bot

# Ma'lumotlar (SQLite) va loglar uchun papkalar (volume bilan almashtiriladi)
RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "bot.main"]

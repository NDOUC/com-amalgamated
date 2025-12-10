FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY ../requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y build-essential libnss3 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libasound2 wget git \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CloudBase 云托管默认注入 PORT（通常为 80），main.py 已优先读取；本地/compose 回退 8123
EXPOSE 80

CMD ["python", "main.py"]
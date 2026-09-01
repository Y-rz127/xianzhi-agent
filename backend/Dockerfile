FROM python:3.11-slim

WORKDIR /app

# 国内 pip 镜像加速构建（腾讯云内网镜像 + 重试/超时，避开清华 403 问题）
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple \
    PIP_RETRIES=5 \
    PIP_TIMEOUT=60

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# 容器入口监听端口对齐 CloudBase「服务端口设置」(80)；main.py 在容器内强制监听 80（除非显式设置 PORT），本地可用 PORT/APP_PORT 覆盖
EXPOSE 80

CMD ["python", "main.py"]
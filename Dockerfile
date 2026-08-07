FROM python:3.11-slim

WORKDIR /app

# 国内镜像（pip + HuggingFace），加速构建
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    HF_ENDPOINT=https://hf-mirror.com

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# 构建时把 BGE 模型烤进镜像（部署即用，免冷启下载）
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', local_dir='/app/models/bge')"

COPY . .
# 容器入口监听端口对齐 CloudBase「服务端口设置」(80)；main.py 在容器内强制监听 80（除非显式设置 PORT），本地可用 PORT/APP_PORT 覆盖
EXPOSE 80

CMD ["python", "main.py"]
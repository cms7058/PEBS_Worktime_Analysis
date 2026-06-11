# PEBS 工时分析系统 — 多阶段构建
# 阶段1：构建前端；阶段2：Python 运行时（含前端产物，单容器部署）
# 镜像源已适配境内网络（npmmirror + 腾讯云 PyPI）

FROM node:22-alpine AS web
WORKDIR /build
COPY web/package*.json ./
RUN npm config set registry https://registry.npmmirror.com && npm ci
COPY web/ ./
RUN npm run build


FROM python:3.11-slim
WORKDIR /app

# opencv/mediapipe 运行时依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.cloud.tencent.com/pypi/simple

# 代码与模型（MediaPipe 模型已入库，境内服务器无需访问 Google 下载）
COPY pipeline/ pipeline/
COPY server/ server/
COPY pmts/ pmts/
COPY agent/ agent/
COPY configs/ configs/
COPY models/ models/
COPY --from=web /build/dist web/dist/

# data/（SQLite 数据库 + 上传视频）通过卷挂载持久化，见 docker-compose.yml
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD curl -sf http://localhost:8000/tutorials >/dev/null || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]

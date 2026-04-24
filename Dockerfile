# ============================================================
# Eyeris — AI-Powered Photo Organizer
# Your Pictures. Fast. Easy. Simple.
# ============================================================
#
# Multi-stage build:
#   Stage 1: frontend-build    — Node.js, builds the React SPA
#   Stage 2: backend-runtime   — Python (CPU PyTorch + minimal NVIDIA libs)
# ============================================================

# ── Stage 1: Frontend build ──────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
ARG NODE_ENV=production
ENV NODE_ENV=production
RUN npm run build

# ── Stage 2: Backend runtime ────────────────────────────────────────
FROM python:3.12-slim AS backend-runtime

LABEL org.opencontainers.image.source="https://github.com/vonhex/Eyeris" \
      org.opencontainers.image.description="Eyeris — AI-Powered Photo Organizer" \
      maintainer="vonhex"

# NVIDIA toolkit (for GPU access at runtime via nvidia-container-toolkit)
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        file \
        cmake \
        libmagic1 \
        libgomp1 \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/*

# Python deps
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
        numpy opencv-python-headless transformers onnxruntime \
        nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-nccl-cu12 \
    && rm -rf /usr/local/lib/python3.12/site-packages/cusparselt \
           /usr/local/lib/python3.12/site-packages/triton \
           /usr/local/lib/python3.12/site-packages/_polars_runtime_32 \
           /usr/local/lib/python3.12/site-packages/sympy \
    && find /usr/local/lib/python3.12/site-packages/ -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Backend source + pre-built frontend
COPY backend/ ./
COPY --from=frontend-build /build/dist /app/frontend/dist

# Create data directories and ensure they are writable
RUN mkdir -p /data/images /data/thumbnails /data/db \
    && chmod -R 777 /data

ENV PYTHONUNBUFFERED=1 \
    TZ=Etc/UTC

EXPOSE 8000

# Volume mounts
VOLUME ["/data/images", "/data/thumbnails", "/data/db"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

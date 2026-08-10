# syntax=docker/dockerfile:1

# ---------- Stage 1: build dependencies ----------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip

# ต้อง copy README.md มาด้วย เพราะ pyproject.toml อ้างถึง readme = "README.md"
# และต้องเพิ่ม [tool.hatch.build.targets.wheel] packages = ["app"] ใน pyproject.toml
# ไม่งั้น hatchling จะหา package ไม่เจอ (โฟลเดอร์ชื่อ "app" ไม่ตรงกับชื่อโปรเจกต์ "village-guard-backend")
COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir --prefix=/install .


# ---------- Stage 2: runtime image ----------
FROM python:3.12-slim AS runtime

# gosu ใช้สำหรับ drop จาก root -> appuser หลัง fix permission ของ volume ตอน container start
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system appuser \
    && useradd --system --gid appuser --create-home --home-dir /home/appuser appuser

COPY --from=builder /install /usr/local

WORKDIR /app

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY create_superadmin.py ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/storage \
    && chown -R appuser:appuser /app /home/appuser \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_PATH=/app/storage

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# หมายเหตุสำคัญ: ห้ามใส่ --workers เกิน 1
# เพราะ rate limiter / account lockout / SSE pub-sub / presence tracking
# เก็บ state ไว้ใน memory ระดับ process เดียว (ดู app/core/rate_limit.py,
# app/core/account_lockout.py, app/services/sse_service.py, app/services/presence_service.py)
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
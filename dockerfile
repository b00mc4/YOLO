# 1. ใช้ Python 3.11 (ขนาดเล็ก)
FROM python:3.11-slim

# 2. ตั้งค่า Environment Variables พื้นฐานของ Python แบบ Production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. สร้าง User ที่ไม่ใช่ Root เพื่อความปลอดภัยสูงสุด (Security Best Practice)
RUN addgroup --system appgroup && adduser --system --group appuser

# 4. กำหนดโฟลเดอร์ทำงาน
WORKDIR /app

# 5. ติดตั้ง OS Dependencies ที่จำเป็น (เช่น timezone, ตัวช่วย build) และลบ Cache ทันที
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 6. ก๊อปปี้และติดตั้ง Library (แยกชั้น Layer เพื่อให้ Build เร็วขึ้นในครั้งหน้า)
COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# 7. ก๊อปปี้ Source Code ทั้งหมด
COPY . /app/

# 8. เปลี่ยนเจ้าของไฟล์ให้เป็นของ non-root user ที่สร้างไว้
RUN chown -R appuser:appgroup /app

# 9. สลับไปใช้ non-root user
USER appuser

# 10. เปิด Port
EXPOSE 8000

# 11. คำสั่งตอนรัน Container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

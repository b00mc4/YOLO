# Village Guard Backend — Project Context & Architecture

> **Village Guard Backend** คือระบบ Backend API สำหรับระบบรักษาความปลอดภัยหมู่บ้านอัจฉริยะ พร้อมการตรวจจับและรู้จำป้ายทะเบียนรถ (License Plate Recognition / LPR - YOLO + OCR) แบบ Real-time, ระบบจัดการกล้องและสตรีมวิดีโอ (MediaMTX / RTSP / WebRTC), ระบบแจ้งเตือนฉุกเฉิน (SSE / Email), และการควบคุมสิทธิ์แบบ Multi-tenant (Superadmin, Admin, User).

---

## 1. ข้อมูลภาพรวมโครงการ (Project Overview)

- **ชื่อโครงการ:** `village-guard-backend`
- **เวอร์ชัน:** `0.1.0`
- **ภาษา / Runtime:** Python >= 3.11
- **Framework หลัก:** [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous Web Framework)
- **ASGI Server:** Uvicorn
- **ฐานข้อมูล:** PostgreSQL (เชื่อมต่อแบบ Async ผ่าน `asyncpg` + `SQLAlchemy 2.0`)
- **Database Migration:** Alembic
- **การจัดการภาพและไฟล์:** Pillow, Local Disk Storage (`storage/`)
- **การแจ้งเตือน Real-time:** Server-Sent Events (SSE via `sse-starlette`)
- **การสตรีมมิ่งวิดีโอ:** MediaMTX (RTSP/WebRTC/HLS Authentication & Token Issuance)
- **การเชื่อมต่อโมเดล AI:** AI Vision Service (YOLO + OCR Webhook & Camera Sync API)
- **ระบบเมล:** aiosmtplib (SMTP Async สำหรับส่งลิงก์ยืนยันตัวตนและรีเซ็ตรหัสผ่าน)

---

## 2. สถาปัตยกรรมระบบ (System Architecture)

```mermaid
graph TD
    subgraph "External Systems & Devices"
        CCTV["CCTV / IP Camera (RTSP / ONVIF)"]
        MediaMTX["MediaMTX Server (RTSP / WebRTC)"]
        AIVision["AI Vision Service (YOLO + OCR)"]
        SMTP["SMTP Server (Email Delivery)"]
    end

    subgraph "Frontend Client"
        WebUI["Web App / Dashboard (React / Next.js)"]
    end

    subgraph "Village Guard Backend (FastAPI)"
        API["FastAPI API Gateway / Routers"]
        AuthMid["Auth & Security (JWT, Argon2, Rate Limit)"]
        SSEHub["SSE Hub (Real-time Broadcast)"]
        Storage["Storage Service (Local FS)"]
        DBEngine["Async SQLAlchemy 2.0"]
        BgTasks["Background Tasks & Resync Loop"]
    end

    subgraph "Database"
        Postgres[(PostgreSQL DB)]
    end

    CCTV -->|RTSP Stream| MediaMTX
    MediaMTX -->|Auth Webhook| API
    AIVision -->|Detection Webhook multipart/form-data| API
    API -->|Register/Sync RTSP| AIVision
    WebUI -->|REST API / JWT| API
    WebUI -->|SSE Connection| SSEHub
    WebUI <-->|WebRTC Stream with JWT| MediaMTX
    API -->|Async SMTP| SMTP
    API --> DBEngine
    DBEngine --> Postgres
    API --> Storage
```

---

## 3. โครงสร้างโฟลเดอร์ของโปรเจกต์ (Directory Structure)

```text
YOLOOO/
├── .env                       # Environment variables config
├── alembic/                   # Database migrations configuration & scripts
│   ├── versions/              # Migration revision scripts (Alembic)
│   └── env.py                 # Async migration runner
├── alembic.ini                # Alembic configuration
├── app/                       # Source code หลักของแอปพลิเคชัน
│   ├── api/                   # API Route Layer
│   │   ├── deps.py            # Dependency Injection (Auth, Role check, API Key, Rate limit)
│   │   ├── router.py          # รวม Route ทั้งหมดเข้า prefix /api
│   │   └── endpoints/         # Controllers แยกตามโมดูล
│   │       ├── audit_logs.py      # บันทึกประวัติและตรวจสอบ Audit Logs
│   │       ├── auth.py            # Login, Register, Refresh Token, Password reset, Verify email
│   │       ├── blacklist.py       # จัดการป้ายทะเบียนต้องสงสัย/ห้ามเข้า
│   │       ├── camera.py          # จัดการกล้องวงจรปิด, ONVIF, Resync, Test Stream
│   │       ├── contacts.py        # จัดการเบอร์ติดต่อฉุกเฉินและหน่วยงาน
│   │       ├── detection.py       # รับ Webhook จาก AI Vision, Dashboard Stats, Route Tracking
│   │       ├── mediamtx.py        # สร้าง Stream Token และ MediaMTX Auth
│   │       ├── notifications.py   # จัดการการแจ้งเตือนในระบบ
│   │       ├── reports.py         # รายงานสรุปการเข้า-ออก, สถิติช่วงเวลาเร่งด่วน
│   │       ├── sse.py             # Server-Sent Events สำหรับ Real-time Feed
│   │       ├── users.py           # จัดการผู้ใช้งานในแต่ละหมู่บ้าน และ Superadmin
│   │       ├── villages.py        # จัดการโครงการ/หมู่บ้าน (Multi-tenancy)
│   │       └── whitelist.py       # จัดการป้ายทะเบียนลูกบ้าน/ที่ได้รับอนุญาต
│   ├── core/                  # Configurations & Shared Utilities
│   │   ├── account_lockout.py    # ระบบระงับบัญชีเมื่อรหัสผ่านผิดหลายครั้ง
│   │   ├── alert_cooldown.py     # หน่วงเวลาการแจ้งเตือนไม่ให้ส่งซ้ำรัวๆ
│   │   ├── config.py             # Pydantic BaseSettings อ่านค่าจาก .env
│   │   ├── connection_limit.py   # จัดการจำกัดจำนวนการเชื่อมต่อ SSE
│   │   ├── contact_format.py     # Format ข้อมูลเบอร์โทรศัพท์/ผู้ติดต่อ
│   │   ├── error_messages.py     # ข้อความ Error กลางที่เป็นระเบียบ
│   │   ├── exceptions.py         # Custom Exception Handlers
│   │   ├── rate_limit.py         # In-memory Token Bucket Rate Limiter
│   │   ├── security.py           # Argon2 Password Hashing & JWT Encode/Decode
│   │   ├── sse_channel.py        # จัดการ Channel และ Pub/Sub ของ SSE
│   │   ├── timezone.py           # Timezone conversion & utilities
│   │   └── url_utils.py          # Helper functions สำหรับจัดการ URLs
│   ├── db/                    # Database Session & Base Models
│   │   ├── base.py               # Import รวม models สำหรับ Alembic autogenerate
│   │   ├── base_class.py         # SQLAlchemy Declarative Base
│   │   └── session.py            # Async Engine & async_sessionmaker
│   ├── models/                # SQLAlchemy ORM Models
│   │   ├── audit_log.py          # ตาราง AuditLogTABLE
│   │   ├── blacklist.py          # ตาราง BlacklistTABLE
│   │   ├── camera.py             # ตาราง CameraTABLE
│   │   ├── car.py                # ตาราง CarTABLE (ประวัติการตรวจจับ)
│   │   ├── contact.py            # ตาราง ContactTABLE
│   │   ├── group.py              # ตาราง GroupTABLE (โครงการ/หมู่บ้าน)
│   │   ├── notification.py       # ตาราง NotificationTABLE
│   │   ├── refresh_token.py      # ตาราง RefreshTokenTABLE
│   │   ├── user.py               # ตาราง UserTABLE
│   │   ├── verify.py             # ตาราง VerifyTABLE (Email Token)
│   │   └── whitelist.py          # ตาราง WhitelistTABLE
│   ├── schemas/               # Pydantic Request/Response Schemas
│   │   ├── audit_log.py, auth.py, blacklist.py, camera.py, car.py,
│   │   ├── common.py, contact.py, notification.py, presence.py,
│   │   ├── report.py, security_alert.py, sse.py, user.py, village.py, whitelist.py
│   └── services/              # Business Logic Services
│       ├── ai_vision_service.py           # สื่อสารกับ AI Vision (YOLO) Webhook & Config
│       ├── audit_service.py               # บันทึก Action Logs
│       ├── auth_service.py                # ตรวจสอบสิทธิ์, Hash, Token, Session
│       ├── blacklist_service.py           # Business logic บัญชีดำ
│       ├── camera_service.py              # จัดการกล้องและตรวจสอบ RTSP
│       ├── camera_sync_service.py         # ซิงค์กล้องกับ AI Vision Background
│       ├── camera_verification_service.py # ตรวจสอบความพร้อมของ Stream กล้อง
│       ├── channel_service.py             # ควบคุม SSE Channel
│       ├── contact_service.py             # จัดการเบอร์ติดต่อ
│       ├── detection_service.py           # ประมวลผลผลลัพธ์ตรวจจับป้ายทะเบียน บันทึกรูปภาพ ตรวจสอบ Blacklist/Whitelist
│       ├── email_service.py               # ส่ง Email อัตโนมัติ (HTML Template)
│       ├── login_security_service.py      # ป้องกัน Brute force การ Login
│       ├── mediamtx_auth_service.py       # ยืนยันสิทธิ์ MediaMTX Streaming
│       ├── mediamtx_service.py            # ติดต่อ MediaMTX API
│       ├── notification_service.py        # จัดการ Notification & Cleanup
│       ├── onvif_service.py               # ค้นหากล้อง ONVIF อัตโนมัติ
│       ├── presence_service.py            # ตรวจสอบสถานะรถที่ยังอยู่ภายในโครงการ (In-Village Presence)
│       ├── report_service.py              # คำนวณ Report และสถิติ
│       ├── session_validation_service.py  # ตรวจสอบ Session ที่หมดอายุ
│       ├── storage_service.py             # บันทึกไฟล์ภาพ Crop และภาพเต็มลง Disk
│       ├── user_service.py                # CRUD จัดการสิทธิ์ User
│       ├── village_service.py             # CRUD จัดการหมู่บ้าน
│       └── whitelist_service.py           # จัดการป้ายทะเบียนลูกบ้าน
├── storage/                   # โฟลเดอร์เก็บภาพ Crop และภาพตัวรถเต็ม
├── create_superadmin.py       # Script สำหรับสร้าง Superadmin คนแรก
├── pyproject.toml             # Project dependencies & build config
├── mediamtx.exe & .yml        # MediaMTX RTSP Server Binary & Config
└── ngrok.exe                  # Tunnel utility สำหรับทดสอบ Webhook ภายนอก
```

---

## 4. โครงสร้างฐานข้อมูลและความสัมพันธ์ (Database Schema & Relationships)

```mermaid
erDiagram
    GroupTABLE ||--o{ UserTABLE : "has users"
    GroupTABLE ||--o{ CameraTABLE : "has cameras"
    GroupTABLE ||--o{ CarTABLE : "has detection logs"
    GroupTABLE ||--o{ BlacklistTABLE : "has blacklist"
    GroupTABLE ||--o{ WhitelistTABLE : "has whitelist"
    GroupTABLE ||--o{ AuditLogTABLE : "has audit logs"
    GroupTABLE ||--o{ NotificationTABLE : "has notifications"

    UserTABLE ||--o{ VerifyTABLE : "has email tokens"
    UserTABLE ||--o{ ContactTABLE : "has contacts"
    UserTABLE ||--o{ RefreshTokenTABLE : "has sessions"
    UserTABLE ||--o{ BlacklistTABLE : "added by"
    UserTABLE ||--o{ WhitelistTABLE : "added by"
    UserTABLE ||--o{ AuditLogTABLE : "performed by"
    UserTABLE ||--o{ NotificationTABLE : "receives"

    CameraTABLE ||--o{ CarTABLE : "detects vehicles"

    GroupTABLE {
        uuid id PK
        string name
        boolean is_active
        timestamp created_at
    }

    UserTABLE {
        uuid id PK
        string username UK
        string fullname
        string email UK
        string hashpassword
        string avatar_path
        enum role "superadmin, admin, user"
        uuid village_id FK
        boolean is_active
        boolean is_verify
        timestamp password_changed_at
        timestamp created_at
    }

    CameraTABLE {
        uuid id PK
        uuid village_id FK
        string name
        float lat
        float long
        string stream_ai UK "RTSP Stream"
        enum direction "entry, exit"
        enum verification_status "pending, verified, failed"
        timestamp ai_vision_synced_at
        boolean is_active
        timestamp created_at
    }

    CarTABLE {
        uuid id PK
        uuid event_id UK
        uuid camera_id FK
        uuid village_id FK
        string camera_name
        float camera_lat
        float camera_long
        string license_plate
        string province
        string color
        string image_crop
        string image_full
        timestamp time_detect
        boolean is_blacklist
        boolean is_whitelist
        enum direction "entry, exit"
        timestamp created_at
    }

    WhitelistTABLE {
        uuid id PK
        uuid village_id FK
        string license_plate
        string province
        string owner_name
        string house_number
        string note
        uuid added_by FK
        timestamp created_at
    }

    BlacklistTABLE {
        uuid id PK
        uuid village_id FK
        string license_plate
        string province
        string reason
        uuid added_by FK
        timestamp created_at
    }
```

---

## 5. บทบาทและสิทธิ์ผู้ใช้งาน (Roles & Permissions)

| Role | ขอบเขตการทำงาน (Scope) | ความสามารถหลัก (Key Capabilities) |
| :--- | :--- | :--- |
| **`superadmin`** | ระบบทั้งหมด (System-wide) | - จัดการโครงการหมู่บ้านทั้งหมด (สร้าง/แก้ไข/ระงับโครงการ)<br>- สร้างและจัดการแอดมินของแต่ละหมู่บ้าน<br>- เข้าถึง Audit Logs ทั้งหมด<br>- `village_id` เป็น `NULL` |
| **`admin`** | เฉพาะหมู่บ้านตนเอง (`village_id`) | - จัดการกล้องวงจรปิดในหมู่บ้าน (เพิ่ม/ลบ/ทดสอบสตรีม)<br>- จัดการลูกบ้าน (Users/Staff) ภายในโครงการ<br>- จัดการ Whitelist / Blacklist<br>- ดูประวัติการตรวจจับ, Dashboard สถิติ, และดาวน์โหลดรายงาน |
| **`user`** (รปภ. / เจ้าหน้าที่) | เฉพาะหมู่บ้านตนเอง (`village_id`) | - ดู Real-time Detection Feed ผ่าน SSE<br>- ตรวจสอบสถานะรถเข้า-ออก (Presence Tracking)<br>- ดูประวัติการเข้า-ออกของยานพาหนะ<br>- จัดการเบอร์ติดต่อฉุกเฉิน |

---

## 6. โฟลว์การทำงานสำคัญ (Core Workflows)

### 6.1 การตรวจจับยานพาหนะ (LPR Webhook & Processing Flow)
1. **AI Vision Service** ตรวจพบป้ายทะเบียนจากกล้อง CCTV ผ่านโมเดล YOLO + OCR
2. **AI Vision Service** ยิง `POST /api/detections` พร้อม `X-API-Key` ในรูปแบบ `multipart/form-data`:
   - `event_id`, `camera_id`, `license_plate`, `province`, `color`, `capture_time`
   - `image_crop` (รูปตัดเฉพาะป้ายทะเบียน), `image_full` (รูปเต็มรถ)
3. **Backend (`detection_service.py`)**:
   - บันทึกรูปภาพลง Local Storage (`storage/`)
   - ตรวจสอบกับฐานข้อมูล **Whitelist** และ **Blacklist** ของหมู่บ้านนั้นๆ
   - บันทึกลงตาราง `CarTABLE`
   - หากพบว่าเป็น **Blacklist**: สร้าง Notification แจ้งเตือนฉุกเฉินทันที
   - ส่งข้อมูลผ่าน **SSE Channel** ไปยัง Web UI ของเจ้าหน้าที่แบบ Real-time

### 6.2 การสตรีมวิดีโอแบบสด (Live Streaming with MediaMTX)
1. Web Client ร้องขอ Token ผ่าน `POST /api/mediamtx/stream-token`
2. Backend ตรวจสอบสิทธิ์และออก JWT Private Key สำหรับอ่านสตรีมของกล้องตัวนั้นๆ
3. Web Client ใช้ WebRTC / WHEP เชื่อมต่อไปยัง MediaMTX Server พร้อม Token
4. MediaMTX ยิง Webhook มาตรวจสอบกับ Backend (`POST /api/mediamtx/auth`) เพื่ออนุญาตการสตรีม

### 6.3 วงจรการเริ่มต้นระบบ (FastAPI Lifespan)
เมื่อ Backend เริ่มต้นทำงาน (`main.py`):
1. **Camera Resync Task**: ซิงค์กล้องทั้งหมดในฐานข้อมูลไปยัง AI Vision Service อัตโนมัติ (พร้อม Exponential Backoff 3 ครั้ง)
2. **Camera Verification Resume**: สานต่อการตรวจสอบกล้องที่ค้างอยู่ในสถานะ Pending
3. **Notification Cleanup Loop**: รัน Background Task ทุก 24 ชั่วโมง เพื่อลบการแจ้งเตือนเก่าที่หมดอายุ

---

## 7. ตัวแปรสภาพแวดล้อมที่สำคัญ (`.env` Configuration)

| Variable | คำอธิบาย |
| :--- | :--- |
| `DATABASE_URL` | PostgreSQL Async Connection String เช่น `postgresql+asyncpg://user:pass@localhost:5432/dbname` |
| `JWT_SECRET` | Secret key สำหรับ Sign JWT Token |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | อายุ Access Token (ค่าเริ่มต้น: 15 นาที) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | อายุ Refresh Token (ค่าเริ่มต้น: 30 วัน) |
| `API_KEY` | API Key สำหรับการรับส่งข้อมูลระหว่าง Backend กับ AI Vision Service |
| `STORAGE_PATH` | ตำแหน่งโฟลเดอร์สำหรับเก็บรูปภาพ เช่น `./storage` |
| `FRONTEND_URL` | URL ของ Frontend (สำหรับลิงก์ Reset Password / Verify Email) |
| `BACKEND_PUBLIC_URL` | Public URL ของ Backend (ส่งให้ AI Vision สำหรับ Webhook Callback) |
| `CORS_ALLOWED_ORIGINS` | รายชื่อ Origins ที่อนุญาต CORS (คั่นด้วย comma) |
| `SMTP_*` | การตั้งค่า SMTP สำหรับส่งอีเมล (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`) |
| `MEDIAMTX_*` | การตั้งค่า MediaMTX API และ Public URL สำหรับ Live Stream |
| `AI_VISION_API_*` | URL และ API Key สำหรับสื่อสารกับ AI Vision Service (YOLO) |
| `MEDIAMTX_JWT_PRIVATE_KEY_B64` | RSA Private Key แบบ Base64 สำหรับเซ็นชื่อ Stream Token |

---

## 8. คู่มือการเริ่มต้นใช้งาน (Getting Started)

### ติดตั้ง Dependencies
```bash
# แนะนำใช้ Python 3.11+
pip install -e .
```

### การตั้งค่าฐานข้อมูล (Database Migration)
```bash
# อัปเดตฐานข้อมูลให้เป็นเวอร์ชันล่าสุด
alembic upgrade head
```

### สร้าง Superadmin คนแรก
```bash
python create_superadmin.py
```

### รันเซิร์ฟเวอร์ Backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---
*เอกสารนี้ถูกสแกนและจัดทำโดย Antigravity เพื่อใช้เป็น Context อ้างอิงสถาปัตยกรรมและการพัฒนาต่อยอดของระบบ Village Guard Backend*

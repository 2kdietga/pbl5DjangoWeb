# Core - Driver Violation Monitoring System

Du an Django nay xay dung he thong giam sat hanh vi tai xe tu camera/thiet bi gan tren xe. Thiet bi upload frame anh ve server, server xac thuc bang device token, xac dinh tai xe bang `card_uid`, chay AI de phat hien vi pham va tao bang chung cho tai xe xem lai tren giao dien web.

He thong hien ho tro 3 nhom vi pham:

- `Drowsiness`: tai xe nham mat/buon ngu qua nguong.
- `Head Turn`: tai xe quay dau trai/phai qua nguong trong mot khoang thoi gian.
- `Phone`: tai xe co dau hieu su dung dien thoai, duoc phat hien bang model video classification CNN + GRU.

## Tech Stack

- Backend: `Django 5.0.14`, `Django REST Framework`
- Database: `SQLite3`
- AI / Computer Vision: `MediaPipe`, `OpenCV`, `PyTorch`, `NumPy`, `Pillow`
- Frontend: Django Templates, Bootstrap, jQuery
- Static serving: `WhiteNoise`
- Production server: `Gunicorn`
- Container: `Docker`
- Video evidence: `OpenCV VideoWriter`, co the convert sang H.264 MP4 bang `ffmpeg`

## Project Structure

```text
core/
  accounts/        Custom user, auth, profile, card_uid
  ai/
    drowsiness/    MediaPipe EAR/yaw detection
    phone/         CNN + GRU phone usage detection
    models/        AI model files
  api/             Upload frame API
  categories/      Violation categories
  core/            Django settings, urls, wsgi/asgi
  devices/         Device management, latest frame, live view
  media/           Runtime uploads: frames, images, videos
  static/          Static files
  templates/       HTML templates
  vehicles/        Vehicle model
  violations/      Violations and appeal workflow
  manage.py
  requirements.txt
  Dockerfile
```

## Domain Model

### Account

`accounts.Account` la custom user model, dang nhap bang `email`.

Thong tin quan trong:

- `email`, `username`, `first_name`, `last_name`, `phone_number`
- `card_uid`: UID the RFID de map frame upload voi tai xe
- `is_admin`, `is_staff`, `is_active`, `is_superadmin`
- `UserImage`: luu anh nguoi dung, co the danh dau avatar

### Vehicle

`vehicles.Vehicle` luu thong tin xe:

- `license_plate`
- `model`
- `registration_date`

### Device

`devices.Device` dai dien cho camera/thiet bi gan tren xe:

- `name`
- `token`: token unique, gui trong header `X-DEVICE-TOKEN`
- `vehicle`: xe dang gan voi thiet bi
- `is_active`
- `last_seen`
- `latest_frame`, `latest_frame_at`

### Category

`categories.Category` dinh nghia loai vi pham:

- `name`
- `description`
- `severality_level`
- `is_active`
- `created_at`

### Violation

`violations.Violation` la ban ghi vi pham:

- `category`
- `reporter`: tai xe bi ghi nhan
- `vehicle`
- `title`, `description`
- `reported_at`
- `image`: anh bang chung/thumbnail
- `video`: video bang chung
- `viewed`
- `status`: `pending`, `confirmed`, `dismissed`, `appealed`

### ViolationAppeal

`violations.ViolationAppeal` cho phep tai xe khang cao:

- moi vi pham chi co mot appeal
- `reason`
- `status`: `pending`, `approved`, `rejected`
- `admin_note`
- `created_at`, `reviewed_at`

Khi staff chap nhan appeal, violation duoc chuyen sang `dismissed`. Khi tu choi, violation duoc chuyen sang `confirmed`.

## AI Pipeline

He thong co 2 pipeline AI chay song song tren moi frame upload.

### Drowsiness va Head Turn

Module: `ai/drowsiness/`

Thanh phan chinh:

- `engine.py`: doc anh, chay MediaPipe Face Landmarker, tinh EAR va yaw
- `metrics.py`: tinh EAR, MAR, pitch, yaw, brightness
- `state.py`: luu state theo device token
- `mediapipe_loader.py`: lazy-load `face_landmarker.task`
- `video_utils.py`: export frame buffer thanh MP4

Co che:

- MediaPipe lay landmark khuon mat va transformation matrix.
- EAR duoc tinh tu moc mat trai/phai.
- He thong calibrate `baseline_ear` ban dau theo tung device.
- Mat duoc coi la nham khi EAR thap hon nguong theo baseline hoac nguong tuyet doi.
- Neu so frame nham mat lien tiep vuot `DROWSINESS_EYE_CLOSED_FRAMES`, tao vi pham `Drowsiness`.
- Yaw dau duoc tinh tu transformation matrix.
- Neu yaw vuot `DROWSINESS_HEAD_YAW_THRESHOLD`, `head_turn_score` tang.
- Neu score vuot `DROWSINESS_HEAD_TURN_VIOLATION_FRAMES`, tao vi pham `Head Turn`.

### Phone Usage

Module: `ai/phone/`

Model: `ai/models/model_ep26_val0.9268.pth`

Kien truc:

- `LightCNN`: 5 block `Conv2D + BatchNorm + ReLU + Pool`, tao vector dac trung 256 chieu cho moi frame
- `GRU`: 2 lop, hidden size 64, hoc quan he theo chuoi frame
- Classifier: `BatchNorm1d -> Linear(64, 32) -> ReLU -> Dropout -> Linear(32, 2)`
- Output: logits `[batch_size, 2]`, tuong ung `Safe` va `Phone`

Input runtime:

- Moi device co buffer 12 frame gan nhat trong RAM.
- Moi frame duoc resize ve `112x112`.
- Frame duoc normalize theo ImageNet mean/std.
- Khi du 12 frame, model nhan tensor `[1, 12, 3, 112, 112]`.
- Neu label la `Phone` va `phone_probability >= PHONE_CONFIDENCE_THRESHOLD`, API tao vi pham `Phone`.
- Chuoi 12 frame tai thoi diem trigger duoc export thanh video bang chung.

## Runtime State

State AI hien dang luu trong RAM:

- `STATE_STORE`: state cho drowsiness/head-turn
- `PHONE_STATE_STORE`: state cho phone detection

Dieu nay phu hop demo/prototype va mot worker. Khi restart server, state se mat. Neu scale nhieu worker/server, can dua state sang Redis hoac mot storage chia se.

Dockerfile hien tai chay Gunicorn voi `--workers 1`, phu hop voi cach luu state trong RAM.

## Main Flow

Endpoint chinh:

```text
POST /api/upload/
```

Luong xu ly:

1. Thiet bi gui `image`, `card_uid`, va header `X-DEVICE-TOKEN`.
2. API kiem tra token va lay `Device`.
3. Cap nhat `last_seen`.
4. Luu frame moi nhat vao `device.latest_frame`.
5. Tim tai xe bang `card_uid`.
6. Lay xe dang gan voi device.
7. Chay `ai.drowsiness.engine.process_frame()`.
8. Chay `ai.phone.engine.process_frame()`.
9. Neu khong co vi pham, tra JSON realtime.
10. Neu co vi pham, chon loai theo uu tien `Drowsiness -> Head Turn -> Phone`.
11. Kiem tra cooldown theo `reporter + vehicle + category`.
12. Export video bang chung neu co frame buffer.
13. Tao `Violation`, luu `image` fallback va `video` neu co.

## API Upload

Request:

```bash
curl -X POST http://127.0.0.1:8000/api/upload/ \
  -H "X-DEVICE-TOKEN: <device-token>" \
  -F "card_uid=<driver-card-uid>" \
  -F "image=@frame.jpg"
```

Response khi khong tao vi pham:

```json
{
  "ok": true,
  "eye_status": "EYE_OPEN",
  "eye_closed_streak": 0,
  "ear": 0.31,
  "baseline_ear": 0.32,
  "is_calibrated": true,
  "head_yaw": 0.0,
  "head_direction": "FORWARD",
  "head_turn_score": 0,
  "head_status": "SAFE",
  "phone_status": "SAFE",
  "phone_label": "Safe",
  "phone_confidence": 0.91,
  "phone_probability": 0.09,
  "phone_frames_collected": 12,
  "phone_sequence_length": 12,
  "violation": false,
  "vehicle": "ABC-123",
  "driver": "driver_username"
}
```

Response khi tao vi pham:

```json
{
  "ok": true,
  "violation": true,
  "created": true,
  "violation_id": 1,
  "violation_kind": "phone",
  "has_video": true
}
```

Gia tri `violation_kind` co the la:

- `eye`
- `head`
- `phone`

Loi thuong gap:

- `400 Missing image`
- `401 Missing X-DEVICE-TOKEN`
- `401 Invalid device token`
- `400 Missing card_uid`
- `404 Driver not found`
- `400 Device has no vehicle`
- `500 AI error: ...`
- `500 Phone AI error: ...`
- `500 Failed to export violation video`

## Web Routes

```text
/                                  Login page
/admin/                            Django admin
/accounts/register/                Register
/accounts/login/                   Login
/accounts/logout/                  Logout
/accounts/profile/                 Profile
/violations/list/                  Driver violation list
/violations/detail/<violation_id>/ Violation detail
/violations/<violation_id>/appeal/ Create appeal
/violations/admin/appeals/         Staff appeal list
/violations/admin/appeals/<id>/    Staff appeal detail
/violations/admin/appeals/<id>/review/ Approve/reject appeal
/devices/<id>/live/                Live camera and AI status
/devices/<id>/frame/               Latest device frame
/api/upload/                       Device upload API
```

## Settings

Quan trong trong `core/settings.py`:

```python
AUTH_USER_MODEL = "accounts.Account"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "violation_list"
LOGOUT_REDIRECT_URL = "login"

DROWSINESS_MODEL_PATH = BASE_DIR / "ai" / "models" / "face_landmarker.task"
DROWSINESS_FPS = 4
DROWSINESS_EYE_CLOSED_RATIO = 0.75
DROWSINESS_EYE_CLOSED_ABS = 0.20
DROWSINESS_EYE_CLOSED_FRAMES = 2 * DROWSINESS_FPS
DROWSINESS_CATEGORY_NAME = "Drowsiness"
DROWSINESS_VIOLATION_COOLDOWN_SECONDS = 30

HEAD_TURN_CATEGORY_NAME = "Head Turn"
HEAD_TURN_VIOLATION_COOLDOWN_SECONDS = 20
DROWSINESS_HEAD_YAW_THRESHOLD = 25
DROWSINESS_HEAD_TURN_VIOLATION_FRAMES = 2 * DROWSINESS_FPS
DROWSINESS_HEAD_TURN_DECAY = 1
DROWSINESS_BUFFER_SECONDS = 5

PHONE_MODEL_PATH = BASE_DIR / "ai" / "models" / "model_ep26_val0.9268.pth"
PHONE_CATEGORY_NAME = "Phone"
PHONE_VIOLATION_COOLDOWN_SECONDS = 30
PHONE_SEQUENCE_LENGTH = 12
PHONE_IMAGE_SIZE = 112
PHONE_CONFIDENCE_THRESHOLD = 0.7
PHONE_CLASS_LABELS = ["Safe", "Phone"]
```

Database/static/media:

```python
DATABASES["default"]["ENGINE"] = "django.db.backends.sqlite3"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_DIRS = ["core/static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
TIME_ZONE = "Asia/Ho_Chi_Minh"
```

## Run Locally

Yeu cau:

- Python 3.10
- Virtualenv
- `ffmpeg` neu muon video evidence phat on dinh tren browser

Chay local:

```bash
python -m venv venv310
venv310\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Truy cap:

```text
Web:   http://127.0.0.1:8000/
Admin: http://127.0.0.1:8000/admin/
```

## Demo Data

Can tao toi thieu:

1. `Account` co `card_uid`.
2. `Vehicle`.
3. `Device` active, co `token`, gan voi `Vehicle`.
4. Category co the tao san hoac de API tu tao: `Drowsiness`, `Head Turn`, `Phone`.

Sau do upload frame bang curl hoac client thiet bi:

```bash
curl -X POST http://127.0.0.1:8000/api/upload/ \
  -H "X-DEVICE-TOKEN: <device-token>" \
  -F "card_uid=<driver-card-uid>" \
  -F "image=@frame.jpg"
```

## Docker

Build:

```bash
docker build -t core-app .
```

Run:

```bash
docker run -p 10000:10000 core-app
```

Truy cap:

```text
http://127.0.0.1:10000/
```

Dockerfile hien tai:

- Dung `python:3.10-slim`.
- Cai thu vien he thong cho OpenCV/MediaPipe.
- Cai dependencies tu `requirements.txt`.
- Chay `collectstatic`.
- Chay Gunicorn tai port `10000`.
- Dung `--workers 1`.

Luu y: Dockerfile hien chua cai `ffmpeg`. Neu can video H.264 web-compatible, nen them `ffmpeg` vao apt packages.

## Runtime Files

Cac file/thu muc runtime:

- `db.sqlite3`: database local
- `media/live/`: frame moi nhat cua device
- `media/violations/`: anh bang chung
- `media/violations/videos/`: video bang chung
- `static/`: collected static/static root

## Production Notes

Cau hinh hien tai phu hop demo/prototype hon production:

- `DEBUG=True`
- `ALLOWED_HOSTS=["*"]`
- `SECRET_KEY` hard-code
- SQLite
- API upload chi xac thuc bang `X-DEVICE-TOKEN`
- AI state nam trong RAM

Huong nang cap:

- Dua secret va config ra environment variables.
- Dung PostgreSQL/MySQL thay SQLite.
- Dung Redis cho realtime AI state neu scale multi-worker.
- Them rate limit va logging cho `/api/upload/`.
- Cai `ffmpeg` trong Docker image.
- Bo sung test cho upload API, cooldown, appeal workflow va AI inference wrapper.


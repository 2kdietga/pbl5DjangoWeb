# Driver Violation Monitoring System

Dự án Django này xây dựng hệ thống giám sát hành vi tài xế từ camera hoặc thiết bị gắn trên xe. Thiết bị gửi frame ảnh về server, server xác thực bằng device token, định danh tài xế bằng `card_uid`, chạy các pipeline AI để phát hiện vi phạm và lưu bằng chứng cho tài xế xem lại trên giao diện web.

Hệ thống hiện hỗ trợ 3 nhóm vi phạm:

- `Drowsiness`: tài xế nhắm mắt hoặc buồn ngủ quá ngưỡng.
- `Head Turn`: tài xế quay đầu trái/phải quá lâu.
- `Phone`: tài xế có dấu hiệu sử dụng điện thoại.

## Tech Stack

- Backend: `Django 5.0.14`, `Django REST Framework`
- Database: `SQLite3`
- AI / Computer Vision: `OpenCV`, `PyTorch`, `TorchVision`, `NumPy`, `Pillow`
- Frontend: Django Templates, Bootstrap, jQuery
- Static serving: `WhiteNoise`
- Production server: `Gunicorn`
- Container: `Docker`
- Video evidence: `OpenCV VideoWriter`

## Project Structure

```text
core/
  accounts/        Custom user, auth, profile, card_uid
  ai/
    drowsiness/    Landmark-98 EAR/yaw detection
    phone/         CNN + GRU phone usage detection
    models/        AI model weights
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

## Main Flow

Endpoint chính:

```text
POST /api/upload/
```

Luồng xử lý:

1. Thiết bị gửi `image`, `card_uid` và header `X-DEVICE-TOKEN`.
2. API xác thực `Device` bằng token.
3. Server cập nhật `last_seen` và lưu frame mới nhất vào `device.latest_frame`.
4. Server tìm tài xế bằng `card_uid`.
5. Server lấy xe đang gắn với device.
6. Chạy AI drowsiness/head-turn bằng `ai.drowsiness.engine.process_frame()`.
7. Chạy AI phone usage bằng `ai.phone.engine.process_frame()`.
8. Nếu không có vi phạm, API trả JSON realtime.
9. Nếu có vi phạm, API chọn loại ưu tiên: `Drowsiness -> Head Turn -> Phone`.
10. Kiểm tra cooldown theo `reporter + vehicle + category`.
11. Export video bằng chứng từ frame buffer nếu có.
12. Tạo bản ghi `Violation`, lưu ảnh thumbnail/fallback và video bằng chứng.

## AI Pipeline

Hệ thống có 2 pipeline AI chạy trên mỗi frame upload:

- Drowsiness + Head Turn: dùng model landmark 98 điểm.
- Phone Usage: dùng model video classification CNN + GRU.

State AI hiện lưu trong RAM theo `device_key`. Cách này phù hợp demo/prototype và cấu hình `Gunicorn --workers 1`. Nếu scale nhiều worker/server, cần chuyển state sang Redis hoặc storage dùng chung.

## AI Input/Output

### Upload API Input

API nhận request dạng `multipart/form-data`.

| Thành phần | Tên | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Header | `X-DEVICE-TOKEN` | string | Có | Token của thiết bị camera |
| Form field | `card_uid` | string | Có | UID thẻ RFID để định danh tài xế |
| Form file | `image` | image file | Có | Frame ảnh hiện tại từ camera |

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8000/api/upload/ \
  -H "X-DEVICE-TOKEN: <device-token>" \
  -F "card_uid=<driver-card-uid>" \
  -F "image=@frame.jpg"
```

### Landmark-98 Model

File weights:

```text
ai/models/landmark_98_best.pth
```

Module liên quan:

- `ai/drowsiness/landmark98_loader.py`: load model, detect/crop mặt, tiền xử lý ảnh, suy luận heatmap.
- `ai/drowsiness/metrics.py`: tính EAR và yaw từ 98 landmark.
- `ai/drowsiness/engine.py`: quản lý state, calibration, streak, trigger vi phạm.

Input runtime của loader:

| Bước | Input | Shape/kiểu | Ghi chú |
| --- | --- | --- | --- |
| API frame | `image_file` | file ảnh | Đọc bằng Pillow, convert sang BGR |
| Face detect | `frame_bgr` | `H x W x 3` | OpenCV detect mặt để crop vùng mặt |
| Landmark model | `tensor_img` | `[1, 3, 256, 256]` | RGB, float32, normalize về khoảng `[-1, 1]` |

Output model landmark:

| Output | Shape/kiểu | Ý nghĩa |
| --- | --- | --- |
| `heatmaps` | `[1, 98, 64, 64]` | 98 heatmap, mỗi heatmap ứng với một landmark |
| `landmarks` | `numpy.ndarray`, shape `[98, 2]` | Tọa độ `(x, y)` của 98 điểm trên ảnh gốc |
| `face_box` | `(x, y, w, h)` | Bounding box mặt được dùng để crop |

Output sau khi tính metric:

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `ear` | float hoặc `None` | Eye Aspect Ratio sau khi smooth |
| `baseline_ear` | float | EAR nền sau calibration |
| `is_calibrated` | bool | Đã đủ frame để calibrate chưa |
| `eye_closed_streak` | int | Số frame nhắm mắt liên tiếp |
| `head_yaw` | float | Góc yaw ước lượng từ mũi và hai mắt |
| `head_direction` | string | `LEFT`, `RIGHT`, hoặc `FORWARD` |
| `head_turn_score` | int | Điểm tích lũy quay đầu |
| `head_status` | string | `SAFE`, `TURNING`, hoặc `VIOLATION` |

Output chính của `ai.drowsiness.engine.process_frame()`:

```json
{
  "status": "EYE_OPEN",
  "should_create_violation": false,
  "should_create_head_turn_violation": false,
  "eye_closed_streak": 0,
  "ear": 0.31,
  "baseline_ear": 0.32,
  "is_calibrated": true,
  "head_yaw": 0.0,
  "head_direction": "FORWARD",
  "head_turn_score": 0,
  "head_status": "SAFE",
  "drowsiness_frames_count": 0,
  "head_turn_frames_count": 0,
  "drowsiness_video_frames": [],
  "head_turn_video_frames": []
}
```

Các giá trị `status` có thể gặp:

- `NO_FACE`: không detect được mặt.
- `CALIBRATING`: đang thu frame để lấy `baseline_ear`.
- `EYE_OPEN`: mắt đang mở.
- `EYE_CLOSED`: mắt đang nhắm theo ngưỡng.

### Phone Usage Model

File weights:

```text
ai/models/model_ep26_val0.9268.pth
```

Module liên quan:

- `ai/phone/model.py`: định nghĩa `PhoneCNNGRU`.
- `ai/phone/engine.py`: load model, gom sequence frame, predict phone usage.
- `ai/phone/state.py`: lưu frame buffer theo device.

Input runtime:

| Bước | Input | Shape/kiểu | Ghi chú |
| --- | --- | --- | --- |
| API frame | `image_file` | file ảnh | Đọc bằng Pillow, giữ RGB |
| Frame buffer | `state.frames` | deque | Lưu các frame gần nhất theo device |
| Model input | `batch` | `[1, 12, 3, 112, 112]` | 12 frame, RGB, normalize ImageNet |

Output model:

| Output | Shape/kiểu | Ý nghĩa |
| --- | --- | --- |
| `logits` | `[1, 2]` | Điểm raw cho 2 class |
| `probabilities` | `[2]` | Xác suất sau softmax |
| `label` | string | `Safe` hoặc `Phone` |
| `phone_probability` | float | Xác suất class `Phone` |

Output chính của `ai.phone.engine.process_frame()`:

```json
{
  "status": "SAFE",
  "label": "Safe",
  "confidence": 0.91,
  "phone_probability": 0.09,
  "frames_collected": 12,
  "sequence_length": 12,
  "should_create_violation": false,
  "video_frames": []
}
```

Các giá trị `status` có thể gặp:

- `COLLECTING`: chưa đủ `PHONE_SEQUENCE_LENGTH` frame để predict.
- `SAFE`: không phát hiện sử dụng điện thoại.
- `PHONE`: phát hiện sử dụng điện thoại và vượt threshold.

## API Response

Response realtime khi không tạo vi phạm:

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

Response khi tạo vi phạm:

```json
{
  "ok": true,
  "eye_status": "EYE_CLOSED",
  "eye_closed_streak": 8,
  "ear": 0.14,
  "baseline_ear": 0.31,
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
  "violation": true,
  "created": true,
  "violation_id": 1,
  "violation_kind": "eye",
  "has_video": true
}
```

`violation_kind` có thể là:

- `eye`: vi phạm buồn ngủ/nhắm mắt.
- `head`: vi phạm quay đầu.
- `phone`: vi phạm sử dụng điện thoại.

Lỗi thường gặp:

- `400 Missing image`
- `401 Missing X-DEVICE-TOKEN`
- `401 Invalid device token`
- `400 Missing card_uid`
- `404 Driver not found`
- `400 Device has no vehicle`
- `500 AI error: ...`
- `500 Phone AI error: ...`
- `500 Failed to export violation video`

## Settings

Các cấu hình chính trong `core/settings.py`:

```python
AUTH_USER_MODEL = "accounts.Account"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "violation_list"
LOGOUT_REDIRECT_URL = "login"

DROWSINESS_LANDMARK98_MODEL_PATH = BASE_DIR / "ai" / "models" / "landmark_98_best.pth"
DROWSINESS_LANDMARK98_DEVICE = "auto"
DROWSINESS_FACE_CROP_MARGIN = 0.25
DROWSINESS_FACE_MIN_SIZE = 40
DROWSINESS_FACE_SCALE_FACTOR = 1.1
DROWSINESS_FACE_MIN_NEIGHBORS = 5
DROWSINESS_FPS = 4
DROWSINESS_EYE_CLOSED_RATIO = 0.75
DROWSINESS_EYE_CLOSED_ABS = 0.20
DROWSINESS_EYE_CLOSED_FRAMES = 2 * DROWSINESS_FPS
DROWSINESS_CATEGORY_NAME = "Drowsiness"
DROWSINESS_VIOLATION_COOLDOWN_SECONDS = 30
DROWSINESS_CALIB_FRAMES = 10

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

Ghi chú:

- `DROWSINESS_LANDMARK98_DEVICE = "auto"` sẽ dùng GPU nếu `torch.cuda.is_available()` là `True`, ngược lại dùng CPU.
- `DROWSINESS_HEAD_YAW_THRESHOLD` có thể cần chỉnh lại sau khi test camera thật, vì yaw hiện được ước lượng từ landmark 2D.
- `PHONE_SEQUENCE_LENGTH` càng lớn thì dự đoán ổn định hơn nhưng phản hồi chậm hơn.

## Run Locally

Yêu cầu:

- Python 3.10
- Virtualenv
- PyTorch/TorchVision đúng môi trường CPU hoặc CUDA
- `ffmpeg` nếu muốn video bằng chứng phát ổn định trên browser

Cài và chạy local:

```bash
python -m venv venv310
venv310\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Kiểm tra PyTorch:

```bash
python -c "import torch, torchvision; print(torch.__version__); print(torchvision.__version__); print(torch.cuda.is_available())"
```

Truy cập:

```text
Web:   http://127.0.0.1:8000/
Admin: http://127.0.0.1:8000/admin/
```

## Demo Data

Cần tạo tối thiểu:

1. `Account` có `card_uid`.
2. `Vehicle`.
3. `Device` active, có `token`, gắn với `Vehicle`.
4. Category có thể tạo sẵn hoặc để API tự tạo: `Drowsiness`, `Head Turn`, `Phone`.

Sau đó upload frame bằng curl hoặc client thiết bị:

```bash
curl -X POST http://127.0.0.1:8000/api/upload/ \
  -H "X-DEVICE-TOKEN: <device-token>" \
  -F "card_uid=<driver-card-uid>" \
  -F "image=@frame.jpg"
```

## Web Routes

```text
/                                      Login page
/admin/                                Django admin
/accounts/register/                    Register
/accounts/login/                       Login
/accounts/logout/                      Logout
/accounts/profile/                     Profile
/violations/list/                      Driver violation list
/violations/detail/<violation_id>/     Violation detail
/violations/<violation_id>/appeal/     Create appeal
/violations/admin/appeals/             Staff appeal list
/violations/admin/appeals/<id>/        Staff appeal detail
/violations/admin/appeals/<id>/review/ Approve/reject appeal
/devices/<id>/live/                    Live camera and AI status
/devices/<id>/frame/                   Latest device frame
/api/upload/                           Device upload API
```

## Domain Model

### Account

`accounts.Account` là custom user model, đăng nhập bằng `email`.

Thông tin chính:

- `email`, `username`, `first_name`, `last_name`, `phone_number`
- `card_uid`: UID thẻ RFID để map frame upload với tài xế
- `is_admin`, `is_staff`, `is_active`, `is_superadmin`
- `UserImage`: lưu ảnh người dùng, có thể đánh dấu avatar

### Vehicle

`vehicles.Vehicle` lưu thông tin xe:

- `license_plate`
- `model`
- `registration_date`

### Device

`devices.Device` đại diện cho camera/thiết bị gắn trên xe:

- `name`
- `token`: token unique, gửi trong header `X-DEVICE-TOKEN`
- `vehicle`: xe đang gắn với thiết bị
- `is_active`
- `last_seen`
- `latest_frame`, `latest_frame_at`

### Category

`categories.Category` định nghĩa loại vi phạm:

- `name`
- `description`
- `severality_level`
- `is_active`
- `created_at`

### Violation

`violations.Violation` là bản ghi vi phạm:

- `category`
- `reporter`: tài xế bị ghi nhận
- `vehicle`
- `title`, `description`
- `reported_at`
- `image`: ảnh bằng chứng/thumbnail
- `video`: video bằng chứng
- `viewed`
- `status`: `pending`, `confirmed`, `dismissed`, `appealed`

### ViolationAppeal

`violations.ViolationAppeal` cho phép tài xế kháng cáo:

- Mỗi vi phạm chỉ có một appeal.
- `reason`
- `status`: `pending`, `approved`, `rejected`
- `admin_note`
- `created_at`, `reviewed_at`

Khi staff chấp nhận appeal, violation chuyển sang `dismissed`. Khi từ chối, violation chuyển sang `confirmed`.

## Docker

Build:

```bash
docker build -t core-app .
```

Run:

```bash
docker run -p 10000:10000 core-app
```

Truy cập:

```text
http://127.0.0.1:10000/
```

Dockerfile hiện tại:

- Dùng `python:3.10-slim`.
- Cài thư viện hệ thống cho OpenCV/PyTorch.
- Cài dependencies từ `requirements.txt`.
- Chạy `collectstatic`.
- Chạy Gunicorn tại port `10000`.
- Dùng `--workers 1`.

Lưu ý: Dockerfile hiện chưa cài `ffmpeg`. Nếu cần video H.264 web-compatible, nên thêm `ffmpeg` vào apt packages.

## Runtime Files

Các file/thư mục runtime:

- `db.sqlite3`: database local
- `media/live/`: frame mới nhất của device
- `media/violations/`: ảnh bằng chứng
- `media/violations/videos/`: video bằng chứng
- `static/`: collected static/static root

## Production Notes

Cấu hình hiện tại phù hợp demo/prototype hơn production:

- `DEBUG=True`
- `ALLOWED_HOSTS=["*"]`
- `SECRET_KEY` hard-code
- SQLite
- API upload chỉ xác thực bằng `X-DEVICE-TOKEN`
- AI state nằm trong RAM

Hướng nâng cấp:

- Đưa secret và config ra environment variables.
- Dùng PostgreSQL/MySQL thay SQLite.
- Dùng Redis cho realtime AI state nếu scale multi-worker.
- Thêm rate limit và logging cho `/api/upload/`.
- Cài `ffmpeg` trong Docker image.
- Bổ sung test cho upload API, cooldown, appeal workflow và AI inference wrapper.

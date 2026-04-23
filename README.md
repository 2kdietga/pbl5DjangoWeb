# Core - He thong giam sat vi pham tai xe bang AI

## 1. Gioi thieu

Day la du an Django xay dung he thong giam sat hanh vi tai xe tu thiet bi gan tren xe. He thong nhan anh tu camera/thiet bi, xu ly AI de phat hien cac tinh huong mat an toan, luu bien ban vi pham va cung cap giao dien web de tai xe xem lai lich su vi pham cua minh.

Theo hien trang ma nguon, he thong dang tap trung vao 2 nhom vi pham chinh:
- `Drowsiness`: tai xe buon ngu, nham mat qua nguong cho phep.
- `Head Turn`: tai xe quay dau qua muc trong mot khoang thoi gian lien tiep.

## 2. Muc tieu he thong

Muc tieu cua du an la tao mot pipeline khap kin gom:
- thiet bi gui anh ve server theo token xac thuc;
- server xu ly AI theo thoi gian gan real-time;
- vi pham duoc tao tu dong va gan voi tai xe, phuong tien, loai vi pham;
- tai xe dang nhap web de xem danh sach, chi tiet va anh minh chung;
- he thong luu frame moi nhat cua tung thiet bi de phuc vu man hinh theo doi truc tiep.

## 3. Cong nghe su dung

- Backend: `Django 5`, `Django REST Framework`
- Co so du lieu: `SQLite3`
- Xu ly thi giac may tinh: `OpenCV`, `MediaPipe`
- Machine Learning / Deep Learning: `PyTorch`, `torchvision`
- Trien khai: `Gunicorn`, `WhiteNoise`, `Docker`
- Frontend server-rendered: Django Templates, Bootstrap, static assets

## 4. Kien truc tong quan

He thong duoc chia thanh cac app Django chinh:

- `accounts`: quan ly tai khoan dang nhap, thong tin ca nhan, anh dai dien, lien ket `card_uid` cua RFID.
- `vehicles`: quan ly phuong tien thong qua bien so, model, ngay dang ky.
- `devices`: quan ly thiet bi gui anh len server, token thiet bi, frame moi nhat va trang thai theo doi.
- `categories`: dinh nghia nhom vi pham.
- `violations`: luu bien ban vi pham, mo ta, anh/video, thoi diem ghi nhan va trang thai da xem.
- `api`: cung cap API de thiet bi upload anh va kich hoat xu ly AI.
- `ai`: chua logic xu ly AI, dac biet la bai toan phat hien buon ngu va quay dau.
- `core`: cau hinh chung, routing, settings va entrypoint cua du an.

## 5. Mo hinh du lieu chinh

### 5.1. Tai khoan (`accounts.Account`)

Tai khoan nguoi dung duoc custom tu `AbstractBaseUser`, dang nhap bang email. Ngoai cac truong thong tin co ban, model con co:
- `card_uid`: ma the RFID dung de xac dinh tai xe khi thiet bi gui du lieu;
- cac co quan tri nhu `is_admin`, `is_staff`, `is_superadmin`;
- lien ket 1-n voi `UserImage` de luu anh dai dien.

### 5.2. Phuong tien (`vehicles.Vehicle`)

Moi xe duoc quan ly boi:
- bien so xe;
- model xe;
- ngay dang ky.

### 5.3. Thiet bi (`devices.Device`)

Moi thiet bi duoc gan voi mot xe va co:
- `token` duy nhat de xac thuc khi goi API;
- `vehicle` de biet thiet bi dang nam tren xe nao;
- `last_seen` de theo doi lan gui du lieu gan nhat;
- `latest_frame`, `latest_frame_at` de hien thi anh gan nhat tren giao dien live view.

### 5.4. Danh muc vi pham (`categories.Category`)

Dung de phan loai vi pham, gom:
- ten loai vi pham;
- mo ta;
- muc do nghiem trong (`severality_level`);
- trang thai kich hoat.

### 5.5. Vi pham (`violations.Violation`)

La bang trung tam cua he thong, lien ket toi:
- `category`: loai vi pham;
- `reporter`: tai xe bi ghi nhan;
- `vehicle`: phuong tien lien quan.

Thong tin luu kem gom:
- tieu de va mo ta vi pham;
- thoi gian bao cao;
- anh bang chung;
- video bang chung (truong da duoc chuan bi trong model);
- co `viewed` de danh dau da xem tren giao dien.

## 6. Luong xu ly nghiep vu chinh

### 6.1. Luong upload va phat hien vi pham

API chinh cua he thong la `POST /api/upload/`.

Khi thiet bi gui du lieu, server xu ly theo cac buoc:
1. Nhan file anh tu request.
2. Kiem tra header `X-DEVICE-TOKEN` de xac thuc thiet bi.
3. Tim `Device` dang hoat dong va cap nhat `last_seen`.
4. Luu frame moi nhat cua thiet bi de phuc vu man hinh live.
5. Nhan `card_uid` de xac dinh tai xe.
6. Lay xe dang gan voi thiet bi.
7. Goi `ai.drowsiness.engine.process_frame()` de phan tich anh.
8. Neu chua co vi pham, tra ve trang thai AI hien tai.
9. Neu co vi pham, tao hoac tai su dung `Category`, kiem tra cooldown de tranh ghi lap.
10. Tao ban ghi `Violation` va luu anh vi pham vao media.

### 6.2. Luong theo doi truc tiep

App `devices` ho tro 2 route quan trong:
- `GET /devices/<id>/frame/`: tra ve frame moi nhat cua thiet bi.
- `GET /devices/<id>/live/`: hien thi trang theo doi thiet bi; neu goi AJAX thi tra ve JSON trang thai realtime nhu muc nham mat, huong quay dau, diem quay dau, goc yaw.

### 6.3. Luong web cho nguoi dung

Nguoi dung co the:
- dang ky, dang nhap, dang xuat;
- cap nhat profile;
- xem danh sach vi pham cua chinh minh;
- loc theo ngay va loai vi pham;
- xem chi tiet tung bien ban va danh dau da xem.

## 7. Logic AI dang duoc ap dung

Phan AI hien tai trong ma nguon tap trung vao bai toan theo doi trang thai mat va huong dau.

### 7.1. Phat hien buon ngu

Module `ai/drowsiness/engine.py` su dung `MediaPipe Face Landmarker` de trich xuat moc khuon mat va tinh `EAR` (Eye Aspect Ratio).

Co che xu ly:
- he thong can mot pha `calibration` ban dau de tinh `baseline_ear` theo tung thiet bi/doi tuong;
- EAR hien tai duoc lam muot bang ham `smooth()`;
- neu EAR thap hon nguong ti le theo baseline hoac thap hon nguong tuyet doi, he thong coi nhu mat dang nham;
- neu so frame nham mat lien tiep vuot nguong cau hinh, he thong tao vi pham `Drowsiness`.

### 7.2. Phat hien quay dau

Tu ma tran bien doi khuon mat cua MediaPipe, he thong tinh `yaw` cua dau:
- neu `yaw` vuot nguong trai/phai, diem `head_turn_score` tang dan;
- neu quay ve trung tam, diem nay giam theo `decay`;
- khi diem vuot nguong cau hinh va chua tung bao vi pham trong dot hien tai, he thong tao vi pham `Head Turn`.

### 7.3. Trang thai theo thiet bi

Trang thai AI duoc luu tam trong bo nho qua `STATE_STORE`, key theo `device token`. Moi thiet bi co mot `EyeState` rieng de nho:
- baseline EAR;
- chuoi frame nham mat;
- diem quay dau;
- huong dau;
- goc yaw gan nhat.

Cach lam nay phu hop cho demo va prototype realtime, nhung ve kien truc van la trang thai trong RAM, chua phai co che phan tan hoac persistent state.

## 8. Cac cau hinh AI quan trong

Trong `core/settings.py`, he thong da khai bao nhieu tham so nghiep vu:
- `DROWSINESS_FPS`: toc do frame gui len;
- `DROWSINESS_EYE_CLOSED_RATIO`: nguong nham mat theo baseline ca nhan;
- `DROWSINESS_EYE_CLOSED_ABS`: nguong tuyet doi fallback;
- `DROWSINESS_EYE_CLOSED_FRAMES`: so frame nham mat lien tiep de ket luan vi pham;
- `DROWSINESS_HEAD_YAW_THRESHOLD`: nguong goc quay dau;
- `DROWSINESS_HEAD_TURN_VIOLATION_FRAMES`: so frame/diem de ket luan quay dau nguy hiem;
- `DROWSINESS_VIOLATION_COOLDOWN_SECONDS` va `HEAD_TURN_VIOLATION_COOLDOWN_SECONDS`: thoi gian chong lap vi pham.

Day la cac tham so quan trong de hieu rang he thong khong chi phan loai anh don le, ma con theo doi theo chuoi thoi gian ngan.

## 9. Giao dien va routing

Cac route muc tieu dang duoc cau hinh nhu sau:
- `/`: trang dang nhap mac dinh.
- `/accounts/login/`, `/accounts/register/`, `/accounts/logout/`, `/accounts/profile/`
- `/violations/`: danh sach vi pham.
- `/devices/<id>/live/`: giao dien xem realtime.
- `/api/upload/`: API nhan frame tu thiet bi.
- `/admin/`: trang quan tri Django.

Template dang co gom `login`, `register`, `profile`, `violation_list`, `violation_detail`, `live_view`, `base`.

## 10. Trien khai va van hanh

Du an co san `Dockerfile` de dong goi va chay bang `gunicorn`. Cac thu vien he thong duoc cai them chu yeu phuc vu OpenCV/MediaPipe nhu `libglib2.0-0`, `libgl1`, `libgomp1`, `libgles2`, `libegl1`.

Cau hinh hien tai:
- cong khai dich vu o cong `10000`;
- dung `WhiteNoise` de phuc vu static files;
- `collectstatic` duoc chay ngay trong qua trinh build image.

## 11. Huong dan chay du an

### 11.1. Chay local

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Truy cap:
- web app: `http://127.0.0.1:8000/`
- admin: `http://127.0.0.1:8000/admin/`

### 11.2. Chay bang Docker

```bash
docker build -t core-app .
docker run -p 10000:10000 core-app
```

## 12. Danh gia hien trang du an

### Diem manh

- Kien truc Django tach app ro rang theo domain.
- Da co luong nghiep vu tu thiet bi den web app kha day du.
- Da ket hop thong tin tai xe, phuong tien, thiet bi va vi pham trong cung mot he thong.
- Co san co che cooldown tranh spam vi pham.
- Co live view de quan sat frame va trang thai realtime.

### Han che

- Co so du lieu dang dung `SQLite`, phu hop cho hoc tap/demo hon la tai lon.
- `STATE_STORE` luu trong RAM nen se mat khi restart va khong phu hop khi scale nhieu worker.
- Bao mat dang o muc demo: `DEBUG=True`, `ALLOWED_HOSTS=['*']`.
- Chua thay bo test nghiep vu duoc xay dung day du.
- Mot so file AI cu van con duoc giu lai o dang comment, cho thay he thong dang trong qua trinh thu nghiem/mo rong.

## 13. Ket luan

`core` la mot du an web AI theo huong ung dung thuc te trong giam sat an toan tai xe. Gia tri chinh cua he thong nam o cho no ket noi duoc 4 lop thanh mot quy trinh thong nhat: thiet bi nhung, xu ly AI, backend quan ly va giao dien tra cuu vi pham. Neu tiep tuc phat trien, huong mo rong hop ly nhat la nang cap ha tang luu state realtime, bo sung test, cai thien bao mat va toi uu trien khai production.

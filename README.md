# 🖼️ ChichBong Imagen4 - Tạo ảnh AI từ Terminal

Script Python **standalone** thay thế hoàn toàn giao diện GUI của app ChichBong Imagen4.  
Cho phép tạo ảnh AI (Google Imagen 4) trực tiếp từ Terminal/Command Line.

---

## 📋 Mục lục

- [Yêu cầu](#-yêu-cầu)
- [Cài đặt nhanh](#-cài-đặt-nhanh)
- [Cách sử dụng](#-cách-sử-dụng)
- [Hướng dẫn chi tiết: Cách reverse-engineer app ChichBong](#-hướng-dẫn-chi-tiết-cách-reverse-engineer-app-chichbong)
  - [Bước 1: Tải và cài app ChichBong](#bước-1-tải-và-cài-app-chichbong)
  - [Bước 2: Bắt network traffic bằng Proxyman](#bước-2-bắt-network-traffic-bằng-proxyman)
  - [Bước 3: Trích xuất mã nguồn từ app](#bước-3-trích-xuất-mã-nguồn-từ-app)
  - [Bước 4: Giải mã bytecode Python](#bước-4-giải-mã-bytecode-python)
  - [Bước 5: Xây dựng API Client](#bước-5-xây-dựng-api-client)
- [Kiến trúc hệ thống](#-kiến-trúc-hệ-thống)
- [Chi tiết kỹ thuật](#-chi-tiết-kỹ-thuật)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)

---

## 🔧 Yêu cầu

- Python 3.9+
- Thư viện: `requests`, `websockets`
- License key hợp lệ từ app ChichBong (bạn cần mua license)

## 🚀 Cài đặt nhanh

```bash
# 1. Clone repo
git clone https://github.com/xuanminhcvp/chichbongtaoanh.git
cd chichbongtaoanh

# 2. Cài thư viện
pip3 install requests websockets

# 3. Sửa thông tin license trong file chichbong_api_client.py
# Thay LICENSE_KEY, HARDWARE_ID, CPU_ID, MAINBOARD_UUID bằng thông tin của bạn
# (Xem hướng dẫn bên dưới để lấy thông tin này)

# 4. Chạy thử
python3 chichbong_api_client.py --info
```

## 📖 Cách sử dụng

### Xem thông tin tài khoản
```bash
python3 chichbong_api_client.py --info
```

### Tạo 1 ảnh
```bash
python3 chichbong_api_client.py "A cute cat sitting on a table"
```

### Tạo nhiều ảnh (phân tách bằng |)
```bash
python3 chichbong_api_client.py "prompt 1 | prompt 2 | prompt 3"
```

### Tạo ảnh từ file (mỗi dòng 1 prompt)
```bash
python3 chichbong_api_client.py --file prompts.txt
```

### Chọn tỉ lệ ảnh
```bash
# Vuông (mặc định)
python3 chichbong_api_client.py "prompt" --ratio square

# Ngang (16:9)
python3 chichbong_api_client.py "prompt" --ratio landscape

# Dọc (9:16)
python3 chichbong_api_client.py "prompt" --ratio portrait
```

### Chỉ định thư mục output
```bash
python3 chichbong_api_client.py "prompt" --output ~/Pictures/ai_images
```

### Chỉ định seed (để tạo lại ảnh giống nhau)
```bash
python3 chichbong_api_client.py "prompt" --seed 12345
```

### Dùng model cũ (IMAGEN 3.5)
```bash
python3 chichbong_api_client.py "prompt" --legacy
```

**Ảnh mặc định được lưu tại:** `~/Desktop/chichbong_output/`

---

## 🔬 Hướng dẫn chi tiết: Cách reverse-engineer app ChichBong

> Đây là hướng dẫn từng bước cách tôi đã phân tích app ChichBong để xây dựng script tự động hóa.
> Bất kỳ ai cũng có thể làm theo các bước này.

### Bước 1: Tải và cài app ChichBong

1. **Tải app** từ trang chủ ChichBong (file `.dmg` cho macOS)
2. **Mount file DMG** — double-click file `.dmg` → app sẽ xuất hiện trong `/Volumes/`
3. **Mở app** lần đầu tiên, nhập email để kích hoạt license
4. **Ghi nhớ**: Sau khi kích hoạt, app sẽ lưu license key vào máy. License key này gắn với hardware ID của máy bạn.

### Bước 2: Bắt network traffic bằng Proxyman

**Mục đích:** Xem app gửi/nhận request gì khi hoạt động.

1. **Cài Proxyman** (miễn phí cho macOS):
   ```bash
   brew install --cask proxyman
   ```

2. **Cấu hình Proxyman**:
   - Mở Proxyman → Certificate → Install Certificate on this Mac
   - Vào **Certificate** → **Install Certificate on This Mac** → nhấn **Install & Trust**
   - Proxyman sẽ cài CA certificate để giải mã HTTPS

3. **Chạy app ChichBong qua proxy**:
   ```bash
   # Set biến môi trường SSL
   export SSL_CERT_FILE=~/.proxyman/proxyman-ca.pem
   export REQUESTS_CA_BUNDLE=~/.proxyman/proxyman-ca.pem
   
   # Chạy app
   open /Volumes/chichbong_image_1.3.5/chichbong_image_1.3.5.app
   ```

4. **Quan sát traffic trong Proxyman**:
   - Bạn sẽ thấy các request tới `11labs.net` (server xác thực license)
   - Ghi lại:
     - `GET /api/account/info?license_key=XXX&app=imagen4` → Lấy thông tin tài khoản
     - `POST /api/license/activate.php` → Chứa `hardware_id`, `cpu_id`, `mainboard_uuid`
     - `POST /api/license/verify_imagen4.php` → Xác thực license
   - **Lưu lại** tất cả các giá trị: `license_key`, `hardware_id`, `cpu_id`, `mainboard_uuid`

> **⚠️ Lưu ý:** WebSocket traffic (`wss://`) không bắt được qua Proxyman thông thường. Đó là lý do cần bước 3 và 4 bên dưới.

### Bước 3: Trích xuất mã nguồn từ app

App ChichBong được đóng gói bằng **PyInstaller** (Python → executable). Ta có thể "mổ" nó ra.

1. **Tải PyInstXtractor** — công cụ giải nén PyInstaller:
   ```bash
   # Tải script
   curl -O https://raw.githubusercontent.com/extremecoders-re/pyinstxtractor/master/pyinstxtractor.py
   ```

2. **Tìm file executable bên trong app**:
   ```bash
   ls /Volumes/chichbong_image_1.3.5/chichbong_image_1.3.5.app/Contents/MacOS/
   # Sẽ thấy file executable chính (ví dụ: main_imagen hoặc tương tự)
   ```

3. **Giải nén**:
   ```bash
   python3 pyinstxtractor.py /Volumes/chichbong_image_1.3.5/chichbong_image_1.3.5.app/Contents/MacOS/main_imagen
   ```
   
   → Tạo ra thư mục `main_imagen_extracted/` chứa tất cả file `.pyc` (Python bytecode)

4. **Copy các file quan trọng ra**:
   ```bash
   mkdir -p ~/Desktop/chichbong_extract/pyc_files/
   cp main_imagen_extracted/*.pyc ~/Desktop/chichbong_extract/pyc_files/
   ```

### Bước 4: Giải mã bytecode Python

File `.pyc` là bytecode đã biên dịch. Ta cần đọc nó để hiểu logic app.

#### Cách 1: Dùng decompiler (nếu may mắn)

```bash
pip3 install uncompyle6 decompyle3
uncompyle6 websocket_client_simple.pyc > websocket_client_simple.py
```

> ⚠️ Các decompiler thường **không hỗ trợ Python 3.11+**. Nếu fail, dùng Cách 2.

#### Cách 2: Dùng `marshal` + `dis` module (luôn hoạt động)

Đây là cách tôi đã dùng. Hoạt động với mọi phiên bản Python.

**a) Trích xuất string constants (tên event, URL, tên field):**

```python
import marshal, types

with open("websocket_client_simple.pyc", "rb") as f:
    data = f.read()
code = marshal.loads(data[16:])  # Bỏ 16 byte header

# Lấy tất cả string constants
def get_strings(code_obj):
    found = []
    for c in code_obj.co_consts:
        if isinstance(c, str) and len(c) > 1:
            found.append(c)
        if isinstance(c, types.CodeType):
            found.extend(get_strings(c))
    return found

for s in sorted(set(get_strings(code))):
    print(s)
```

→ Từ đây ta thấy: `"register"`, `"submit_prompt"`, `"prompt_result"`, `"license_key"`, `"image_base64"`, v.v.

**b) Liệt kê tất cả hàm và tham số:**

```python
def find_functions(code_obj, prefix=''):
    for c in code_obj.co_consts:
        if isinstance(c, types.CodeType):
            params = list(c.co_varnames[:c.co_argcount])
            print(f"{prefix}{c.co_name}({', '.join(params)})")
            find_functions(c, prefix + "  ")

find_functions(code)
```

**c) Disassemble từng hàm (cần Python cùng version với app):**

```bash
# App dùng Python 3.11, cần python3.11 để dis chính xác
python3.11 -c "
import marshal, types, dis, io, sys

with open('websocket_client_simple.pyc', 'rb') as f:
    data = f.read()
code = marshal.loads(data[16:])

# Tìm hàm cần phân tích
def find_func(code_obj, name):
    for c in code_obj.co_consts:
        if isinstance(c, types.CodeType):
            if c.co_name == name:
                return c
            r = find_func(c, name)
            if r: return r

func = find_func(code, '_async_generate_images')
dis.dis(func)
"
```

→ Đọc từng instruction bytecode để hiểu **chính xác** cấu trúc JSON được gửi đi.

**d) Ví dụ phân tích bytecode register message:**

```
LOAD_CONST  'register'           ← giá trị cho key 'event'
LOAD_CONST  'license_key'        ← key trong dict data
LOAD_FAST   self
LOAD_ATTR   license_key          ← giá trị = self.license_key  
BUILD_MAP   1                    ← tạo dict {'license_key': self.license_key}
LOAD_CONST  ('event', 'data')    ← tên các keys
BUILD_CONST_KEY_MAP  2           ← tạo dict {'event': 'register', 'data': {...}}
```

→ Kết luận: `register_message = {"event": "register", "data": {"license_key": "..."}}`

### Bước 5: Xây dựng API Client

Sau khi đã biết:
- **REST API endpoints** (từ Proxyman): `11labs.net/api/license/verify_imagen4.php`, v.v.
- **WebSocket URL** (từ bytecode): `wss://api.chichbong.me/`
- **Message format** (từ bytecode disassembly): register, submit_prompt_batch, prompt_result

Ta ghép lại thành script `chichbong_api_client.py`:

```
Flow hoàn chỉnh:
1. POST /api/license/verify_imagen4.php → Xác thực license
2. GET /api/account/info → Xem thông tin (tuỳ chọn)
3. WebSocket connect → wss://api.chichbong.me/
4. Send: {"event": "register", "data": {"license_key": "..."}}
5. Recv: {"event": "registered", "data": {"client_id": "..."}}
6. Send: {"event": "submit_prompt_batch", "data": [...]}
7. Recv: {"event": "prompt_queued", ...} (nhiều lần)
8. Recv: {"event": "prompt_result", "data": {"status": "success", "image_base64": "..."}}
9. Decode base64 → Lưu file JPG
```

---

## 🏗️ Kiến trúc hệ thống

```
┌──────────────┐     REST API      ┌──────────────┐
│   Script     │ ───────────────► │  11labs.net   │  (License server)
│   Python     │                   └──────────────┘
│              │     WebSocket     ┌──────────────┐     ┌──────────────┐
│              │ ───────────────► │ api.chichbong │ ──► │ Google API   │
└──────────────┘                   │    .me       │     │ (Imagen 4)   │
                                   └──────────────┘     └──────────────┘
```

- **11labs.net**: Server xác thực license, quản lý tài khoản
- **api.chichbong.me**: WebSocket proxy server, nhận prompt → gọi Google Imagen API → trả ảnh base64
- **Google Imagen API**: AI tạo ảnh thực tế (phía sau, script không gọi trực tiếp)

---

## 📐 Chi tiết kỹ thuật

### REST API Endpoints (11labs.net)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/license/verify_imagen4.php` | Xác thực license |
| GET | `/api/account/info?license_key=...&app=imagen4` | Thông tin tài khoản |
| POST | `/api/resource/report-imagen-counter.php` | Báo cáo usage |

### WebSocket Events

| Direction | Event | Mô tả |
|-----------|-------|-------|
| → Send | `register` | Đăng ký client với license_key |
| ← Recv | `registered` | Xác nhận đăng ký, trả client_id |
| → Send | `submit_prompt_batch` | Gửi batch prompts |
| ← Recv | `prompt_queued` | Xác nhận đã nhận, trả queue_position |
| ← Recv | `task_status` | Cập nhật tiến trình (đang tạo ảnh...) |
| ← Recv | `prompt_result` | Kết quả: status + image_base64 |
| ← Recv | `stats` | Thống kê server (queue_size) |

### Cấu trúc prompt_data (7 fields chính)

```json
{
  "prompt_id": "pc_{uuid4}_{index}",
  "prompt": "A cute cat...",
  "aspect_ratio": "IMAGE_ASPECT_RATIO_SQUARE",
  "seed": 12345,
  "index": 0,
  "original_prompt": "A cute cat...",
  "attachment": null
}
```

### WebSocket connection params

| Param | Giá trị |
|-------|---------|
| `ping_interval` | 60s (90s nếu >50 prompts) |
| `ping_timeout` | 30s (45s nếu >50 prompts) |
| `open_timeout` | 30s |
| `max_size` | 20971520 (20MB) |
| `compression` | None |

---

## 📁 Cấu trúc thư mục

```
chichbongtaoanh/
├── chichbong_api_client.py          # ✅ Script chính (chỉ cần file này để chạy)
├── README.md                        # 📖 File hướng dẫn này
├── main_imagen.py                   # 📖 Mã nguồn giải mã từ app (tham khảo)
├── services/
│   └── api_imagen_service.py        # 📖 API service giải mã (tham khảo)
├── pyc_files/                       # 📖 Bytecode gốc từ app (tham khảo)
│   ├── websocket_client_simple.pyc
│   ├── websocket_config.pyc
│   ├── token_client.pyc
│   ├── main_window_imagen.pyc
│   ├── imagen_api.pyc
│   └── ...
└── decompiled/                      # 📖 Kết quả disassembly (tham khảo)
    ├── _async_generate_images_dis.txt
    ├── _producer_task_dis.txt
    ├── _message_dispatcher_task_dis.txt
    └── get_tokens_dis.txt
```

---

## ⚠️ Lưu ý quan trọng

1. **Bạn cần có license hợp lệ** — Script sử dụng license key mà bạn đã mua từ ChichBong.
2. **Thay đổi thông tin cá nhân** — Trước khi chạy, phải sửa `LICENSE_KEY`, `HARDWARE_ID`, `CPU_ID`, `MAINBOARD_UUID` trong script thành thông tin máy của bạn.
3. **Lấy thông tin máy** — Dùng Proxyman bắt request `POST /api/license/activate.php` khi mở app lần đầu, request đó chứa tất cả thông tin hardware của bạn.
4. **Giới hạn** — Tuân thủ giới hạn tạo ảnh của tài khoản (ví dụ: 999 ảnh/ngày cho VIP).

---

## 🛠️ Công cụ đã sử dụng

| Công cụ | Mục đích |
|---------|----------|
| [Proxyman](https://proxyman.io/) | Bắt HTTP/HTTPS traffic |
| [PyInstXtractor](https://github.com/extremecoders-re/pyinstxtractor) | Giải nén PyInstaller executable |
| Python `marshal` module | Đọc bytecode .pyc |
| Python `dis` module | Disassemble bytecode thành instructions |
| Python 3.11 | Cần đúng version để disassemble chính xác |

---

*Được tạo bằng cách reverse-engineer app ChichBong Imagen4 v1.3.5*

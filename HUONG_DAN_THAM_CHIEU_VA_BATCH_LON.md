# Hướng Dẫn Tham Chiếu Nhân Vật Và Tạo Nhiều Ảnh Trong 1 Batch

Tài liệu này hướng dẫn bạn:

1. Cách dùng ảnh tham chiếu nhân vật (character reference).
2. Cách tạo số lượng ảnh lớn (ví dụ 150 ảnh) trong cùng một lần chạy.
3. Request gửi đi gì, response nhận về gì, để bạn dễ debug.

---

## 1) Cách hệ thống hoạt động (dễ hiểu)

Script hiện tại chạy theo flow:

1. Verify license.
2. Lấy thông tin tài khoản.
3. Kết nối WebSocket.
4. Gửi prompt (có hoặc không có ảnh tham chiếu).
5. Nhận từng kết quả ảnh trả về.

Nếu bạn có tham chiếu nhân vật:

- Script sẽ đọc ảnh từ máy bạn.
- Encode ảnh thành base64.
- Gắn vào payload `attachments`.
- Mỗi prompt sẽ có `attachment` (bitset) và `attachment_order` để chỉ định dùng ảnh nào.

---

## 2) Chuẩn bị ảnh tham chiếu

### 2.1 Quy tắc số lượng

- Tối đa 10 ảnh tham chiếu cho mỗi lần chạy.

### 2.2 Quy tắc đặt tên file (rất quan trọng)

Script tự map nhân vật theo **tên file ảnh**:

- Bỏ đuôi file (`.jpg`, `.jpeg`, `.png`...).
- Đổi `_` và `-` thành khoảng trắng.
- So khớp với text trong prompt.

Ví dụ:

- File: `CHAR02_BERNICE_CARTER_PRESENT.jpeg`
- Prompt có: `CHAR02_BERNICE_CARTER_PRESENT`
- Script sẽ tự hiểu prompt này cần ảnh slot tương ứng.

Mẹo:

- Nên đặt tên file gần giống tên nhân vật bạn viết trong prompt.

---

## 3) Cách chạy với tham chiếu nhân vật

## 3.1 Một prompt, nhiều ảnh tham chiếu

```bash
python3 chichbong_api_client.py "CHAR02_BERNICE_CARTER_PRESENT đứng cạnh CHAR05_HARRISON_ASHFORD_III_WEAKENED" \
  --ref-image ~/Downloads/CHAR02_BERNICE_CARTER_PRESENT.jpeg \
  --ref-image ~/Downloads/CHAR05_HARRISON_ASHFORD_III_WEAKENED.jpeg
```

Khi không truyền `--ref-order`:

- Script tự map tên nhân vật trong prompt sang ảnh tham chiếu.
- Tự sinh `attachment` và `attachment_order` cho từng prompt.

## 3.2 Ép thứ tự ảnh tham chiếu (nếu cần)

```bash
python3 chichbong_api_client.py "prompt của bạn" \
  --ref-image ~/Downloads/A.jpeg \
  --ref-image ~/Downloads/B.jpeg \
  --ref-order 1,2
```

Lưu ý:

- `--ref-order` dùng số slot 1..10.

---

## 4) Tạo số lượng lớn ảnh trong 1 batch (ví dụ 150 ảnh)

## 4.1 Chuẩn bị file prompt

Tạo file `prompts_150.txt`, mỗi dòng là 1 prompt:

```txt
Prompt dòng 1...
Prompt dòng 2...
...
Prompt dòng 150...
```

## 4.2 Chạy batch lớn không tham chiếu

```bash
python3 chichbong_api_client.py --file prompts_150.txt
```

## 4.3 Chạy batch lớn có tham chiếu nhân vật

```bash
python3 chichbong_api_client.py --file prompts_150.txt \
  --ref-image ~/Downloads/CHAR02_BERNICE_CARTER_PRESENT.jpeg \
  --ref-image ~/Downloads/CHAR05_HARRISON_ASHFORD_III_WEAKENED.jpeg
```

---

## 5) Request gửi đi gì? Response nhận về gì?

## 5.1 Không dùng tham chiếu ảnh

Request chính:

- Event: `submit_prompt_batch`
- Data: danh sách prompt (prompt_id, prompt, aspect_ratio, seed, ...)

Response chính:

- Event: `prompt_result`
- Data: `status`, `image_base64`, `prompt_id`, ...

## 5.2 Có dùng tham chiếu ảnh

### Trường hợp nhiều prompt

Request chính:

- Event: `submit_prompt_with_attachments`
- Data:
  - `prompts`: danh sách prompt
  - `attachments`:
    - `images`: mỗi ảnh có `index`, `base64`, `mimeType`
    - `aspectRatio`

### Trường hợp 1 prompt

Request chính:

- Event: `submit_prompt`
- Data:
  - thông tin prompt
  - `attachment` (bitset)
  - `attachment_order`
  - `attachments` (images + aspectRatio)

Response vẫn là:

- Event: `prompt_result` cho kết quả ảnh cuối.

---

## 6) Ý nghĩa log quan trọng khi debug

- `[REF-MAP] line=... matched_slots=[...] bitset=...`
  - Script đã map prompt -> ảnh tham chiếu nào.

- `Upload X ảnh tham chiếu...`
  - Server đã nhận block attachments và đang upload ảnh tham chiếu.

- `Saved [a/b]: prompt_XXX.jpg`
  - Đã nhận `image_base64` thành công và lưu file.

- `Timeout, continuing...`
  - Đang chờ lâu, chưa chắc là lỗi; server có thể vẫn xử lý.

---

## 7) Lưu ý khi chạy batch rất lớn

1. Timeout chờ kết quả trong script hiện là 300 giây.
2. Với batch lớn (100-150 ảnh), 300 giây có thể không đủ.
3. Nếu thấy timeout sớm, cần tăng thời gian chờ trong code.
4. Khi server bận, bạn có thể thấy log như `Captcha worker bận, đang chờ...`; đây là trạng thái chờ xử lý, không phải lỗi cú pháp request.

---

## 8) Checklist chạy ổn định cho 150 ảnh

1. Prompt file đúng 150 dòng, không dòng rỗng dư.
2. Đường dẫn ảnh tham chiếu đúng, có đuôi file thật (`.jpeg`, `.jpg`, ...).
3. Tên file ảnh khớp tên nhân vật trong prompt (để auto-map chính xác).
4. Theo dõi log `[REF-MAP]` để kiểm tra map đúng.
5. Theo dõi thư mục output: `~/Desktop/chichbong_output/`.

---

## 9) Ví dụ hoàn chỉnh

```bash
python3 chichbong_api_client.py --file prompts_150.txt \
  --ref-image ~/Downloads/CHAR02_BERNICE_CARTER_PRESENT.jpeg \
  --ref-image ~/Downloads/CHAR05_HARRISON_ASHFORD_III_WEAKENED.jpeg \
  --ratio square
```

Kỳ vọng:

- Request có attachments + mapping nhân vật.
- Response trả dần từng `prompt_result`.
- Ảnh lưu lần lượt thành `prompt_001.jpg`, `prompt_002.jpg`, ...


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChichBong Imagen4 API Client - Giả lập app desktop qua API
Đã xác minh chuẩn 100% từ bytecode gốc (Python 3.11 disassembly)

Flow:
  1. verify license (POST /license/verify_imagen4.php)
  2. lấy token (POST /checker/get-imagen4-token.php)
  3. kết nối WebSocket (wss://v2.chichbong.me)
  4. register: {"event":"register","data":{"license_key":"..."}}
  5. batch: {"event":"submit_prompt_batch","data":[...]}  (không có attachment)
  6. hoặc single: {"event":"submit_prompt","data":{7 fields + model fields + "attachments"}}
  7. nhận: {"event":"prompt_result","data":{"status":"success","image_base64":"..."}}
"""

import asyncio
import json
import os
import sys
import time
import base64
import logging
import uuid
import argparse
import mimetypes
import re
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Chưa cài requests. Chạy: pip3 install --break-system-packages requests")
    sys.exit(1)
try:
    import websockets
except ImportError:
    print("❌ Chưa cài websockets. Chạy: pip3 install --break-system-packages websockets")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# =================================================================
# CẤU HÌNH - Lấy từ Proxyman + giải mã bytecode app
# =================================================================
LICENSE_KEY = "ELV-2de351a2-1a99a72d-f59bfe30"
HARDWARE_ID = "f12857101ba06b3e76d1317dc5d2743077968acf84c51564894e27e918377239"
CPU_ID = "df6cf5d1556d7cb1260ad2432d01f31d"
MAINBOARD_UUID = "7D1E5B40-1A38-5D04-A1FC-300E36AA6D01"

API_BASE_URL = "https://11labs.net/api"
WEBSOCKET_URL = "wss://api.chichbong.me/"  # SSL cert valid cho domain này
BRAND = "imagen4"
VERSION = "1.3.5"
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "chichbong_output")


def _guess_mime_type(file_path):
    """
    Đoán mime type từ đuôi file.
    Server app gốc gửi field `mimeType` cho từng ảnh attachment.
    """
    mime, _ = mimetypes.guess_type(file_path)
    return mime or "image/jpeg"


def _build_attachments_payload(ref_image_paths, attachments_aspect_ratio):
    """
    Đọc ảnh tham chiếu từ local file -> encode base64 -> tạo payload theo format bytecode:
      {
        "images": [{"index": 1, "base64": "...", "mimeType": "image/jpeg"}, ...],
        "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
      }
    """
    images = []
    for idx, image_path in enumerate(ref_image_paths):
        with open(image_path, "rb") as f:
            b64_content = base64.b64encode(f.read()).decode("utf-8")
        images.append({
            # App gốc gửi index theo slot 1..10 (không phải 0-based).
            "index": idx + 1,
            "base64": b64_content,
            # main_window_imagen.pyc encode ảnh về JPG và gửi mimeType cố định image/jpeg.
            "mimeType": "image/jpeg",
        })
    return {"images": images, "aspectRatio": attachments_aspect_ratio}


def _compute_attachment_bitset(image_indices):
    """
    App gốc dùng field `attachment` dạng int (bitset).
    Ví dụ:
      - slot 1 -> bitset = 1
      - slot 2 -> bitset = 2
      - dùng cả slot 1 và 2 -> bitset = 3
    """
    bitset = 0
    for idx in image_indices:
        slot = int(idx)
        # Theo bytecode app gốc: bitset |= (1 << (slot_index - 1)), slot_index thuộc [1..10].
        if 1 <= slot <= 10:
            bitset |= (1 << (slot - 1))
    return bitset


def _normalize_name_text(text):
    """
    Chuẩn hóa text để so khớp tên nhân vật:
    - lowercase
    - đổi _ và - thành khoảng trắng
    - bỏ ký tự đặc biệt
    - gộp nhiều khoảng trắng thành 1
    """
    s = str(text or "").lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_reference_name_entries(ref_image_paths):
    """
    Tạo map từ tên file ảnh tham chiếu -> slot index 1..10.
    Mỗi ảnh có thể có nhiều alias để tăng khả năng match prompt.
    """
    entries = []
    for idx, image_path in enumerate(ref_image_paths):
        slot_index = idx + 1
        stem = Path(image_path).stem
        norm = _normalize_name_text(stem)
        aliases = set()
        if norm:
            aliases.add(norm)
            # Bỏ các cụm số dài ở cuối tên file (ví dụ timestamp) để dễ match prompt.
            norm_no_tail_digits = re.sub(r"(?:\s+\d{6,})+$", "", norm).strip()
            if norm_no_tail_digits:
                aliases.add(norm_no_tail_digits)

        entries.append({
            "slot_index": slot_index,
            "image_path": image_path,
            "aliases": sorted(a for a in aliases if a),
        })
    return entries


def _match_prompt_to_slots(prompt_text, ref_name_entries):
    """
    Trả về danh sách slot index xuất hiện trong prompt theo tên nhân vật.
    """
    prompt_norm = _normalize_name_text(prompt_text)
    if not prompt_norm:
        return []

    matched_slots = []
    for entry in ref_name_entries:
        for alias in entry["aliases"]:
            # So khớp theo biên từ để giảm match sai.
            pattern = r"(^|\s)" + re.escape(alias) + r"(\s|$)"
            if re.search(pattern, prompt_norm):
                matched_slots.append(int(entry["slot_index"]))
                break
    return matched_slots

# =================================================================
# API CLIENT (đã verify chuẩn 100% qua Proxyman + source code)
# =================================================================
class ChichBongAPIClient:
    def __init__(self, license_key):
        self.license_key = license_key
        self.base_url = API_BASE_URL
        self.timeout = 15
        self.headers = {"User-Agent": "Imagen4-Client/1.0", "Content-Type": "application/json"}

    def verify_license(self):
        url = f"{self.base_url}/license/verify_imagen4.php"
        payload = {"license_key": self.license_key, "hardware_id": HARDWARE_ID,
                    "cpu_id": CPU_ID, "mainboard_uuid": MAINBOARD_UUID,
                    "brand": BRAND, "current_version": VERSION}
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
            result = r.json()
            if result.get("success"):
                logger.info("✅ License hợp lệ!")
            else:
                logger.error(f"❌ License không hợp lệ: {result.get('message')}")
            return result
        except Exception as e:
            logger.error(f"💥 Lỗi verify: {e}")
            return {"success": False, "error": str(e)}

    def get_account_info(self):
        url = f"{self.base_url}/account/info"
        params = {"license_key": self.license_key, "app": BRAND}
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            result = r.json()
            info = result.get("data", {}).get("account_info", {})
            logger.info(f"📧 Email: {info.get('email', '-')}")
            logger.info(f"🖼️ Tổng ảnh: {info.get('imagen_count', 0)}")
            logger.info(f"📅 Hôm nay: {info.get('imagen_count_today', 0)}/{info.get('imagen_per_day', 50)}")
            return result
        except Exception as e:
            logger.error(f"💥 Lỗi: {e}")
            return {"success": False, "error": str(e)}

    def get_tokens(self, limit=5):
        # Bytecode xác nhận: session.get(url, params={"license_key": ...}, timeout=30)
        # PHẢI dùng GET, không phải POST!
        url = f"{self.base_url}/checker/get-imagen4-token.php"
        params = {"license_key": self.license_key}
        try:
            r = requests.get(url, params=params, headers=self.headers, timeout=30)
            if r.status_code == 200:
                result = r.json()
                if result.get("success"):
                    tokens = result.get("tokens", [])
                    logger.info(f"🔑 Lấy được {len(tokens)} tokens từ server")
                    return tokens
                else:
                    logger.error(f"❌ Failed to get tokens: {result.get('message', 'Unknown error')}")
                    return []
            else:
                logger.error(f"❌ HTTP error {r.status_code}: {r.text}")
                return []
        except Exception as e:
            logger.error(f"💥 Lỗi khi lấy tokens: {e}")
            return []

    def report_usage(self, count):
        url = f"{self.base_url}/resource/report-imagen-counter.php"
        try:
            r = requests.post(url, json={"license_key": self.license_key, "successful_count": count},
                              headers=self.headers, timeout=self.timeout)
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

# =================================================================
# WEBSOCKET CLIENT - Chuẩn 100% theo SimpleWebSocketImageGenerator
# Đã disassemble bằng Python 3.11 dis module và đọc từng instruction
# =================================================================
class ChichBongWSClient:
    """Chuẩn theo SimpleWebSocketImageGenerator trong websocket_client_simple.pyc"""
    def __init__(self, token, license_key, output_dir):
        self.token = token
        self.license_key = license_key
        self.output_dir = output_dir
        self.registered = False
        self.client_id = None
        os.makedirs(self.output_dir, exist_ok=True)

    async def connect_and_generate(self, prompts, seed=None,
                                     aspect_ratio="IMAGE_ASPECT_RATIO_SQUARE",
                                     use_legacy_model=False, upscale_mode=False,
                                     image_model_name=None, attachments_payload=None,
                                     attachments_by_index=None, attachments_order_by_index=None):
        saved_files = []
        try:
            # --- SSL context: bytecode dòng 1268-1534 ---
            # Dùng certifi CA bundle nếu có, fallback system default
            import ssl
            ssl_ctx = None
            try:
                import certifi
                cafile = certifi.where()
                ssl_ctx = ssl.create_default_context(cafile=cafile)
                logger.info(f"🔐 Using certifi CA bundle: {cafile}")
            except Exception:
                ssl_ctx = ssl.create_default_context()

            # --- WebSocket connect: bytecode dòng 986-1076 + 1672-1734 ---
            # ping_interval: 90 nếu >50 prompts, else 60
            # ping_timeout: 45 nếu >50 prompts, else 30
            # open_timeout: 30
            # max_size: 20971520 (20MB)
            # compression: None
            ping_interval = 90 if len(prompts) > 50 else 60
            ping_timeout = 45 if len(prompts) > 50 else 30

            logger.info(f"🔗 Connecting to: {WEBSOCKET_URL}")
            logger.info(f"🔧 Settings: ping_interval={ping_interval}s, ping_timeout={ping_timeout}s")

            async with websockets.connect(
                WEBSOCKET_URL, ssl=ssl_ctx,
                ping_interval=ping_interval, ping_timeout=ping_timeout,
                open_timeout=30, max_size=20971520, compression=None
            ) as ws:
                logger.info("✅ WebSocket connected successfully")

                # === REGISTER: bytecode dòng 438-447 ===
                # BUILD_CONST_KEY_MAP 2 với keys ('event', 'data')
                # data = {'license_key': self.license_key}  (BUILD_MAP 1)
                # CHỈ gửi license_key, KHÔNG gửi token
                register_message = {"event": "register", "data": {"license_key": self.license_key}}
                logger.info("📡 Đang đăng ký với server...")
                await ws.send(json.dumps(register_message))

                # Chờ response "registered" - bytecode dòng 485-564
                resp = await asyncio.wait_for(ws.recv(), timeout=15)
                resp_data = json.loads(resp)

                if resp_data.get("event") != "registered":
                    error_msg = f"Registration failed: {resp_data}"
                    logger.error(f"❌ {error_msg}")
                    return saved_files

                # Lấy client_id: response_data.get('data', {}).get('client_id')
                self.client_id = resp_data.get("data", {}).get("client_id", "")
                self.registered = True
                logger.info(f"✅ Registration successful, client_id: {self.client_id}")

                # === CHUẨN BỊ PROMPT DATA: bytecode dòng 2546-3408 ===
                total = len(prompts)
                base_seed = seed or int(time.time()) % 100000

                logger.info(f"📝 Preparing {total} prompts for producer-consumer processing (seed={base_seed})")

                send_queue = []
                for i, prompt_text in enumerate(prompts):
                    # prompt_id format: "pc_{uuid4().hex}_{index}" (bytecode dòng 3128-3176)
                    prompt_id = f"pc_{uuid.uuid4().hex}_{i}"

                    # prompt_data: BUILD_CONST_KEY_MAP 7
                    # keys: ('prompt_id','prompt','aspect_ratio','seed','index','original_prompt','attachment')
                    prompt_data = {
                        "prompt_id": prompt_id,
                        "prompt": prompt_text,
                        "aspect_ratio": aspect_ratio,
                        "seed": base_seed,
                        "index": i,
                        "original_prompt": prompt_text,
                        # `attachment` là bitset int để chỉ định prompt này dùng ảnh tham chiếu nào.
                        # Nếu không có tham chiếu thì để None như flow cũ.
                        "attachment": (
                            int(attachments_by_index[i])
                            if attachments_by_index and i < len(attachments_by_index)
                            else None
                        ),
                    }
                    send_queue.append(prompt_data)
                    logger.info(f"[CLIENT][PROMPT] line={i+1} prompt_id={prompt_id} seed={base_seed}")

                # === GỬI PROMPTS: _producer_task (bytecode dòng 616-960 + 1934-2032) ===
                # 1. Thêm use_legacy_model, image_model_name, upscale_mode vào mỗi item
                # 2. Gom tất cả vào batch_data
                # 3. Gửi 1 lần bằng event "submit_prompt_batch"
                batch_data = []
                for item in send_queue:
                    # Bytecode dòng 616-876: thêm model fields từ self attributes
                    if use_legacy_model:
                        item["use_legacy_model"] = True
                    if not use_legacy_model and image_model_name:
                        item["image_model_name"] = image_model_name
                    if upscale_mode in ("2k", "4k"):
                        item["upscale_mode"] = upscale_mode
                    # Bytecode có field `attachment_order`, chỉ gửi khi có dữ liệu hợp lệ.
                    if attachments_order_by_index and item["index"] < len(attachments_order_by_index):
                        order_list = attachments_order_by_index[item["index"]] or []
                        order_list = [int(x) for x in order_list][:3]
                        if order_list:
                            item["attachment_order"] = order_list
                    batch_data.append(item)

                has_attachments = bool(attachments_payload and attachments_payload.get("images"))

                # Tách nhánh gửi đúng như bytecode:
                # 1) Nhiều prompt + có attachment -> submit_prompt_with_attachments
                # 2) 1 prompt + có attachment -> submit_prompt
                # 3) Không attachment -> submit_prompt_batch
                if has_attachments and total > 1:
                    raw_images = attachments_payload.get("images") or []
                    aspect_ratio_attach = attachments_payload.get(
                        "aspectRatio", "IMAGE_ASPECT_RATIO_LANDSCAPE"
                    )
                    new_images = []
                    for img in raw_images:
                        slot_idx = int(img.get("index", 0))
                        b64_data = str(img.get("base64", "") or "")
                        mime = str(img.get("mimeType", "image/jpeg") or "image/jpeg")
                        # Bytecode xử lý trường hợp data URL: data:image/...;base64,xxxxx
                        if b64_data.startswith("data:") and "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]
                        if b64_data:
                            new_images.append({
                                "index": slot_idx,
                                "base64": b64_data,
                                "mimeType": mime,
                            })

                    payload = {
                        "event": "submit_prompt_with_attachments",
                        "data": {
                            "prompts": batch_data,
                            "attachments": {
                                "images": new_images,
                                "aspectRatio": aspect_ratio_attach,
                            },
                        },
                    }
                    payload_json = json.dumps(payload)
                    await ws.send(payload_json)
                    logger.info(
                        f"📎 Sent submit_prompt_with_attachments | images={len(new_images)} | payload_size={len(payload_json)} bytes"
                    )
                elif has_attachments and total == 1:
                    # Flow single trong bytecode dùng event `submit_prompt` và nhúng cả `attachments`.
                    prompt_data = batch_data[0]
                    submit_message = {
                        "event": "submit_prompt",
                        "data": {
                            "prompt_id": prompt_data["prompt_id"],
                            "prompt": prompt_data["prompt"],
                            "aspect_ratio": prompt_data["aspect_ratio"],
                            "seed": prompt_data["seed"],
                            "original_prompt": prompt_data.get("original_prompt", prompt_data["prompt"]),
                            "attachment": prompt_data.get("attachment"),
                            "attachments": attachments_payload,
                        },
                    }
                    if "attachment_order" in prompt_data:
                        submit_message["data"]["attachment_order"] = prompt_data["attachment_order"]
                    await ws.send(json.dumps(submit_message))
                    logger.info("📎 Sent submit_prompt (single) with attachments")
                else:
                    # Bytecode dòng 1934-1940: submit_prompt_batch
                    payload = {"event": "submit_prompt_batch", "data": batch_data}
                    await ws.send(json.dumps(payload))
                    logger.info(f"📤 Đã gửi {len(batch_data)} prompts qua submit_prompt_batch")

                # === NHẬN KẾT QUẢ: _message_dispatcher_task ===
                received = 0
                failed = 0
                timeout_total = 300

                logger.info(f"⏳ Waiting for all results, timeout: {timeout_total//60} minutes")
                start = time.time()

                while (received + failed) < total and (time.time() - start) < timeout_total:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        data = json.loads(msg)
                        event = data.get("event", "")

                        if event == "prompt_queued":
                            qp = data.get("data", {}).get("queue_position", "?")
                            logger.info(f"📊 Prompt queued | Vị trí hàng đợi: {qp}")

                        elif event == "prompt_result":
                            rd = data.get("data", {})
                            pid = rd.get("prompt_id", "")
                            status = rd.get("status", "")
                            img_b64 = rd.get("image_base64", "")

                            if status == "success" and img_b64:
                                fpath = self._save_image(img_b64, received)
                                if fpath:
                                    saved_files.append(fpath)
                                    fsize = os.path.getsize(fpath) if os.path.exists(fpath) else 0
                                    logger.info(f"💾 Saved [{received+1}/{total}]: {os.path.basename(fpath)} ({fsize} bytes)")
                                received += 1
                            elif status in ("error", "failed"):
                                err = rd.get("error", "Unknown error")
                                logger.warning(f"⚠️ {pid} failed: {err}")
                                failed += 1
                            else:
                                logger.debug(f"📥 Result: status={status}")

                        elif event == "task_status":
                            ts_data = data.get("data", {})
                            msg_text = ts_data.get("message", "")
                            progress = ts_data.get("progress", "")
                            if msg_text:
                                logger.info(f"📡 Task status: {msg_text}")

                        elif event == "stats":
                            qs = data.get("data", {}).get("queue_size", "?")
                            logger.info(f"📊 Server queue_size: {qs}")

                        else:
                            logger.debug(f"📡 Dispatcher: event '{event}'")

                    except asyncio.TimeoutError:
                        logger.warning(f"📥 Timeout, continuing... ({received} received)")

                if received + failed >= total:
                    logger.info(f"✅ All results: {received} completed, {failed} failed")
                else:
                    logger.warning(f"⚠️ Timeout: {received} completed, {failed} failed / {total}")

        except Exception as e:
            logger.error(f"💥 WebSocket error: {e}")

        return saved_files

    def _save_image(self, b64_data, index):
        """Lưu base64 -> JPG, chuẩn theo _message_dispatcher_task"""
        try:
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
            # Filename format: prompt_XXX.jpg (bytecode: f"prompt_{seq:03d}.jpg")
            fname = f"prompt_{index+1:03d}.jpg"
            fpath = os.path.join(self.output_dir, fname)
            with open(fpath, "wb") as f:
                f.write(img_bytes)
            return fpath
        except Exception as e:
            logger.error(f"❌ Save error: {e}")
            return ""

# =================================================================
# HÀM CHÍNH
# =================================================================
async def generate_images(prompts, aspect_ratio="IMAGE_ASPECT_RATIO_SQUARE",
                           use_legacy_model=False, seed=None, output_dir=None,
                           attachments_payload=None, attachments_by_index=None,
                           attachments_order_by_index=None):
    if not output_dir:
        output_dir = OUTPUT_DIR

    api = ChichBongAPIClient(LICENSE_KEY)

    # Bước 1: Verify license
    if not api.verify_license().get("success"):
        logger.error("❌ License không hợp lệ!")
        return []

    # Bước 2: Xem thông tin tài khoản
    api.get_account_info()

    # Bước 3: WebSocket generate
    # start_generation KHÔNG gọi get_tokens — chỉ cần license_key + server_url
    # Token chỉ dùng cho Google API flow (imagen_api.pyc), KHÔNG dùng cho WebSocket
    ws_client = ChichBongWSClient(token=None, license_key=LICENSE_KEY, output_dir=output_dir)
    saved = await ws_client.connect_and_generate(
        prompts=prompts, seed=seed, aspect_ratio=aspect_ratio,
        use_legacy_model=use_legacy_model,
        attachments_payload=attachments_payload,
        attachments_by_index=attachments_by_index,
        attachments_order_by_index=attachments_order_by_index
    )

    # Bước 4: Báo cáo
    if saved:
        api.report_usage(len(saved))
    return saved

def main():
    parser = argparse.ArgumentParser(description="🖼️ ChichBong Imagen4 - Tạo ảnh AI từ Terminal")
    parser.add_argument("prompt", nargs="?", help="Prompt (dùng | để tách nhiều prompt)")
    parser.add_argument("--file", "-f", help="Đọc prompts từ file (mỗi dòng 1 prompt)")
    parser.add_argument("--ratio", "-r", choices=["square", "landscape", "portrait"], default="square")
    parser.add_argument("--legacy", action="store_true", help="Dùng model cũ IMAGEN_3_5")
    parser.add_argument("--seed", "-s", type=int, default=None)
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--info", action="store_true", help="Chỉ xem thông tin tài khoản")
    parser.add_argument(
        "--ref-image",
        action="append",
        default=[],
        help="Ảnh tham chiếu nhân vật. Có thể lặp lại nhiều lần hoặc dùng dấu phẩy: --ref-image a.jpg --ref-image b.jpg",
    )
    parser.add_argument(
        "--ref-order",
        default="",
        help="Thứ tự ưu tiên ảnh tham chiếu theo slot 1..10 (vd: 1,2,3). Nếu bỏ trống sẽ tự map theo tên trong prompt",
    )
    parser.add_argument(
        "--ref-aspect",
        choices=["square", "landscape", "portrait"],
        default="landscape",
        help="Aspect ratio cho block attachments (theo bytecode app gốc)",
    )
    args = parser.parse_args()

    if args.info:
        api = ChichBongAPIClient(LICENSE_KEY)
        api.verify_license()
        api.get_account_info()
        return

    prompts = []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            prompts = [l.strip() for l in f if l.strip()]
    elif args.prompt:
        prompts = [p.strip() for p in args.prompt.split("|") if p.strip()]

    if not prompts:
        parser.print_help()
        return

    ratio_map = {"square": "IMAGE_ASPECT_RATIO_SQUARE",
                 "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                 "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT"}

    # Gom danh sách ảnh tham chiếu từ --ref-image.
    # Hỗ trợ cả cú pháp lặp lại nhiều cờ và cú pháp 1 cờ chứa danh sách phân tách bằng dấu phẩy.
    ref_images = []
    for raw in args.ref_image:
        parts = [p.strip() for p in str(raw).split(",") if p.strip()]
        ref_images.extend(parts)

    attachments_payload = None
    attachments_by_index = None
    attachments_order_by_index = None
    if ref_images:
        if len(ref_images) > 10:
            print("❌ Tối đa 10 ảnh tham chiếu mỗi lần chạy (chuẩn app gốc).")
            return

        # Validate file tồn tại trước khi gửi request, để dễ debug cho người dùng.
        for image_path in ref_images:
            if not os.path.isfile(image_path):
                print(f"❌ Không tìm thấy file ảnh tham chiếu: {image_path}")
                return

        attachments_payload = _build_attachments_payload(
            ref_image_paths=ref_images,
            attachments_aspect_ratio=ratio_map[args.ref_aspect],
        )
        selected_indices = [img["index"] for img in attachments_payload["images"]]
        ref_name_entries = _build_reference_name_entries(ref_images)

        # Nếu có --ref-order: ép dùng thứ tự đó cho mọi prompt.
        # Nếu không: tự map theo tên file xuất hiện trong từng prompt.
        if args.ref_order.strip():
            try:
                parsed_order = [int(x.strip()) for x in args.ref_order.split(",") if x.strip()]
            except ValueError:
                print("❌ --ref-order không hợp lệ. Ví dụ đúng: --ref-order 1,2,3")
                return
            # Chuẩn app gốc: attachment_order chỉ nhận slot index 1..10.
            order_to_use = [x for x in parsed_order if 1 <= x <= 10][:3]
            attachment_bitset = _compute_attachment_bitset(order_to_use or selected_indices)
            attachments_by_index = [attachment_bitset] * len(prompts)
            attachments_order_by_index = [order_to_use] * len(prompts)
            logger.info(
                f"📎 Reference enabled (forced order) | images={len(ref_images)} | bitset={attachment_bitset} | order={order_to_use}"
            )
        else:
            attachments_by_index = []
            attachments_order_by_index = []
            for i, prompt_text in enumerate(prompts):
                matched_slots = _match_prompt_to_slots(prompt_text, ref_name_entries)
                order_for_prompt = matched_slots[:3]
                bitset_for_prompt = _compute_attachment_bitset(matched_slots)
                attachments_by_index.append(bitset_for_prompt if bitset_for_prompt > 0 else None)
                attachments_order_by_index.append(order_for_prompt)
                logger.info(
                    f"[REF-MAP] line={i+1} matched_slots={matched_slots} bitset={bitset_for_prompt}"
                )

            # Fallback: nếu tất cả prompt đều không match tên file, dùng toàn bộ ảnh như cách cũ.
            if not any(v for v in attachments_by_index):
                fallback_bitset = _compute_attachment_bitset(selected_indices)
                fallback_order = selected_indices[:3]
                attachments_by_index = [fallback_bitset] * len(prompts)
                attachments_order_by_index = [fallback_order] * len(prompts)
                logger.info(
                    f"📎 Reference enabled (fallback all slots) | images={len(ref_images)} | bitset={fallback_bitset} | order={fallback_order}"
                )

    print(f"\n{'='*50}")
    print(f"🖼️  ChichBong Imagen4 Generator")
    print(f"📝 Prompts: {len(prompts)} | 📐 Ratio: {args.ratio}")
    print(f"{'='*50}\n")

    saved = asyncio.run(generate_images(
        prompts=prompts, aspect_ratio=ratio_map[args.ratio],
        use_legacy_model=args.legacy, seed=args.seed, output_dir=args.output,
        attachments_payload=attachments_payload,
        attachments_by_index=attachments_by_index,
        attachments_order_by_index=attachments_order_by_index
    ))

    print(f"\n{'='*50}")
    if saved:
        print(f"✅ Tạo thành công {len(saved)} ảnh!")
        for fp in saved:
            print(f"   📁 {fp}")
    else:
        print("❌ Không tạo được ảnh nào.")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import requests
from datetime import datetime
from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

class ApiImagenService:
    """Dịch vụ gọi API cho app Imagen4"""
    def __init__(self, license_key):
        self.license_key = license_key
        self.base_url = "https://11labs.net"
        self.timeout = 15
        # Khởi tạo QSettings để lưu thông tin tài khoản
        self.settings = QSettings("ElevenLabs", "ElevenLabs TTS Client")

    def get_account_info(self):
        """Lấy thông tin tài khoản từ server cho Imagen4"""
        endpoint = "/api/account/info"
        params = {"license_key": self.license_key, "app": "imagen4"}
        url = f"{self.base_url}{endpoint}"
        try:
            logger.info(f"[Imagen4] Gửi request GET {url} với params: {params}")
            response = requests.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"[Imagen4] Nhận account info: {data}")
                info = data.get('data', {}).get('account_info', {})
                # Parse các trường cần thiết
                email = info.get('email', '-')
                imagen_buy_package = info.get('imagen_buy_package', 0)
                expiry_imagen = info.get('expiry_imagen', '-')
                imagen_count = info.get('imagen_count', 0)
                total_credits = info.get('total_credits', 0)
                is_expired = info.get('is_expired', False)
                imagen_limit_no_package = info.get('imagen_limit_no_package', 100)
                imagen_free_threshold = info.get('imagen_free_threshold', 0)
                system_prompt_deepseek = info.get('system_prompt_deepseek', None)
                imagen_count_today = info.get('imagen_count_today', 0)
                imagen_per_day = info.get('imagen_per_day', 50)
                
                # Xử lý expiry_imagen - đảm bảo không bị None
                if expiry_imagen and expiry_imagen != '-' and isinstance(expiry_imagen, str):
                    # Loại bỏ giờ trong ngày hết hạn nếu có
                    if ' ' in expiry_imagen:
                        expiry_imagen = expiry_imagen.split(' ')[0]
                elif expiry_imagen is None or expiry_imagen == '' or expiry_imagen == 'null':
                    expiry_imagen = '-'
                
                # Xác định loại tài khoản - cập nhật để nhất quán với logic unlimited
                is_vip = False
                if imagen_buy_package in [1, True, '1', 'true'] and expiry_imagen and expiry_imagen != '-' and expiry_imagen >= datetime.now().strftime('%Y-%m-%d'):
                    is_vip = True
                elif total_credits >= imagen_free_threshold and not is_expired:
                    is_vip = True
                
                account_type = 'VIP' if is_vip else 'Thường'
                
                # Logic số lượt tạo ảnh
                show_unlimited = False
                if (total_credits >= imagen_free_threshold and not is_expired) or (imagen_buy_package in [1, True, '1', 'true'] and expiry_imagen and expiry_imagen != '-' and expiry_imagen >= datetime.now().strftime('%Y-%m-%d')):
                    show_unlimited = True
                if show_unlimited:
                    usage_str = f"{imagen_count} / ∞"
                    max_images = '∞'
                else:
                    usage_str = f"{imagen_count} / {imagen_limit_no_package} ảnh"
                    max_images = imagen_limit_no_package
                
                # Tạo dict kết quả
                result = {
                    'email': email,
                    'loai_tai_khoan': account_type,
                    'so_lan_tao_anh': usage_str,
                    'ngay_het_han': expiry_imagen,
                    'max_images': max_images,
                    'raw': data,
                    # Thêm các thông tin chi tiết để dễ truy cập
                    'imagen_buy_package': imagen_buy_package,
                    'imagen_count': imagen_count,
                    'total_credits': total_credits,
                    'is_expired': is_expired,
                    'imagen_limit_no_package': imagen_limit_no_package,
                    'imagen_free_threshold': imagen_free_threshold,
                    'expiry_imagen': expiry_imagen,
                    'system_prompt_deepseek': system_prompt_deepseek,
                    'imagen_count_today': imagen_count_today,
                    'imagen_per_day': imagen_per_day
                }
                
                # Debug VIP logic
                self.debug_vip_logic(result)
                
                # Lưu thông tin vào QSettings
                self.save_account_info_to_settings(result)
                logger.info(f"[Imagen4] Đã lưu thông tin tài khoản vào QSettings: {result}")
                
                return result
            else:
                logger.error(f"[Imagen4] Lỗi khi lấy account info: HTTP {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"[Imagen4] Exception khi lấy account info: {str(e)}")
            return {"success": False, "error": str(e)}

    def save_account_info_to_settings(self, account_info):
        """Lưu thông tin tài khoản vào QSettings"""
        try:
            # Lưu từng trường thông tin với key account_imagen4
            self.settings.setValue("account_imagen4/email", account_info.get('email', '-'))
            self.settings.setValue("account_imagen4/loai_tai_khoan", account_info.get('loai_tai_khoan', 'Thường'))
            self.settings.setValue("account_imagen4/so_lan_tao_anh", account_info.get('so_lan_tao_anh', '0 / 100 ảnh'))
            self.settings.setValue("account_imagen4/ngay_het_han", account_info.get('ngay_het_han', '-'))
            self.settings.setValue("account_imagen4/max_images", account_info.get('max_images', '100'))
            
            # Lưu thêm các thông tin chi tiết từ raw data
            raw_data = account_info.get('raw', {})
            if raw_data:
                account_raw = raw_data.get('data', {}).get('account_info', {})
                self.settings.setValue("account_imagen4/imagen_buy_package", account_raw.get('imagen_buy_package', 0))
                self.settings.setValue("account_imagen4/imagen_count", account_raw.get('imagen_count', 0))
                self.settings.setValue("account_imagen4/total_credits", account_raw.get('total_credits', 0))
                self.settings.setValue("account_imagen4/is_expired", account_raw.get('is_expired', False))
                self.settings.setValue("account_imagen4/imagen_limit_no_package", account_raw.get('imagen_limit_no_package', 100))
                self.settings.setValue("account_imagen4/imagen_free_threshold", account_raw.get('imagen_free_threshold', 0))
                self.settings.setValue("account_imagen4/expiry_imagen", account_raw.get('expiry_imagen', '-'))
                self.settings.setValue("account_imagen4/system_prompt_deepseek", account_raw.get('system_prompt_deepseek', None))
                self.settings.setValue("account_imagen4/imagen_count_today", account_raw.get('imagen_count_today', 0))
                self.settings.setValue("account_imagen4/imagen_per_day", account_raw.get('imagen_per_day', 50))
            
            # Lưu timestamp để biết khi nào cập nhật lần cuối
            self.settings.setValue("account_imagen4/last_updated", datetime.now().isoformat())
            
            # Sync để đảm bảo lưu ngay lập tức
            self.settings.sync()
            
            logger.info(f"[Imagen4] Đã lưu thông tin tài khoản vào QSettings thành công")
            
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi lưu thông tin tài khoản vào QSettings: {str(e)}")

    def get_account_info_from_settings(self):
        """Lấy thông tin tài khoản từ QSettings (cache)"""
        try:
            # Kiểm tra xem có thông tin trong cache không
            last_updated = self.settings.value("account_imagen4/last_updated")
            if not last_updated:
                logger.info(f"[Imagen4] Không có thông tin tài khoản trong cache")
                return None
            
            # Tạo dict từ QSettings với key account_imagen4
            cached_info = {
                'email': self.settings.value("account_imagen4/email", '-'),
                'loai_tai_khoan': self.settings.value("account_imagen4/loai_tai_khoan", 'Thường'),
                'so_lan_tao_anh': self.settings.value("account_imagen4/so_lan_tao_anh", '0 / 100 ảnh'),
                'ngay_het_han': self.settings.value("account_imagen4/ngay_het_han", '-'),
                'max_images': self.settings.value("account_imagen4/max_images", '100'),
                'last_updated': last_updated,
                # Thêm các thông tin chi tiết
                'imagen_buy_package': self.settings.value("account_imagen4/imagen_buy_package", 0),
                'imagen_count': self.settings.value("account_imagen4/imagen_count", 0),
                'total_credits': self.settings.value("account_imagen4/total_credits", 0),
                'is_expired': self.settings.value("account_imagen4/is_expired", False),
                'imagen_limit_no_package': self.settings.value("account_imagen4/imagen_limit_no_package", 100),
                'imagen_free_threshold': self.settings.value("account_imagen4/imagen_free_threshold", 0),
                'expiry_imagen': self.settings.value("account_imagen4/expiry_imagen", '-'),
                'system_prompt_deepseek': self.settings.value("account_imagen4/system_prompt_deepseek", None),
                'imagen_count_today': self.settings.value("account_imagen4/imagen_count_today", 0),
                'imagen_per_day': self.settings.value("account_imagen4/imagen_per_day", 50)
            }
            
            logger.info(f"[Imagen4] Lấy thông tin tài khoản từ cache: {cached_info}")
            return cached_info
            
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi lấy thông tin tài khoản từ cache: {str(e)}")
            return None

    def clear_account_info_cache(self):
        """Xóa cache thông tin tài khoản"""
        try:
            # Xóa tất cả key liên quan đến account_imagen4
            self.settings.remove("account_imagen4/email")
            self.settings.remove("account_imagen4/loai_tai_khoan")
            self.settings.remove("account_imagen4/so_lan_tao_anh")
            self.settings.remove("account_imagen4/ngay_het_han")
            self.settings.remove("account_imagen4/max_images")
            self.settings.remove("account_imagen4/last_updated")
            self.settings.remove("account_imagen4/imagen_buy_package")
            self.settings.remove("account_imagen4/imagen_count")
            self.settings.remove("account_imagen4/total_credits")
            self.settings.remove("account_imagen4/is_expired")
            self.settings.remove("account_imagen4/imagen_limit_no_package")
            self.settings.remove("account_imagen4/imagen_free_threshold")
            self.settings.remove("account_imagen4/expiry_imagen")
            self.settings.remove("account_imagen4/system_prompt_deepseek")
            self.settings.remove("account_imagen4/imagen_count_today")
            self.settings.remove("account_imagen4/imagen_per_day")
            self.settings.sync()
            
            logger.info(f"[Imagen4] Đã xóa cache thông tin tài khoản")
            
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi xóa cache thông tin tài khoản: {str(e)}")

    def get_detailed_account_info_from_settings(self):
        """Lấy thông tin chi tiết tài khoản từ QSettings (cache) - bao gồm tất cả thông tin"""
        try:
            # Kiểm tra xem có thông tin trong cache không
            last_updated = self.settings.value("account_imagen4/last_updated")
            if not last_updated:
                logger.info(f"[Imagen4] Không có thông tin tài khoản chi tiết trong cache")
                return None
            
            # Tạo dict chi tiết từ QSettings với key account_imagen4
            detailed_info = {
                # Thông tin cơ bản
                'email': self.settings.value("account_imagen4/email", '-'),
                'loai_tai_khoan': self.settings.value("account_imagen4/loai_tai_khoan", 'Thường'),
                'so_lan_tao_anh': self.settings.value("account_imagen4/so_lan_tao_anh", '0 / 100 ảnh'),
                'ngay_het_han': self.settings.value("account_imagen4/ngay_het_han", '-'),
                'max_images': self.settings.value("account_imagen4/max_images", '100'),
                'last_updated': last_updated,
                
                # Thông tin chi tiết từ server
                'imagen_buy_package': self.settings.value("account_imagen4/imagen_buy_package", 0),
                'imagen_count': self.settings.value("account_imagen4/imagen_count", 0),
                'total_credits': self.settings.value("account_imagen4/total_credits", 0),
                'is_expired': self.settings.value("account_imagen4/is_expired", False),
                'imagen_limit_no_package': self.settings.value("account_imagen4/imagen_limit_no_package", 100),
                'imagen_free_threshold': self.settings.value("account_imagen4/imagen_free_threshold", 0),
                'expiry_imagen': self.settings.value("account_imagen4/expiry_imagen", '-'),
                'system_prompt_deepseek': self.settings.value("account_imagen4/system_prompt_deepseek", None),
                'imagen_count_today': self.settings.value("account_imagen4/imagen_count_today", 0),
                'imagen_per_day': self.settings.value("account_imagen4/imagen_per_day", 50)
            }
            
            logger.info(f"[Imagen4] Lấy thông tin chi tiết tài khoản từ cache: {detailed_info}")
            return detailed_info
            
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi lấy thông tin chi tiết tài khoản từ cache: {str(e)}")
            return None

    def is_cache_valid(self, max_age_minutes=30):
        """Kiểm tra xem cache có còn hợp lệ không (dựa trên thời gian)"""
        try:
            last_updated = self.settings.value("account_imagen4/last_updated")
            if not last_updated:
                return False
            
            # Parse timestamp
            from datetime import datetime
            try:
                last_update_time = datetime.fromisoformat(last_updated)
                current_time = datetime.now()
                time_diff = current_time - last_update_time
                
                # Cache hợp lệ nếu chưa quá max_age_minutes phút
                is_valid = time_diff.total_seconds() < (max_age_minutes * 60)
                logger.info(f"[Imagen4] Cache age: {time_diff.total_seconds()/60:.1f} minutes, valid: {is_valid}")
                return is_valid
                
            except Exception as parse_error:
                logger.error(f"[Imagen4] Lỗi parse timestamp: {parse_error}")
                return False
                
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi kiểm tra cache validity: {str(e)}")
            return False

    def debug_cache(self):
        """Debug để xem tất cả thông tin cache đã lưu"""
        try:
            logger.info("=== DEBUG CACHE ACCOUNT_IMAGEN4 ===")
            
            # Lấy tất cả key liên quan đến account_imagen4
            all_keys = [
                "account_imagen4/email",
                "account_imagen4/loai_tai_khoan", 
                "account_imagen4/so_lan_tao_anh",
                "account_imagen4/ngay_het_han",
                "account_imagen4/max_images",
                "account_imagen4/last_updated",
                "account_imagen4/imagen_buy_package",
                "account_imagen4/imagen_count",
                "account_imagen4/total_credits",
                "account_imagen4/is_expired",
                "account_imagen4/imagen_limit_no_package",
                "account_imagen4/imagen_free_threshold",
                "account_imagen4/expiry_imagen",
                "account_imagen4/system_prompt_deepseek",
                "account_imagen4/imagen_count_today",
                "account_imagen4/imagen_per_day"
            ]
            
            for key in all_keys:
                value = self.settings.value(key, "NOT_FOUND")
                logger.info(f"[Imagen4] {key}: {value}")
            
            logger.info("=== END DEBUG CACHE ===")
            
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi debug cache: {str(e)}")

    def debug_vip_logic(self, account_info):
        """Debug logic VIP để kiểm tra các điều kiện"""
        try:
            logger.info("=== DEBUG VIP LOGIC ===")
            
            # Lấy các giá trị từ account_info
            imagen_buy_package = account_info.get('imagen_buy_package', 0)
            expiry_imagen = account_info.get('expiry_imagen', '-')
            total_credits = account_info.get('total_credits', 0)
            is_expired = account_info.get('is_expired', False)
            imagen_free_threshold = account_info.get('imagen_free_threshold', 0)
            system_prompt_deepseek = account_info.get('system_prompt_deepseek', None)
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            logger.info(f"[Imagen4] imagen_buy_package: {imagen_buy_package} (type: {type(imagen_buy_package)})")
            logger.info(f"[Imagen4] expiry_imagen: {expiry_imagen}")
            logger.info(f"[Imagen4] total_credits: {total_credits}")
            logger.info(f"[Imagen4] is_expired: {is_expired}")
            logger.info(f"[Imagen4] imagen_free_threshold: {imagen_free_threshold}")
            logger.info(f"[Imagen4] system_prompt_deepseek: {system_prompt_deepseek}")
            logger.info(f"[Imagen4] current_date: {current_date}")
            
            # Kiểm tra điều kiện 1: Mua package VIP
            condition1 = imagen_buy_package in [1, True, '1', 'true']
            condition2 = expiry_imagen and expiry_imagen != '-'
            condition3 = expiry_imagen >= current_date if condition2 else False
            
            vip_by_package = condition1 and condition2 and condition3
            logger.info(f"[Imagen4] VIP by package: {vip_by_package}")
            logger.info(f"[Imagen4]   - condition1 (imagen_buy_package valid): {condition1}")
            logger.info(f"[Imagen4]   - condition2 (expiry_imagen exists): {condition2}")
            logger.info(f"[Imagen4]   - condition3 (not expired): {condition3}")
            
            # Kiểm tra điều kiện 2: Đủ credits
            condition4 = total_credits >= imagen_free_threshold
            condition5 = not is_expired
            
            vip_by_credits = condition4 and condition5
            logger.info(f"[Imagen4] VIP by credits: {vip_by_credits}")
            logger.info(f"[Imagen4]   - condition4 (enough credits): {condition4} ({total_credits} >= {imagen_free_threshold})")
            logger.info(f"[Imagen4]   - condition5 (not expired): {condition5}")
            
            # Kết quả cuối cùng
            is_vip = vip_by_package or vip_by_credits
            logger.info(f"[Imagen4] Final VIP result: {is_vip}")
            logger.info(f"[Imagen4] Account type: {'VIP' if is_vip else 'Thường'}")
            
            logger.info("=== END DEBUG VIP LOGIC ===")
            
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi debug VIP logic: {str(e)}")

    def check_generation_conditions(self, prompt_count=0):
        """Kiểm tra điều kiện tạo ảnh dựa trên thông tin tài khoản và số lượng prompts"""
        try:
            logger.info(f"[Imagen4] Kiểm tra điều kiện tạo ảnh với {prompt_count} prompts")
            
            # Lấy thông tin tài khoản từ cache trước
            account_info = self.get_detailed_account_info_from_settings()
            if not account_info:
                logger.warning("[Imagen4] Không có thông tin tài khoản trong cache, cần refresh")
                return {
                    'can_generate': False,
                    'reason': 'Không có thông tin tài khoản. Vui lòng thử lại.',
                    'details': {
                        'is_vip': False,
                        'imagen_count': 0,
                        'imagen_limit_no_package': 100,
                        'remaining_slots': 0
                    }
                }
            
            # Lấy các thông tin cần thiết
            imagen_count = int(account_info.get('imagen_count', 0))
            imagen_limit_no_package = int(account_info.get('imagen_limit_no_package', 100))
            imagen_count_today = int(account_info.get('imagen_count_today', 0))
            imagen_per_day = int(account_info.get('imagen_per_day', 50))
            is_vip = account_info.get('loai_tai_khoan', 'Thường') == 'VIP'

            # Kiểm tra điều kiện 1: Đã đạt giới hạn ảnh/ngày (áp dụng cho cả VIP và thường)
            if imagen_count_today + prompt_count > imagen_per_day:
                logger.warning(f"[Imagen4] Đã đạt giới hạn ảnh/ngày: {imagen_count_today}/{imagen_per_day}, yêu cầu tạo {prompt_count} ảnh")
                return {
                    'can_generate': False,
                    'reason': f'Bạn đã tạo {imagen_count_today}/{imagen_per_day} ảnh hôm nay. Vui lòng quay lại vào ngày mai!',
                    'details': {
                        'is_vip': is_vip,
                        'imagen_count_today': imagen_count_today,
                        'imagen_per_day': imagen_per_day,
                        'remaining_today': max(0, imagen_per_day - imagen_count_today),
                        'prompt_count': prompt_count
                    }
                }

            logger.info(f"[Imagen4] Thông tin kiểm tra: VIP={is_vip}, imagen_count={imagen_count}, limit={imagen_limit_no_package}, prompts={prompt_count}")
            
            # Nếu là VIP thì luôn cho phép tạo ảnh (ngoại trừ đã bị chặn bởi giới hạn/ngày ở trên)
            if is_vip:
                logger.info("[Imagen4] Tài khoản VIP - cho phép tạo ảnh không giới hạn")
                return {
                    'can_generate': True,
                    'reason': 'Tài khoản VIP - không giới hạn số lượng ảnh (nhưng vẫn bị giới hạn/ngày)',
                    'details': {
                        'is_vip': True,
                        'imagen_count': imagen_count,
                        'imagen_limit_no_package': imagen_limit_no_package,
                        'remaining_slots': float('inf')
                    }
                }
            
            # Nếu không phải VIP, kiểm tra giới hạn tổng
            remaining_slots = imagen_limit_no_package - imagen_count
            
            # Kiểm tra điều kiện 2: Đã đạt giới hạn tổng
            if imagen_count >= imagen_limit_no_package:
                logger.warning(f"[Imagen4] Đã đạt giới hạn: {imagen_count}/{imagen_limit_no_package}")
                return {
                    'can_generate': False,
                    'reason': f'Bạn đã đạt giới hạn tạo ảnh ({imagen_count}/{imagen_limit_no_package}). Vui lòng nâng cấp lên VIP để tạo ảnh không giới hạn.',
                    'details': {
                        'is_vip': False,
                        'imagen_count': imagen_count,
                        'imagen_limit_no_package': imagen_limit_no_package,
                        'remaining_slots': 0
                    }
                }
            
            # Kiểm tra điều kiện 3: Số prompts vượt quá slot còn lại
            if prompt_count > remaining_slots:
                logger.warning(f"[Imagen4] Số prompts ({prompt_count}) vượt quá slot còn lại ({remaining_slots})")
                return {
                    'can_generate': False,
                    'reason': f'Bạn chỉ còn {remaining_slots} slot tạo ảnh nhưng đã nhập {prompt_count} prompts. Vui lòng giảm số lượng prompts hoặc nâng cấp lên VIP.',
                    'details': {
                        'is_vip': False,
                        'imagen_count': imagen_count,
                        'imagen_limit_no_package': imagen_limit_no_package,
                        'remaining_slots': remaining_slots
                    }
                }
            
            # Nếu qua tất cả điều kiện thì cho phép tạo ảnh
            logger.info(f"[Imagen4] Cho phép tạo ảnh: còn {remaining_slots} slot, cần {prompt_count} prompts")
            return {
                'can_generate': True,
                'reason': f'Có thể tạo {prompt_count} ảnh. Còn lại {remaining_slots - prompt_count} slot.',
                'details': {
                    'is_vip': False,
                    'imagen_count': imagen_count,
                    'imagen_limit_no_package': imagen_limit_no_package,
                    'remaining_slots': remaining_slots
                }
            }
        except Exception as e:
            logger.error(f"[Imagen4] Lỗi khi kiểm tra điều kiện tạo ảnh: {str(e)}")
            return {
                'can_generate': False,
                'reason': f'Lỗi khi kiểm tra điều kiện: {str(e)}',
                'details': {
                    'is_vip': False,
                    'imagen_count': 0,
                    'imagen_limit_no_package': 100,
                    'remaining_slots': 0
                }
            }

    def get_imagen4_tokens_via_license(self, limit=5):
        """Gọi endpoint get-imagen4-token.php để lấy token bằng license_key"""
        endpoint = "/api/checker/get-imagen4-token.php"
        url = f"{self.base_url}{endpoint}"
        data = {
            'license_key': self.license_key,
            'limit': limit
        }
        try:
            logger.info(f"[Imagen4] Gửi request POST {url} với data: {data}")
            response = requests.post(url, json=data, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    tokens = result.get('data', {}).get('tokens', [])
                    logger.info(f"[Imagen4] Nhận {len(tokens)} tokens từ server")
                    return tokens
                else:
                    logger.error(f"[Imagen4] Lỗi lấy token: {result.get('message')}")
                    return []
            else:
                logger.error(f"[Imagen4] Lỗi HTTP khi lấy token: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"[Imagen4] Exception khi lấy token: {str(e)}")
            return []

    def report_imagen_counter(self, successful_count):
        """Báo cáo số lần tạo ảnh thành công lên server"""
        endpoint = "/api/resource/report-imagen-counter.php"
        url = f"{self.base_url}{endpoint}"
        data = {
            'license_key': self.license_key,
            'successful_count': successful_count
        }
        try:
            logger.info(f"[Imagen4] Gửi request POST {url} với data: {data}")
            response = requests.post(url, json=data, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    count_added = result.get('data', {}).get('count_added', 0)
                    total_count = result.get('data', {}).get('total_imagen_count', 0)
                    logger.info(f"[Imagen4] Báo cáo thành công: thêm {count_added} lần, tổng: {total_count}")
                    return {
                        'success': True,
                        'count_added': count_added,
                        'total_imagen_count': total_count
                    }
                else:
                    logger.error(f"[Imagen4] Lỗi báo cáo counter: {result.get('message')}")
                    return {
                        'success': False,
                        'error': result.get('message', 'Unknown error')
                    }
            else:
                logger.error(f"[Imagen4] Lỗi HTTP khi báo cáo counter: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            logger.error(f"[Imagen4] Exception khi báo cáo counter: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_payment_packages(self):
        """Lấy danh sách gói cước cho Imagen4"""
        endpoint = "/api/payment/packages.php"
        params = {
            "license_key": self.license_key,
            "brand": getattr(self, 'brand_id', 'imagen4')
        }
        url = f"{self.base_url}{endpoint}"
        try:
            logger.info(f"[Imagen4] Gửi request GET {url} với params: {params}")
            response = requests.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[Imagen4] Lấy danh sách gói cước thành công: {result}")
                return result
            else:
                logger.error(f"[Imagen4] Lỗi khi lấy danh sách gói cước: HTTP {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"[Imagen4] Exception khi lấy danh sách gói cước: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_payment_order(self, package_id, payment_method="sepay"):
        """Tạo đơn hàng thanh toán cho Imagen4"""
        endpoint = "/api/payment/create_order.php"
        data = {
            "license_key": self.license_key,
            "package_id": package_id,
            "payment_method": payment_method,
            "brand": getattr(self, 'brand_id', 'imagen4')
        }
        url = f"{self.base_url}{endpoint}"
        try:
            logger.info(f"[Imagen4] Gửi request POST {url} với data: {data}")
            response = requests.post(url, json=data, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[Imagen4] Tạo đơn hàng thành công: {result}")
                return result
            else:
                logger.error(f"[Imagen4] Lỗi khi tạo đơn hàng: HTTP {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"[Imagen4] Exception khi tạo đơn hàng: {str(e)}")
            return {"success": False, "error": str(e)}

    def check_payment_status(self, order_id):
        """Kiểm tra trạng thái thanh toán cho Imagen4"""
        # Đồng bộ với Veo3/11labs: check theo order id qua endpoint license/check_payment_status.php
        # Server kỳ vọng param tên là "order" (không phải "order_id")
        endpoint = "/api/license/check_payment_status.php"
        try:
            order_int = int(order_id)
        except Exception:
            order_int = order_id
        params = {"order": order_int}
        url = f"{self.base_url}{endpoint}"
        try:
            logger.info(f"[Imagen4] Gửi request GET {url} với params: {params}")
            response = requests.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[Imagen4] Kiểm tra trạng thái thanh toán thành công: {result}")
                return result
            else:
                logger.error(f"[Imagen4] Lỗi khi kiểm tra trạng thái thanh toán: HTTP {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"[Imagen4] Exception khi kiểm tra trạng thái thanh toán: {str(e)}")
            return {"success": False, "error": str(e)}
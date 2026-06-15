#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import requests
from datetime import datetime
from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

# Lấy BRAND_CONFIG từ main hoặc fallback
def _get_brand_qsettings():
	try:
		import sys
		main_module = sys.modules.get('main_imagen') or sys.modules.get('__main__')
		if main_module and hasattr(main_module, 'BRAND_CONFIG'):
			conf = getattr(main_module, 'BRAND_CONFIG')
			return conf.get('qsettings_org', 'Imagen4'), conf.get('qsettings_app', 'Imagen4 Client')
	except Exception:
		pass
	# fallback
	return 'Imagen4', 'Imagen4 Client'

# Thêm: hàm lấy payments_brand an toàn từ BRAND_CONFIG (fallback brand.txt)
def _get_payments_brand():
	try:
		import sys
		main_module = sys.modules.get('main_imagen') or sys.modules.get('__main__')
		if main_module and hasattr(main_module, 'BRAND_CONFIG'):
			conf = getattr(main_module, 'BRAND_CONFIG')
			return conf.get('payments_brand', 'imagen4')
	except Exception:
		pass
	# Fallback: đọc resources/brand.txt và dùng branding.get_brand_config
	try:
		import sys as _sys, os as _os
		if getattr(_sys, 'frozen', False):
			base_path = _os.path.dirname(_sys.executable)
		else:
			base_path = _os.path.dirname(__file__)
		brand_file = _os.path.join(base_path, 'resources', 'brand.txt')
		brand_code = None
		if _os.path.exists(brand_file):
			with open(brand_file, 'r', encoding='utf-8') as bf:
				brand_code = bf.read().strip()
		from branding import get_brand_config
		conf = get_brand_config(brand_code or os.getenv('APP_BRAND', 'imagen4'))
		return conf.get('payments_brand', 'imagen4')
	except Exception:
		return 'imagen4'

class LicenseService:
	"""Dịch vụ quản lý license cho Imagen4"""
	
	def __init__(self):
		self.base_url = "https://11labs.net"
		self.timeout = 20
		
		# Sử dụng QSettings cùng brand với phần mềm chính
		org, app = _get_brand_qsettings()
		self.settings = QSettings(org, app)
	
	def save_last_email(self, email):
		"""Lưu email đã sử dụng cho imagen4"""
		self.settings.setValue('last_email_imagen4', email)
		self.settings.setValue('activation/last_email', email)
		self.settings.sync()
		logger.info(f"Đã lưu email: {email}")
		
	def get_last_email(self):
		"""Lấy email đã sử dụng lần trước"""
		# Thử các key khác nhau
		email_keys = [
			'last_email_imagen4',
			'last_email_elevenlabs', 
			'activation/last_email'
		]
		
		for key in email_keys:
			email = self.settings.value(key, '', str)
			if email and '@' in email:
				return email
		
		return ''
	
	def _make_request(self, method, endpoint, params=None, data=None, json_data=None):
		"""Gửi yêu cầu đến API"""
		try:
			url = f"{self.base_url}{endpoint}"
			logger.info(f"🚀 [_MAKE_REQUEST] Starting {method} request...")
			logger.info(f"🌐 Gửi yêu cầu {method} đến {url}")
			
			if json_data:
				logger.info(f"📤 Dữ liệu gửi đi: {json_data}")
			
			logger.info(f"⏳ [_MAKE_REQUEST] Sending request with timeout {self.timeout}s...")
			response = requests.request(
				method,
				url,
				params=params,
				data=data,
				json=json_data,
				timeout=self.timeout
			)
			logger.info(f"✅ [_MAKE_REQUEST] Request completed successfully")
			
			logger.info(f"📡 Mã phản hồi: {response.status_code}")
			logger.info(f"📥 Nội dung phản hồi: {response.text}")
			
			if response.status_code == 200:
				return response.json()
			else:
				logger.error(f"❌ Lỗi API: {response.status_code} - {response.text}")
				return {
					"success": False,
					"message": f"Lỗi máy chủ: HTTP {response.status_code}"
				}
		
		except requests.exceptions.Timeout:
			logger.error("⏱️ [_MAKE_REQUEST] API request timed out")
			logger.exception("Timeout stack trace:")
			return {
				"success": False,
				"message": "Yêu cầu hết thời gian chờ. Vui lòng kiểm tra kết nối mạng."
			}
		
		except requests.exceptions.ConnectionError as ce:
			logger.error(f"🔌 [_MAKE_REQUEST] API connection error: {str(ce)}")
			logger.exception("Connection error stack trace:")
			return {
				"success": False,
				"message": "Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối mạng."
			}
		
		except Exception as e:
			logger.error(f"💥 [_MAKE_REQUEST] API request error: {str(e)}")
			logger.exception("Full stack trace:")
			return {
				"success": False,
				"message": f"Lỗi: {str(e)}"
			}
	
	def request_new_license(self, email, hardware_id, cpu_id, mainboard_uuid):
		"""Gửi yêu cầu cấp license mới cho imagen4"""
		try:
			logger.info(f"🚀 [LICENSE_SERVICE] Starting request_new_license...")
			logger.info(f"🔑 Đang gửi yêu cầu license mới cho email: {email}")
			logger.info(f"🖥️ Thông tin thiết bị:")
			logger.info(f"   Hardware ID: {hardware_id}")
			logger.info(f"   CPU ID: {cpu_id}")
			logger.info(f"   Mainboard UUID: {mainboard_uuid}")
			brand_for_activation = _get_payments_brand()
			logger.info(f"   Brand (payments): {brand_for_activation}")
			
			# Kiểm tra thông tin bắt buộc
			logger.info("🔍 [LICENSE_SERVICE] Validating required fields...")
			if not all([email, hardware_id, cpu_id, mainboard_uuid]):
				logger.error("❌ [LICENSE_SERVICE] Missing required fields")
				return {
					'success': False,
					'message': 'Thiếu thông tin bắt buộc để yêu cầu license'
				}
			
			# Kiểm tra email format
			logger.info("📧 [LICENSE_SERVICE] Validating email format...")
			if not email or '@' not in email or '.' not in email:
				logger.error(f"❌ [LICENSE_SERVICE] Invalid email format: {email}")
				return {
					'success': False,
					'message': 'Email không hợp lệ'
				}
			
			# Gửi yêu cầu API với brand theo payments_brand
			logger.info("📡 [LICENSE_SERVICE] Preparing API request...")
			endpoint = "/api/license/activate.php"
			data = {
				"email": email.strip(),
				"hardware_id": hardware_id,
				"cpu_id": cpu_id,
				"mainboard_uuid": mainboard_uuid,
				"brand": brand_for_activation
			}
			
			logger.info(f"🌐 [LICENSE_SERVICE] Making API request to {self.base_url}{endpoint}")
			logger.info(f"📤 [LICENSE_SERVICE] Request payload: {data}")
			
			result = self._make_request("POST", endpoint, json_data=data)
			logger.info(f"📥 [LICENSE_SERVICE] API response: {result}")
			
			if result.get('success', False):
				# Lưu email nếu yêu cầu thành công
				self.save_last_email(email)
				logger.info("✅ Yêu cầu license thành công")
			else:
				logger.error(f"❌ Yêu cầu license thất bại: {result.get('message', 'Unknown error')}")
				
			return result
			
		except Exception as e:
			logger.error(f"💥 Lỗi khi gửi yêu cầu license mới: {str(e)}")
			return {
				'success': False,
				'message': f'Lỗi không xác định: {str(e)}'
			}
	
	def request_duplicate_inactive_license(self, email, hardware_id, cpu_id, mainboard_uuid):
		"""Gửi yêu cầu tạo license INACTIVE cho trường hợp thiết bị trùng (CPU + Mainboard đã đăng ký email khác).

		Server sẽ nhận tham số duplicate_mode='inactive' để tạo bản ghi license mới ở trạng thái 'inactive'
		dành riêng cho email mới, chờ admin xét duyệt (không tự động kích hoạt).
		"""
		try:
			logger.info("📨 [LICENSE_SERVICE] Yêu cầu duplicate INACTIVE license (imagen4)")
			brand_for_activation = _get_payments_brand()
			
			# Kiểm tra thông tin bắt buộc
			if not all([email, hardware_id, cpu_id, mainboard_uuid]):
				logger.error("❌ [LICENSE_SERVICE] Thiếu thông tin bắt buộc khi tạo duplicate inactive license")
				return {
					"success": False,
					"message": "Thiếu thông tin bắt buộc"
				}
			
			endpoint = "/api/license/activate.php"
			data = {
				"email": email,
				"hardware_id": hardware_id,
				"cpu_id": cpu_id,
				"mainboard_uuid": mainboard_uuid,
				"brand": brand_for_activation,
				"duplicate_mode": "inactive"
			}
			
			logger.info(f"🌐 [LICENSE_SERVICE] Gửi request duplicate INACTIVE đến {self.base_url}{endpoint}")
			result = self._make_request("POST", endpoint, json_data=data)
			
			if result.get("success", False):
				# Server sẽ trả về status='inactive', yêu cầu người dùng liên hệ admin
				self.save_last_email(email)
				logger.info("✅ [LICENSE_SERVICE] Tạo license INACTIVE (duplicate) thành công cho imagen4")
			else:
				logger.error(f"❌ [LICENSE_SERVICE] Tạo license INACTIVE thất bại: {result.get('message', 'Unknown error')}")
			
			return result
		
		except Exception as e:
			logger.error(f"💥 [LICENSE_SERVICE] Lỗi request_duplicate_inactive_license: {str(e)}")
			logger.exception("Full stack trace (duplicate_inactive_license):")
			return {
				"success": False,
				"message": f"Lỗi không xác định: {str(e)}"
			}
	
	def change_activation_email(self, old_email, new_email, hardware_id, cpu_id, mainboard_uuid):
		"""Thay đổi email cho yêu cầu kích hoạt imagen4"""
		try:
			logger.info(f"📧 Đang thay đổi email từ {old_email} thành {new_email}")
			logger.info(f"🖥️ Thông tin thiết bị: hardware_id={hardware_id}")
			brand_for_activation = _get_payments_brand()
			
			# Kiểm tra thông tin bắt buộc
			if not all([old_email, new_email, hardware_id, cpu_id, mainboard_uuid]):
				return {
					'success': False,
					'message': 'Thiếu thông tin bắt buộc để thay đổi email'
				}
			
			# Kiểm tra email format
			if not old_email or '@' not in old_email:
				return {
					'success': False,
					'message': 'Email cũ không hợp lệ'
				}
				
			if not new_email or '@' not in new_email:
				return {
					'success': False,
					'message': 'Email mới không hợp lệ'
				}
			
			# Gửi yêu cầu API
			endpoint = "/api/license/change_email.php"
			data = {
				"old_email": old_email.strip(),
				"new_email": new_email.strip(),
				"hardware_id": hardware_id,
				"cpu_id": cpu_id,
				"mainboard_uuid": mainboard_uuid,
				"brand": brand_for_activation
			}
			
			result = self._make_request("POST", endpoint, json_data=data)
			
			if result.get('success', False):
				# Lưu email mới nếu thay đổi thành công
				self.save_last_email(new_email)
				logger.info("✅ Thay đổi email thành công")
			else:
				logger.error(f"❌ Thay đổi email thất bại: {result.get('message', 'Unknown error')}")
				
			return result
				
		except Exception as e:
			logger.error(f"💥 Lỗi khi thay đổi email: {str(e)}")
			return {
				'success': False,
				'message': f'Lỗi không xác định: {str(e)}'
			}
	
	def verify_license(self, license_key, email, hardware_id, cpu_id, mainboard_uuid, current_version=None):
		"""Xác thực license với máy chủ cho imagen4"""
		endpoint = "/api/license/verify.php"
		brand_for_activation = _get_payments_brand()
		
		# Kiểm tra thông tin bắt buộc
		if not all([license_key, email, hardware_id, cpu_id, mainboard_uuid]):
			return {
				"success": False,
				"message": "Thiếu thông tin bắt buộc để kích hoạt"
			}
		
		data = {
			"license_key": license_key,
			"email": email,
			"hardware_id": hardware_id,
			"cpu_id": cpu_id,
			"mainboard_uuid": mainboard_uuid,
			"brand": brand_for_activation
		}
		
		# Thêm current_version nếu có
		if current_version:
			data["current_version"] = current_version
		
		logger.info(f"🔍 Đang xác thực license: {license_key[:20]}... cho brand {brand_for_activation}")
		result = self._make_request("POST", endpoint, json_data=data)
		
		if result.get('success', False):
			# Lưu email nếu kích hoạt thành công
			self.save_last_email(email)
			logger.info("✅ Xác thực license thành công")
		else:
			logger.error(f"❌ Xác thực license thất bại: {result.get('message', 'Unknown error')}")
			
		return result 
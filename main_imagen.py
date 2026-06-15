#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import logging
from pathlib import Path
import threading

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSettings, Qt, QTimer, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QPalette, QColor

from hardware_info_imagen import HardwareInfo
from token_client import TokenClient
from main_window_imagen import MainWindow
from activation_window_imagen import ActivationWindow
from splash_screen import SplashManager
# Tham số hóa brand cho whitelabel

#________________________   imagen4 + vinhson + toanthang   _________________________
# Ưu tiên đọc brand từ file resources/brand.txt (để build mỗi brand sinh file riêng); fallback ENV APP_BRAND; cuối cùng default 'imagen4'
from branding import get_brand_config

def get_resource_path(relative_path):
	"""
	Lấy đường dẫn tài nguyên, hỗ trợ cả khi đóng gói và chạy trực tiếp.
	- Windows (cx_Freeze/PyInstaller): resources nằm cạnh .exe -> dirname(sys.executable)
	- macOS (py2app): resources nằm trong MyApp.app/Contents/Resources
	  (sys.executable thường là MyApp.app/Contents/MacOS/<binary>)
	- Dev mode: dirname(__file__)
	"""
	import sys, os
	if getattr(sys, 'frozen', False):
		if sys.platform == 'darwin':
			base_path = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '..', 'Resources'))
		else:
			base_path = os.path.dirname(sys.executable)
	else:
		base_path = os.path.dirname(__file__)
	return os.path.join(base_path, relative_path)

brand_from_file = None
try:
	brand_file_path = get_resource_path('resources/brand.txt')
	if os.path.exists(brand_file_path):
		with open(brand_file_path, 'r', encoding='utf-8') as bf:
			brand_from_file = bf.read().strip()
except Exception:
	brand_from_file = None
BRAND_APP = brand_from_file or os.getenv("APP_BRAND", "imagen4")
BRAND_CONFIG = get_brand_config(BRAND_APP)
#________________________   imagen4 + vinhson + toanthang   _________________________
# Global logger
logger = logging.getLogger(__name__)

# =================================================================
# PHIÊN BẢN VÀ CẤU HÌNH
# =================================================================
VERSION = "1.3.5"
BRAND_ID = BRAND_CONFIG.get('license_brand', 'imagen4')
# KO SUA O DAY
APP_NAME = BRAND_CONFIG.get('ui_name', 'Imagen4 Generator')

# === Định nghĩa thư mục log mới ===
def get_log_directory():
	if sys.platform == 'win32':
		app_data = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Imagen4Tool')
	else:
		app_data = os.path.join(os.path.expanduser('~'), '.config', 'Imagen4Tool')
	if not os.path.exists(app_data):
		try:
			os.makedirs(app_data)
		except Exception:
			app_data = os.path.expanduser('~')
	return app_data

# === Đường dẫn file log mới ===
LOG_FILENAME = 'imagen4_client.log'
LOG_FILE_PATH = os.path.join(get_log_directory(), LOG_FILENAME)

# =================================================================
# SETUP LOGGING
# =================================================================

# Thiết lập log level DEBUG - hiển thị WARNING để giảm noise CRITICAL
LOG_LEVEL = logging.CRITICAL  # Giảm logging để trải nghiệm mượt mà hơn

def setup_logging():
	"""Setup logging với định dạng đẹp và level hợp lý"""
	try:
		# Clear existing handlers
		root_logger = logging.getLogger()
		for handler in root_logger.handlers[:]:
			root_logger.removeHandler(handler)
		
		# Configure logging với force flush
		logging.basicConfig(
			level=LOG_LEVEL,
			format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
			datefmt='%H:%M:%S',
			force=True,  # Force reconfigure logging
			stream=sys.stdout  # Ensure output to stdout
		)
		
		# Thêm file handler để ghi log ra file
		file_handler = logging.FileHandler(LOG_FILE_PATH, mode='w', encoding='utf-8')
		file_handler.setLevel(LOG_LEVEL)
		file_handler.setFormatter(logging.Formatter(
			'%(asctime)s - %(name)s - %(levelname)s - %(message)s',
			datefmt='%H:%M:%S'
		))
		root_logger.addHandler(file_handler)
		
		# Force flush all handlers
		for handler in root_logger.handlers:
			handler.flush()
		
		# Thiết lập level cho các module cụ thể
		logging.getLogger('hardware_info').setLevel(LOG_LEVEL)
		logging.getLogger('token_client').setLevel(LOG_LEVEL)
		logging.getLogger('main').setLevel(LOG_LEVEL)
		
		# Chi tiết cho activation và verification
		logging.getLogger('activation').setLevel(LOG_LEVEL)
		logging.getLogger('verification').setLevel(LOG_LEVEL)
		logging.getLogger('activation_window').setLevel(LOG_LEVEL)  # Thêm module này
		
		# Giảm noise từ network requests
		logging.getLogger('urllib3').setLevel(logging.WARNING)
		logging.getLogger('requests').setLevel(logging.WARNING)
		
		logger.info("🚀 Imagen4 Generator starting...")
		
		# Force flush
		for handler in root_logger.handlers:
			handler.flush()
		
	except Exception as e:
		print(f"Lỗi setup logging: {e}")

def debug_qsettings():
	"""Debug QSettings - tắt để giảm noise"""
	pass

# =================================================================
# SINGLE INSTANCE
# =================================================================
class SingleInstanceListener(QObject):
	messageReceived = Signal()
	def __init__(self, main_app):
		super().__init__()
		self.main_app = main_app

	def handle_new_connection(self):
		socket = self.main_app.local_server.nextPendingConnection()
		if socket and socket.waitForReadyRead(1000):
			message = socket.readAll().data().decode('utf-8')
			if message == 'SHOW':
				# Hiện cửa sổ chính hoặc activation
				if hasattr(self.main_app, 'main_window') and self.main_app.main_window:
					self.main_app.main_window.showNormal()
					self.main_app.main_window.activateWindow()
					self.main_app.main_window.raise_()
				elif hasattr(self.main_app, 'activation_window') and self.main_app.activation_window:
					self.main_app.activation_window.showNormal()
					self.main_app.activation_window.activateWindow()
					self.main_app.activation_window.raise_()
		socket.close()

class Imagen4App:
	def __init__(self):
		self.start_time = time.time()
		setup_logging()
		self.app = QApplication(sys.argv)
		self.app.setApplicationName(BRAND_CONFIG.get('qsettings_app', 'Imagen4 Client'))
		self.app.setOrganizationName(BRAND_CONFIG.get('qsettings_org', 'Imagen4'))
		self.app.setOrganizationDomain("")
		self.app.setApplicationVersion("3.12.6150.1013")

		# Ép style hệ thống về Fusion để đồng nhất giao diện
		self.app.setStyle('Fusion')
		
		# Set application icon cho toàn bộ ứng dụng
		# Thử load application icon
		default_icons = [
			"resources/icons/app_icon.png",
			"resources/icons/app_icon.ico"
		]
		app_icon_paths = list(BRAND_CONFIG.get('icons', [])) + default_icons
		
		app_icon_loaded = False
		for icon_path in app_icon_paths:
			full_path = get_resource_path(icon_path)
			if os.path.exists(full_path):
				from PySide6.QtGui import QIcon
				app_icon = QIcon(full_path)
				if not app_icon.isNull():
					self.app.setWindowIcon(app_icon)
					logger.info(f"✅ Set application icon: {icon_path}")
					app_icon_loaded = True
					break
		
		if not app_icon_loaded:
			logger.warning("⚠️ No application icon found, using system default")

		# === Nạp stylesheet QSS cho toàn bộ app ===
		qss_path = get_resource_path('resources/style.qss')
		try:
			with open(qss_path, 'r', encoding='utf-8') as f:
				self.app.setStyleSheet(f.read())
			logger.info(f"Đã nạp stylesheet từ {qss_path}")
		except Exception as e:
			logger.error(f"Không thể nạp stylesheet: {e}")
			# Fallback: thử đường dẫn cũ
			try:
				fallback_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
				with open(fallback_path, 'r', encoding='utf-8') as f:
					self.app.setStyleSheet(f.read())
				logger.info(f"Đã nạp stylesheet từ fallback path: {fallback_path}")
			except Exception as e2:
				logger.error(f"Cả 2 đường dẫn đều thất bại: {e2}")
		# Ép palette sáng để không bị Windows dark mode override
		palette = QPalette()
		palette.setColor(QPalette.Window, QColor("#f7f8fa"))
		palette.setColor(QPalette.WindowText, QColor("#23272f"))
		palette.setColor(QPalette.Base, QColor("#ffffff"))
		palette.setColor(QPalette.Text, QColor("#181a1b"))
		palette.setColor(QPalette.Button, QColor("#e3eaf2"))
		palette.setColor(QPalette.ButtonText, QColor("#23272f"))
		self.app.setPalette(palette)

		# --- SINGLE INSTANCE LOGIC ---
		self.app_id = "imagen4_generator_single_instance"
		self.socket = QLocalSocket()
		self.socket.connectToServer(self.app_id)
		if self.socket.waitForConnected(500):
			self.socket.write(b"SHOW")
			self.socket.flush()
			self.socket.close()
			sys.exit(0)
		self.local_server = QLocalServer()
		QLocalServer.removeServer(self.app_id)
		self.local_server.listen(self.app_id)
		self.listener = SingleInstanceListener(self)
		self.local_server.newConnection.connect(self.listener.handle_new_connection)
		# --- END SINGLE INSTANCE ---
			
		# Khởi tạo splash screen với version
		self.splash_manager = SplashManager(VERSION, BRAND_CONFIG)
		self.splash = self.splash_manager.show_splash()
			
		# Simulate loading và cập nhật splash
		self.splash_manager.update_progress(10, "Đang khởi tạo...")
		QApplication.processEvents()
		
		# Sử dụng QSettings mặc định
		self.settings = QSettings()
		self.splash_manager.update_progress(20, "Đang tải cấu hình...")
		QApplication.processEvents()
		
		# Khởi tạo components
		self.token_client = TokenClient()
		self.hardware_info = None
		self.license_key = None
		
		# Cờ để thoát ngay không hỏi lại khi cập nhật
		self.force_quit_for_update = False
		
		# Import license service
		from services.license_service_imagen import LicenseService
		self.license_service = LicenseService()
		
		self.splash_manager.update_progress(40, "Đang kiểm tra hệ thống...")
		QApplication.processEvents()
		
		# Bắt đầu luồng chính
		self.start_main_flow()
	
	def run(self):
		"""Chạy ứng dụng"""
		return self.app.exec()
	
	def start_main_flow(self):
		"""Luồng chính với splash screen"""
		
		# Thu thập hardware info
		self.splash_manager.update_progress(50, "Đang thu thập thông tin hệ thống...")
		QApplication.processEvents()
		
		try:
			self.hardware_info = HardwareInfo(brand_id=BRAND_ID)
			hw_info = self.hardware_info.get_hardware_info()
			logger.info(f"🔧 Hardware ID: {hw_info['hardware_id']}")
			
			if hw_info.get('from_old_app'):
				logger.info("✅ Using hardware configuration from old app")
			
		except Exception as e:
			self.splash_manager.close_splash()
			QMessageBox.critical(None, "Lỗi", f"Không thể thu thập thông tin hệ thống: {e}")
			return
		
		# Kiểm tra license
		self.splash_manager.update_progress(70, "Đang kiểm tra license...")
		QApplication.processEvents()
		
		self.license_key = self.settings.value("license/key", None)
		
		if not self.license_key:
			# Chưa có license → hiển thị activation
			self.splash_manager.update_progress(90, "Đang khởi tạo...")
			QApplication.processEvents()
			
			# Delay nhẹ để user thấy splash đẹp
			time.sleep(0.3)
			
			# Đóng splash trước khi hiển thị activation window
			self.splash_manager.close_splash()
			
			# Delay để animation close hoàn tất
			QTimer.singleShot(500, self.show_activation_window)
		else:
			# Có license → verify
			self.splash_manager.update_progress(80, "Đang xác thực license...")
			QApplication.processEvents()
			
			if self.verify_license():
				self.splash_manager.update_progress(95, "Đang khởi động ứng dụng...")
				QApplication.processEvents()
				
				# Delay nhẹ để hiển thị 100%
				time.sleep(0.3)
				self.splash_manager.update_progress(100, "Hoàn thành!")
				QApplication.processEvents()
				time.sleep(0.2)
				
				self.splash_manager.close_splash()
				
				# Delay để animation close hoàn tất trước khi hiển thị main window
				QTimer.singleShot(500, self.show_main_window)
			else:
				# License không hợp lệ → xóa và activation
				self.settings.remove("license/key")
				self.splash_manager.update_progress(90, "License không hợp lệ...")
				QApplication.processEvents()
				time.sleep(0.5)
				
				self.splash_manager.close_splash()
				
				# Hiển thị thông báo sau khi splash đóng
				QTimer.singleShot(500, lambda: [
					QMessageBox.warning(None, "License không hợp lệ", 
					                  "License hiện tại không hợp lệ. Vui lòng kích hoạt lại."),
					self.show_activation_window()
				])
	
	def verify_license(self):
		"""Xác thực license với server"""
		try:
			# Thu thập thông tin phần cứng cho verification
			hw_info = self.hardware_info.get_hardware_info()
			
			# Gọi token client để verify
			result = self.token_client.verify_license(
				license_key=self.license_key,
				hardware_id=hw_info['hardware_id'],
				cpu_id=hw_info['cpu_id'], 
				mainboard_uuid=hw_info['mainboard_uuid'],
				brand=BRAND_APP,
				current_version=VERSION
			)
			# Bổ sung: nếu có update_available thì lưu lại để hiển thị sau
			self.update_info = None
			if result.get('success', False):
				if result.get('update_available', False):
					self.update_info = {
						'latest_version': result.get('latest_version', ''),
						'download_url': result.get('download_url', ''),
						'update_message': result.get('update_message', 'Có phiên bản mới!')
					}
				logger.info("✅ License verification thành công")
				return True
			else:
				error_msg = result.get('message', result.get('error', 'Unknown error'))
				logger.error(f"❌ License verification thất bại: {error_msg}")
				return False
		except Exception as e:
			logger.error(f"💥 Lỗi khi verify license: {str(e)}")
			return False
	
	def show_activation_window(self):
		"""Hiển thị cửa sổ activation"""
		try:
			logger.info("🚪 Creating ActivationWindow...")
			self.activation_window = ActivationWindow(self.license_service, self.hardware_info)
			self.activation_window.license_activated.connect(self.on_license_activated)
			
			logger.info("🚪 Showing activation window...")
			self.activation_window.show()
				
		except Exception as e:
			logger.error(f"💥 Exception in show_activation_window: {str(e)}")
			logger.exception("Full stack trace:")
			sys.exit(1)
	
	def on_license_activated(self, license_key):
		"""Xử lý khi license được kích hoạt"""
		try:
			logger.info("🎯 License activation successful")
			self.license_key = license_key
			# Lưu license và hiển thị main window, KHÔNG gọi lại verify_license ở đây
			self.settings.setValue("license/key", license_key)
			self.settings.sync()
			logger.info("✅ License successfully saved and activated")
			# Close activation window
			if hasattr(self, 'activation_window') and self.activation_window:
				self.activation_window.close()
			self.show_main_window()
		except Exception as e:
			logger.error(f"💥 Exception in on_license_activated: {str(e)}")
			logger.exception("Full stack trace:")
			sys.exit(1)
	
	def show_main_window(self):
		"""Hiển thị main window và đặt cờ kiểm tra tài khoản song song (giống chương trình chính)"""
		self.main_window = MainWindow()
		# Truyền app_ref để MainWindow có thể kiểm tra cờ force_quit_for_update
		self.main_window.app_ref = self
		self.main_window.show()

		# Truyền branding xuống Results panel (Zalo/link/icon) nếu có
		try:
			if hasattr(self.main_window, 'results_panel') and hasattr(self.main_window.results_panel, 'set_branding'):
				self.main_window.results_panel.set_branding(BRAND_CONFIG)
		except Exception as _:
			pass

		# Hiển thị thông báo cập nhật nếu có
		if hasattr(self, 'update_info') and self.update_info:
			from PySide6.QtCore import QTimer
			QTimer.singleShot(1000, self._show_update_notification)

		# Đặt cờ cần kiểm tra tài khoản, main thread sẽ xử lý
		def set_account_refresh_flag():
			try:
				if hasattr(self.main_window, 'need_account_refresh'):
					self.main_window.need_account_refresh = True
					logger.info("[BG] Đã đặt cờ need_account_refresh = True cho MainWindow")
				else:
					# Nếu chưa có thuộc tính, tạo luôn
					self.main_window.need_account_refresh = True
					logger.info("[BG] Đã tạo và đặt cờ need_account_refresh = True cho MainWindow")
			except Exception as e:
				logger.error(f"Lỗi khi đặt cờ need_account_refresh: {str(e)}")
		threading.Thread(target=set_account_refresh_flag, daemon=True).start()

		# Đảm bảo MainWindow có QTimer kiểm tra cờ và gọi cập nhật tài khoản
		if not hasattr(self.main_window, '_account_refresh_timer'):
			from PySide6.QtCore import QTimer
			def check_and_refresh_account():
				try:
					if getattr(self.main_window, 'need_account_refresh', False):
						self.main_window.need_account_refresh = False
						if hasattr(self, 'license_key') and self.license_key:
							def fetch_and_update():
								from services.api_imagen_service import ApiImagenService
								api_service = ApiImagenService(self.license_key)
								try:
									account_info = api_service.get_account_info()
									def update_ui():
										if hasattr(self.main_window, 'refresh_account_info'):
											self.main_window.refresh_account_info(account_info)
										else:
											logger.info(f"[UI] Account info: {account_info}")
									QTimer.singleShot(0, update_ui)
								except Exception as e:
									def log_error():
										logger.error(f"Lỗi khi lấy account info: {str(e)}")
									QTimer.singleShot(0, log_error)
							threading.Thread(target=fetch_and_update, daemon=True).start()
				except Exception as e:
					logger.error(f"Lỗi khi kiểm tra/cập nhật tài khoản: {str(e)}")
			self.main_window._account_refresh_timer = QTimer(self.main_window)
			self.main_window._account_refresh_timer.timeout.connect(check_and_refresh_account)
			self.main_window._account_refresh_timer.start(200)

		elapsed = time.time() - self.start_time
		logging.info(f"Ứng dụng khởi động trong {elapsed:.2f} giây")

	def _show_update_notification(self):
		"""Hiển thị thông báo cập nhật phiên bản mới và hỏi người dùng có muốn tự động cập nhật"""
		try:
			if not hasattr(self, 'update_info') or not self.update_info:
				return
			latest_version = self.update_info.get('latest_version', '')
			download_url = self.update_info.get('download_url', '')
			# Fallback download_url theo brand nếu server không trả về FULL link (rỗng hoặc chỉ chứa version)
			is_full_url = isinstance(download_url, str) and download_url.lower().startswith(('http://','https://'))
			if not is_full_url:
				try:
					base = BRAND_CONFIG.get('download_base_url', '') if isinstance(BRAND_CONFIG, dict) else ''
					fname_tpl = BRAND_CONFIG.get('download_filename_template', '') if isinstance(BRAND_CONFIG, dict) else ''
					ver = latest_version or download_url or ''
					if base and fname_tpl and ver:
						# Đảm bảo không có dấu '//' dư
						base_norm = base.rstrip('/')
						download_url = f"{base_norm}/{fname_tpl.format(version=ver)}"
				except Exception:
					pass
			update_message = self.update_info.get('update_message', 'Có phiên bản mới!')
			message_html = f"""
			<div style=\"font-size: 12pt;\">
				<h3 style=\"color: #2196F3;\">🎉 Có phiên bản mới! {latest_version}</h3>
				<p>{update_message}</p>
				<p style=\"font-size: 11pt; color: #666;\">
					Bạn có muốn tự động tải và cài đặt phiên bản mới ngay bây giờ?
				</p>
			</div>
			"""
			from PySide6.QtWidgets import QMessageBox
			from PySide6.QtCore import Qt
			msg_box = QMessageBox(self.main_window)
			msg_box.setWindowTitle("Thông báo cập nhật")
			msg_box.setTextFormat(Qt.TextFormat.RichText)
			msg_box.setText(message_html)
			msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
			msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
			msg_box.setIcon(QMessageBox.Icon.Information)
			# Thêm nút "Tải thủ công" nếu có thể
			manual_button = msg_box.addButton("Tải thủ công", QMessageBox.ButtonRole.AcceptRole)
			result = msg_box.exec()
			
			if result == QMessageBox.StandardButton.Yes:
				# Người dùng chọn tự động cập nhật
				self._launch_auto_update(download_url, latest_version)
			elif msg_box.clickedButton() == manual_button:
				# Người dùng chọn tải thủ công - mở link trong trình duyệt
				import webbrowser
				try:
					webbrowser.open(download_url)
					logger.info(f"Đã mở link download trong trình duyệt: {download_url}")
				except Exception as e:
					logger.error(f"Lỗi khi mở trình duyệt: {str(e)}")
					# Fallback: copy link vào clipboard
					try:
						from PySide6.QtGui import QGuiApplication
						clipboard = QGuiApplication.clipboard()
						clipboard.setText(download_url)
						QMessageBox.information(self.main_window, "Link đã được sao chép", 
							f"Link tải về đã được sao chép vào clipboard:\n{download_url}")
					except Exception:
						pass
			logger.info(f"Đã hiển thị thông báo cập nhật cho version {latest_version}")
		except Exception as e:
			logger.error(f"Lỗi khi hiển thị thông báo cập nhật: {str(e)}")
	
	def _launch_auto_update(self, download_url: str, version: str):
		"""Khởi chạy updater tự động"""
		try:
			import subprocess
			import os
			import sys
			import tempfile
			import json
			import time
			
			# Đánh dấu thoát để cập nhật (không hỏi lại)
			self.force_quit_for_update = True
			
			# Tìm đường dẫn updater
			def get_resource_path(relative_path: str) -> str:
				if getattr(sys, 'frozen', False):
					return os.path.join(os.path.dirname(sys.executable), relative_path)
				return os.path.join(os.path.dirname(__file__), relative_path)
			
			updater_exe = get_resource_path('UpdaterImagen.exe')
			if not os.path.exists(updater_exe):
				# Thử tìm trong thư mục hiện tại
				updater_exe = os.path.join(os.path.dirname(sys.executable), 'UpdaterImagen.exe')
			
			if not os.path.exists(updater_exe):
				logger.error(f"Không tìm thấy UpdaterImagen.exe tại {updater_exe}")
				QMessageBox.warning(self.main_window, "Lỗi", 
					"Không tìm thấy công cụ cập nhật tự động.\nVui lòng tải thủ công từ link đã cung cấp.")
				self.force_quit_for_update = False
				return
			
			# Xác định main exe name theo brand
			if getattr(sys, 'frozen', False):
				install_dir = os.path.dirname(sys.executable)
				main_exe_name = os.path.basename(sys.executable)
				process_to_wait = os.path.basename(sys.executable)
			else:
				install_dir = os.path.dirname(__file__)
				if BRAND_APP == 'imagen4':
					main_exe_name = 'chichbong_generator.exe'
				else:
					main_exe_name = f"{BRAND_APP}_generator.exe"
				process_to_wait = main_exe_name
			
			# Ẩn cửa sổ chính và trì hoãn 1s trước khi chạy updater (tránh giật)
			try:
				if self.main_window:
					self.main_window.hide()
			except Exception:
				pass
			
			def _start_updater():
				try:
					# Khởi chạy updater dạng GUI để hiển thị tiến trình
					if updater_exe.lower().endswith('.exe'):
						subprocess.Popen([
							updater_exe,
							'--download-url', download_url,
							'--install-dir', install_dir,
							'--main-exe', main_exe_name,
							'--process-to-wait', process_to_wait,
							'--version', version
						], close_fds=True)
					else:
						# Dev mode: chạy bằng pythonw.exe để không mở console nhưng vẫn hiển thị UI
						import shutil
						py_exec = sys.executable
						if os.name == 'nt':
							try:
								if py_exec.lower().endswith('python.exe'):
									cand = py_exec[:-4] + 'w.exe'
									if os.path.exists(cand):
										py_exec = cand
								else:
									found = shutil.which('pythonw.exe')
									if found:
										py_exec = found
							except Exception:
								pass
						subprocess.Popen([
							py_exec,
							updater_exe,
							'--download-url', download_url,
							'--install-dir', install_dir,
							'--main-exe', main_exe_name,
							'--process-to-wait', process_to_wait,
							'--version', version
						], close_fds=True)
				except Exception as e:
					logger.error(f"Failed to start updater: {e}")
					QMessageBox.warning(self.main_window, "Cập nhật", "Không thể khởi động chương trình cập nhật.")
					self.force_quit_for_update = False
					return
				# Kill hẳn tiến trình để không bật bất kỳ hộp thoại/console nào khi thoát
				try:
					os._exit(0)
				except Exception:
					self.app.quit()
			
			# Đợi 1 giây rồi chạy updater
			from PySide6.QtCore import QTimer
			QTimer.singleShot(1000, _start_updater)
			
		except Exception as e:
			logger.error(f"Lỗi khi khởi chạy auto update: {str(e)}")
			QMessageBox.warning(self.main_window, "Lỗi", 
				f"Không thể khởi chạy cập nhật tự động.\nLỗi: {str(e)}\nVui lòng tải thủ công từ link đã cung cấp.")
			self.force_quit_for_update = False

# =================================================================
# ENTRY POINT
# =================================================================
def main():
	"""Hàm main - khởi động Imagen4 Generator với splash screen"""
	
	# Setup logging trước tiên
	setup_logging()
	
	# Khởi tạo QApplication
	app = QApplication(sys.argv)
	app.setApplicationName(BRAND_CONFIG.get('qsettings_app', 'Imagen4 Client'))
	app.setOrganizationName(BRAND_CONFIG.get('qsettings_org', 'Imagen4'))
	app.setOrganizationDomain("")
	app.setApplicationVersion("3.12.6150.1013")

	# Ép style hệ thống về Fusion để đồng nhất giao diện
	app.setStyle('Fusion')
	
	# Set application icon
	# Thử load application icon
	default_icons = [
		"resources/icons/app_icon.png",
		"resources/icons/app_icon.ico"
	]
	app_icon_paths = list(BRAND_CONFIG.get('icons', [])) + default_icons
	
	app_icon_loaded = False
	for icon_path in app_icon_paths:
		full_path = get_resource_path(icon_path)
		if os.path.exists(full_path):
			from PySide6.QtGui import QIcon
			app_icon = QIcon(full_path)
			if not app_icon.isNull():
				app.setWindowIcon(app_icon)
				print(f"✅ Set application icon: {icon_path}")
				app_icon_loaded = True
				break
	
	if not app_icon_loaded:
		print("⚠️ No application icon found, using system default")

	# Khởi tạo hardware info để kiểm tra tương thích
	try:
		hardware_info = HardwareInfo(brand_id=BRAND_CONFIG.get('license_brand', 'imagen4'))
		hw_info = hardware_info.get_hardware_info()
		
	except Exception as e:
		print(f"Lỗi hardware info: {e}")
		return
	
	# Kiểm tra license
	settings = QSettings(BRAND_CONFIG.get('qsettings_org', 'Imagen4'), BRAND_CONFIG.get('qsettings_app', 'Imagen4 Client'))
	license_key = settings.value("license/key", None)
	
	if license_key:
		# Xác thực license với server
		token_client = TokenClient()
		
		result = token_client.verify_license(
			license_key=license_key,
			hardware_id=hw_info['hardware_id'],
			cpu_id=hw_info['cpu_id'],
			mainboard_uuid=hw_info['mainboard_uuid'],
			brand=BRAND_CONFIG.get('license_brand', 'imagen4'),
			current_version=VERSION
		)
		
		if result.get('success', False):
			# License verification thành công - hiển thị splash ngắn với version
			splash_manager = SplashManager(VERSION, BRAND_CONFIG)
			splash = splash_manager.show_splash()
			
			# Quick splash cho main window
			for i in range(0, 101, 20):
				splash_manager.update_progress(i, "Đang khởi động...")
				QApplication.processEvents()
				time.sleep(0.1)
			
			splash_manager.close_splash()
			
			# Delay để splash animation hoàn tất
			def show_main():
				window = MainWindow()
				window.show()
				
			QTimer.singleShot(500, show_main)
			sys.exit(app.exec())
			
		else:
			# License verification thất bại - xóa license và hiển thị activation
			settings.remove("license/key")
			settings.sync()
			
			from services.license_service_imagen import LicenseService
			license_service = LicenseService()
			activation_window = ActivationWindow(license_service, hardware_info)
			
			def on_license_activated(license_key):
				activation_window.close()
				window = MainWindow()
				window.show()
			
			activation_window.license_activated.connect(on_license_activated)
			activation_window.show()
			
			sys.exit(app.exec())
			
	else:
		# Không có license - hiển thị activation window
		from services.license_service_imagen import LicenseService
		license_service = LicenseService()
		activation_window = ActivationWindow(license_service, hardware_info)
		
		def on_license_activated(license_key):
			activation_window.close()
			window = MainWindow()
			window.show()
		
		activation_window.license_activated.connect(on_license_activated)
		activation_window.show()
		
		sys.exit(app.exec())

if __name__ == "__main__":
	# Sử dụng phiên bản với splash screen đẹp
	app = Imagen4App()
	sys.exit(app.run()) 
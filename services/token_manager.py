import logging
import json
from datetime import datetime, timedelta
from PySide6.QtCore import QSettings
from services.api_imagen_service import ApiImagenService

class TokenManager:
    CACHE_KEY = "imagen4_tokens_cache"
    CACHE_EXPIRY_KEY = "imagen4_tokens_cache_expiry"
    CACHE_DURATION = 540  # 9 minutes in seconds

    def __init__(self, license_key):
        self.license_key = license_key
        self.settings = QSettings("ElevenLabs", "ElevenLabs TTS Client")
        self.api_service = ApiImagenService(license_key)
        self._cached_tokens = None
        self._cache_expiry = None
        self._load_cache()

    def _load_cache(self):
        tokens_json = self.settings.value(self.CACHE_KEY)
        expiry_str = self.settings.value(self.CACHE_EXPIRY_KEY)
        if tokens_json and expiry_str:
            try:
                self._cached_tokens = json.loads(tokens_json)
                self._cache_expiry = datetime.fromisoformat(expiry_str)
            except Exception as e:
                logging.warning(f"[TokenManager] Lỗi load cache: {e}")
                self._cached_tokens = None
                self._cache_expiry = None
        else:
            self._cached_tokens = None
            self._cache_expiry = None

    def _save_cache(self, tokens):
        # Đảm bảo mỗi token đều có trường gemini_apikey (nếu không có thì None)
        for t in tokens:
            if 'gemini_apikey' not in t:
                t['gemini_apikey'] = None
        self._cached_tokens = tokens
        self._cache_expiry = datetime.now() + timedelta(seconds=self.CACHE_DURATION)
        self.settings.setValue(self.CACHE_KEY, json.dumps(tokens))
        self.settings.setValue(self.CACHE_EXPIRY_KEY, self._cache_expiry.isoformat())
        self.settings.sync()

    def clear_cache(self):
        self._cached_tokens = None
        self._cache_expiry = None
        self.settings.remove(self.CACHE_KEY)
        self.settings.remove(self.CACHE_EXPIRY_KEY)
        self.settings.sync()

    def is_token_valid(self):
        if self._cached_tokens and self._cache_expiry:
            return datetime.now() < self._cache_expiry
        return False

    def get_tokens(self, force_refresh=False, limit=5):
        """Lấy tokens, ưu tiên cache nếu còn hạn, nếu force_refresh thì luôn gọi API mới"""
        if not force_refresh and self.is_token_valid():
            logging.info(f"[TokenManager] Dùng tokens từ cache. Hạn cache: {self._cache_expiry}, Hiện tại: {datetime.now()}")
            if self._cached_tokens:
                for idx, t in enumerate(self._cached_tokens):
                    logging.info(f"[TokenManager] [cache] Token {idx}: {t.get('token','')[:16]}..., proxy: {t.get('proxy','')}, gemini_apikey: {t.get('gemini_apikey','')}")
            return self._cached_tokens
        # Gọi API lấy mới
        tokens = self.api_service.get_imagen4_tokens_via_license(limit=limit)
        if tokens:
            # Đảm bảo mỗi token đều có trường gemini_apikey (nếu không có thì None)
            for t in tokens:
                if 'gemini_apikey' not in t:
                    t['gemini_apikey'] = None
            logging.info(f"[TokenManager] Nhận {len(tokens)} tokens mới từ API:")
            for idx, t in enumerate(tokens):
                logging.info(f"[TokenManager] [api] Token {idx}: {t.get('token','')[:16]}..., proxy: {t.get('proxy','')}, gemini_apikey: {t.get('gemini_apikey','')}")
            self._save_cache(tokens)
            logging.info(f"[TokenManager] Đã refresh và cache {len(tokens)} tokens mới")
            return tokens
        else:
            logging.warning("[TokenManager] Không lấy được tokens mới, dùng cache cũ nếu có")
            return self._cached_tokens or []

    def force_refresh_tokens(self, limit=5):
        """Luôn gọi API lấy tokens mới và cập nhật cache"""
        return self.get_tokens(force_refresh=True, limit=limit) 
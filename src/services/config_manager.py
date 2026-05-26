import json
import os

class ConfigManager:
    _instance = None
    DEFAULT_CONFIG = {
        "udp_port": 39169,
        "api_base_url": "https://rest.xxt.cn",
        "time_window_start": "16:30",
        "time_window_end": "18:30",
        "broadcast_count": 3,
        "deduplication_interval_seconds": 300,
        "mqtt_enabled": True,
        "mqtt_host": "111.6.173.61",
        "mqtt_port": 1883,
        "mqtt_heartbeat_interval_seconds": 60,
        "mqtt_telemetry_topic": "v1/devices/me/telemetry",
        "mqtt_rpc_request_topic": "v1/devices/me/rpc/request/+",
        "mqtt_rpc_response_topic_template": "v1/devices/me/rpc/response/{request_id}"
    }

    def __new__(cls, config_path=None):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path=None):
        if self._initialized:
            return
        
        if config_path is None:
            from ..utils.path_utils import get_app_root
            base_dir = get_app_root()
            self.config_path = os.path.join(base_dir, "config", "settings.json")
        else:
            self.config_path = config_path

        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()
        self._initialized = True

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
            except Exception as e:
                print(f"[Config] Error loading config: {e}")

    def get(self, key, default=None):
        # Only use DEFAULT_CONFIG if default argument is None
        # But wait, python default arg IS None if not provided.
        # Logic: 
        # 1. Check user config
        # 2. Check default argument (if not None)
        # 3. Check DEFAULT_CONFIG
        
        if key in self.config:
            return self.config[key]
            
        if default is not None:
             return default
             
        return self.DEFAULT_CONFIG.get(key)

    def set(self, key, value):
        self.config[key] = value

    def save(self):
        self.save_config()

    def save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

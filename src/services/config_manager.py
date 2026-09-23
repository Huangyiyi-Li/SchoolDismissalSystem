import json
import os

class ConfigManager:
    _instance = None
    DEFAULT_CONFIG = {
        "udp_port": 39169,
        "api_base_url": "https://rest.xxt.cn",
        "time_window_start": "16:30",
        "time_window_end": "18:30",
        "tts_rate": 0,
        "tts_repeat_count": 3,
        "tts_repeat_interval_seconds": 0,
        "deduplication_interval_seconds": 300,
        "mqtt_enabled": True,
        "mqtt_host": "111.6.173.61",
        "mqtt_port": 1883,
        "mqtt_heartbeat_interval_seconds": 60,
        "mqtt_reconnect_interval_seconds": 60,
        "mqtt_telemetry_topic": "v1/devices/me/telemetry",
        "mqtt_rpc_request_topic": "v1/devices/me/rpc/request/+",
        "mqtt_rpc_response_topic_template": "v1/devices/me/rpc/response/{request_id}",
        "led_enabled": False,
        "led_output_type": "led",
        "led_monitor": "",
        "led_title_position": "left",
        "led_controller_ip": "192.168.100.1",
        "led_controller_port": 5005,
        "led_width": 1024,
        "led_height": 96,
        "led_color_mode": "single",
        "led_page_seconds": 5,
        "led_grades_per_page": 2,
        "led_layout_regions": 1,
        "led_grade_filter_mode": "all",
        "led_visible_grades": [],
        "led_grade_pages": [],
        "led_club_rows_per_group": 4,
        "led_club_groups_per_page": 5,
        "led_dismissed_delay_seconds": 5,
        "led_show_title": True,
        "led_school_title": "数智家校\n放学系统",
        "led_title_font_size": 0,
        "led_header_font_size": 0,
        "led_cell_font_size": 0,
        "led_status_labels": None,
        "led_status_colors": None,
        "led_table_scale_percent": 100,
        "led_title_scale_percent": 100,
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


# Device settings are independent even when several screens share one plan.
LED_DEVICE_KEYS = ('led_controller_ip', 'led_controller_port', 'led_width',
                   'led_height', 'led_color_mode', 'led_output_type', 'led_monitor',
                   'led_grade_filter_mode', 'led_visible_grades', 'led_grade_pages')
LED_PLAN_KEYS = tuple(key for key in ConfigManager.DEFAULT_CONFIG
                      if key.startswith('led_') and
                      (key not in LED_DEVICE_KEYS or key in ('led_grade_filter_mode', 'led_visible_grades'))
                      and key not in ('led_enabled', 'led_dismissed_delay_seconds'))


def load_led_setup(config):
    """Return an isolated editing snapshot; legacy migration never changes the caller."""
    from copy import deepcopy
    screens = config.get('led_screens')
    if screens is not None:
        return deepcopy(screens), deepcopy(config.get('led_display_plans', []))
    def settings(keys):
        return {key: deepcopy(config.get(key, ConfigManager.DEFAULT_CONFIG[key])) for key in keys}
    return ([{'id': 'default', 'name': '默认屏幕', 'enabled': bool(config.get('led_enabled', False)),
              'plan_id': 'default', 'settings': settings(LED_DEVICE_KEYS)}],
            [{'id': 'default', 'name': '默认显示方案', 'settings': settings(LED_PLAN_KEYS)}])


def validate_led_setup(screens, plans):
    import ipaddress
    import re
    from .led_dimensions import validate_led_dimensions
    ids, targets = set(), set()
    plan_ids = set()
    for plan in plans:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(plan.get('id', ''))) or plan['id'] in plan_ids:
            raise ValueError('显示方案标识无效或重复')
        plan_ids.add(plan['id'])
        if not str(plan.get('name', '')).strip():
            raise ValueError('请填写显示方案名称')
        values = {**ConfigManager.DEFAULT_CONFIG, **plan.get('settings', {})}
        if values['led_title_position'] not in ('left', 'top'):
            raise ValueError('标题位置必须为左侧或顶部')
        if values['led_grade_filter_mode'] not in ('all', 'selected'):
            raise ValueError('显示年级模式无效')
        if values['led_grade_filter_mode'] == 'selected' and not values['led_visible_grades']:
            raise ValueError('指定显示年级时，至少选择一个年级')
        for key in ('led_page_seconds',):
            if not 1 <= float(values[key]) <= 300:
                raise ValueError('翻页间隔必须为 1-300 秒')
        for key in ('led_grades_per_page', 'led_layout_regions', 'led_club_rows_per_group', 'led_club_groups_per_page'):
            if not 1 <= int(values[key]) <= 6:
                raise ValueError('布局行数和分区数必须为 1-6')
        for key in ('led_title_font_size', 'led_header_font_size', 'led_cell_font_size'):
            if not 0 <= int(values[key]) <= 64:
                raise ValueError('字号必须为自动或 1-64 像素')
        for key in ('led_table_scale_percent', 'led_title_scale_percent'):
            if not 50 <= int(values[key]) <= 100:
                raise ValueError('文字大小调节必须在 50%-100% 之间')
        labels = values['led_status_labels']
        colors = values['led_status_colors']
        states = {'未放学', '放学中', '已放学'}
        if labels is not None and (not isinstance(labels, dict) or set(labels) != states
                                   or any(not isinstance(value, str) or '\n' in value for value in labels.values())):
            raise ValueError('状态显示内容必须分别设置三种单行文字')
        if colors is not None and (not isinstance(colors, dict) or set(colors) != states
                                   or any(value not in ('red', 'yellow', 'green') for value in colors.values())):
            raise ValueError('状态颜色仅支持红、黄、绿')
        if values['led_show_title'] and not str(values['led_school_title']).strip():
            raise ValueError('显示标题时，标题不能为空')
    for screen in screens:
        sid = str(screen.get('id', ''))
        if not re.fullmatch(r'[A-Za-z0-9_-]+', sid) or sid in ids:
            raise ValueError('屏幕标识无效或重复')
        ids.add(sid)
        name = str(screen.get('name', '')).strip()
        if not name:
            raise ValueError('请填写屏幕名称')
        if screen.get('plan_id') not in plan_ids:
            raise ValueError(f'{name}：请选择有效的显示方案')
        plan = next(plan for plan in plans if plan['id'] == screen['plan_id'])
        values = {**ConfigManager.DEFAULT_CONFIG, **plan.get('settings', {}),
                  **screen.get('settings', {})}
        if values['led_grade_filter_mode'] == 'selected' and not values['led_visible_grades']:
            raise ValueError(f'{name}：至少选择一个显示年级')
        grade_pages = values['led_grade_pages']
        if not isinstance(grade_pages, list) or any(
            not isinstance(page, list) or not page or
            any(not isinstance(grade, str) or not grade.strip() for grade in page)
            for page in grade_pages
        ):
            raise ValueError(f'{name}：每页年级必须是非空的年级列表')
        if grade_pages:
            flattened = [grade for page in grade_pages for grade in page]
            if len(flattened) != len(set(flattened)):
                raise ValueError(f'{name}：同一年级不能重复出现在多个页面')
            if values['led_grade_filter_mode'] == 'selected' and set(flattened) != set(values['led_visible_grades']):
                raise ValueError(f'{name}：自定义页面须包含全部已选择的年级')
        if values['led_output_type'] not in ('led', 'desktop'):
            raise ValueError(f'{name}：屏幕输出类型无效')
        if values['led_output_type'] == 'desktop':
            target = ('desktop', str(values['led_monitor']))
            if screen.get('enabled') and target in targets:
                raise ValueError(f'{name}：该电脑显示器已被另一块启用屏幕使用')
            if screen.get('enabled'):
                targets.add(target)
            continue  # Desktop dimensions come from QScreen, never a controller.
        try:
            ip = str(ipaddress.ip_address(values['led_controller_ip']))
            port = int(values['led_controller_port'])
            if not 1 <= port <= 65535:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f'{name}：屏幕 IP 或端口无效') from None
        target = (ip, port)
        if target in targets:
            raise ValueError(f'{name}：该 IP 和端口已被另一块屏使用')
        targets.add(target)
        dimensions = validate_led_dimensions(values['led_width'], values['led_height'], values['led_color_mode'])
        if not dimensions.ok:
            raise ValueError(f'{name}：{dimensions.message}')


class LedScreenConfig:
    """Immutable screen/plan overlay with live access to school-wide settings."""
    def __init__(self, parent, screen, plan):
        from copy import deepcopy
        self.parent = parent
        device_defaults = {}
        if screen.get('settings', {}).get('led_output_type') == 'desktop':
            device_defaults['led_color_mode'] = 'double'
        self.values = deepcopy({**{k: ConfigManager.DEFAULT_CONFIG[k] for k in (*LED_DEVICE_KEYS, *LED_PLAN_KEYS)},
                                **{k: v for k, v in plan.get('settings', {}).items() if k in LED_PLAN_KEYS},
                                **device_defaults,
                                **{k: v for k, v in screen.get('settings', {}).items() if k in LED_DEVICE_KEYS},
                                'led_enabled': bool(screen.get('enabled', False))})

    def get(self, key, default=None):
        return self.values[key] if key in self.values else self.parent.get(key, default)

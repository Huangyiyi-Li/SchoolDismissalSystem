import sys
import os

# Ensure src is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from src.app_info import APP_NAME
from src.services.config_manager import ConfigManager
from src.services.udp_server import UDPServerService
from src.services.broadcast_manager import BroadcastManager
from src.services.led_service import LedService
from src.services.device_identity import get_or_create_device_no
from src.database import DatabaseManager
from src.ui.main_window import MainWindow
from src.utils.path_utils import get_resource_path

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(get_resource_path("assets/branding/logo-vertical.png")))
    
    # Initialize Core Services
    config_manager = ConfigManager()
    db_manager = DatabaseManager()
    # Until the first schedule check completes, never overwrite the controller's
    # original Ledshow program.
    led_service = LedService(config_manager, db_manager, dismissal_active=None)
    
    # API & Sync
    from src.services.api_service import ApiService
    from src.services.data_sync_service import DataSyncService
    
    school_id = config_manager.get("school_id")
    api_service = None
    data_sync_service = None
    
    school_id = config_manager.get("school_id")
    
    # Always initialize services to allow hot-binding of School ID
    print(f"[Main] Initializing API Service (School ID: {school_id or 'Not Set'})")
    api_service = ApiService(school_id, base_url=config_manager.get("api_base_url", "https://rest.xxt.cn"))
    data_sync_service = DataSyncService(
        api_service,
        db_manager,
        config_manager,
        led_service=led_service,
    )
    data_sync_service.start()

    # Services
    broadcast_manager = BroadcastManager(
        config_manager,
        db_manager,
        api_service=api_service,
        led_service=led_service,
    )
    mqtt_service = None
    if config_manager.get("mqtt_enabled", True):
        device_no = get_or_create_device_no(config_manager)
        from src.services.mqtt_service import DismissalMqttService
        mqtt_service = DismissalMqttService(
            device_no=device_no,
            command_handler=broadcast_manager.process_manual_dismissal,
            host=config_manager.get("mqtt_host", "111.6.173.61"),
            port=config_manager.get("mqtt_port", 1883),
            heartbeat_interval_seconds=config_manager.get("mqtt_heartbeat_interval_seconds", 60),
            reconnect_interval_seconds=config_manager.get("mqtt_reconnect_interval_seconds", 60),
            telemetry_topic=config_manager.get("mqtt_telemetry_topic", "v1/devices/me/telemetry"),
            rpc_request_topic=config_manager.get("mqtt_rpc_request_topic", "v1/devices/me/rpc/request/+"),
            rpc_response_topic_template=config_manager.get(
                "mqtt_rpc_response_topic_template",
                "v1/devices/me/rpc/response/{request_id}",
            ),
        )
        mqtt_service.start()
    # Pass db_manager to UDPServer for device management
    udp_server = UDPServerService(port=config_manager.get("udp_port", 39169), db_manager=db_manager)
    
    # Initialize UI
    window = MainWindow(
        config_manager,
        db_manager,
        broadcast_manager,
        udp_server,
        data_sync_service,
        led_service=led_service,
    )
    window.show()
    
    # Start Services
    if not udp_server.start():
        print("Error: Could not bind UDP port.")
    
    # Execution
    exit_code = app.exec()
    
    # Cleanup
    udp_server.stop()
    if mqtt_service:
        mqtt_service.stop()
    broadcast_manager.cleanup()
    led_service.shutdown()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

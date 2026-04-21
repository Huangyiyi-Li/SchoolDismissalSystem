import sys
import os
import logging

# Ensure src is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from PyQt6.QtWidgets import QApplication
from src.services.config_manager import ConfigManager
from src.services.udp_server import UDPServerService
from src.services.broadcast_manager import BroadcastManager
from src.services.system_status import RuntimeStatusStore
from src.database import DatabaseManager
from src.ui.main_window import MainWindow
from src.ui.theme import build_global_stylesheet
from src.utils.path_utils import get_app_root
from src.utils.runtime_logging import configure_runtime_logging

def main():
    log_dir = os.path.join(get_app_root(), "logs")
    log_paths = configure_runtime_logging(log_dir)
    logging.getLogger(__name__).info("Application bootstrap started")

    app = QApplication(sys.argv)
    app.setStyleSheet(build_global_stylesheet())

    udp_server = None
    broadcast_manager = None
    exit_code = 1

    try:
        # Initialize Core Services
        config_manager = ConfigManager()
        db_manager = DatabaseManager()
        status_store = RuntimeStatusStore()

        # API & Sync
        from src.services.api_service import ApiService
        from src.services.data_sync_service import DataSyncService

        school_id = config_manager.get("school_id")

        print(f"[Main] Initializing API Service (School ID: {school_id or 'Not Set'})")
        api_service = ApiService(school_id)
        data_sync_service = DataSyncService(
            api_service,
            db_manager,
            config_manager,
            status_store=status_store,
        )
        data_sync_service.start()

        # Services
        broadcast_manager = BroadcastManager(
            config_manager,
            db_manager,
            api_service=api_service,
            status_store=status_store,
        )
        udp_server = UDPServerService(
            port=config_manager.get("udp_port", 39169),
            db_manager=db_manager,
            status_store=status_store,
        )

        window = MainWindow(
            config_manager,
            db_manager,
            broadcast_manager,
            udp_server,
            data_sync_service,
            status_store=status_store,
        )
        window.enter_guard_mode()
        window.showMaximized()

        if not udp_server.start():
            print("Error: Could not bind UDP port.")

        logging.getLogger(__name__).info(
            "UI ready. runtime_log=%s crash_log=%s",
            log_paths.runtime_log_path,
            log_paths.crash_log_path,
        )
        exit_code = app.exec()
        logging.getLogger(__name__).info("Application event loop exited with code %s", exit_code)
    except Exception:
        logging.getLogger(__name__).exception("Application terminated with an unhandled error")
        raise
    finally:
        if udp_server is not None:
            udp_server.stop()
        if broadcast_manager is not None:
            broadcast_manager.cleanup()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()

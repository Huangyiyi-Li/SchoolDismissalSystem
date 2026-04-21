import sys
import os

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

def main():
    app = QApplication(sys.argv)
    
    # Initialize Core Services
    config_manager = ConfigManager()
    db_manager = DatabaseManager()
    status_store = RuntimeStatusStore()
    
    # API & Sync
    from src.services.api_service import ApiService
    from src.services.data_sync_service import DataSyncService
    
    school_id = config_manager.get("school_id")
    api_service = None
    data_sync_service = None
    
    # Always initialize services to allow hot-binding of School ID
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
    # Pass db_manager to UDPServer for device management
    udp_server = UDPServerService(
        port=config_manager.get("udp_port", 39169),
        db_manager=db_manager,
        status_store=status_store,
    )
    
    # Initialize UI
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
    
    # Start Services
    if not udp_server.start():
        print("Error: Could not bind UDP port.")
    
    # Execution
    exit_code = app.exec()
    
    # Cleanup
    udp_server.stop()
    broadcast_manager.cleanup()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

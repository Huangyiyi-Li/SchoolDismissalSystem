import sys
import os

def get_app_root():
    """
    Returns the application root directory.
    - If frozen (packaged), returns the directory containing the executable.
    - If running as script, returns the project root (3 levels up from this file).
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller Bundle
        return os.path.dirname(sys.executable)
    else:
        # Running as Source (src/utils/path_utils.py -> project_root)
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    Used for static assets bundled INSIDE the exe (e.g. icons, templates).
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(get_app_root(), relative_path)

import PyInstaller.__main__
import os
import shutil

# Clean previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

print("Starting Build Process...")

# Define PyInstaller arguments
args = [
    'main.py',                       # Script to build
    '--name=SchoolDismissalSystem',  # Name of the executable
    '--noconfirm',                   # Replace output directory without asking
    '--clean',                       # Clean cache
    '--windowed',                    # No console window (GUI mode)
    '--onedir',                      # Create a directory (easier for debugging/config) - User asked for "exe file" but folder is safer for "system". 
                                     # Let's use --onedir first. Onefile is often flagged by AV and slower start.
                                     # But user said "ensure can run on other computers", often implies "zip it up".
                                     # I will stick to onedir and maybe zip it manually if I could, but I'll leave it as folder.
                                     # Wait, user said "pack into exe file" (打包成exe文件). Usually means onefile.
                                     # But I have external config/data requirement.
                                     # If I use onefile, the config/data will be created Next to the exe (thanks to path_utils).
                                     # So onefile is FINE.
    '--onefile',                     # Request: "exe file"
    
    # Hidden imports often needed for PyQt/Sqlite/etc if not detected
    '--hidden-import=sqlite3',
    '--hidden-import=pyttsx3.drivers',
    '--hidden-import=pyttsx3.drivers.sapi5',
    '--hidden-import=requests',
    
    # Paths
    '--add-data=src;src',            # Include src if needed for reflection, though usually imports are bundled.
                                     # If we use imports, we don't strictly need add-data src unless dynamic loading.
                                     # But main.py adds src to sys.path.
    
    # Icon (Optional, skip if no icon)
    # '--icon=icon.ico'
]

PyInstaller.__main__.run(args)

print("Build Complete. Executable is in 'dist' folder.")

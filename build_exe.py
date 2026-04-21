import PyInstaller.__main__
import os
import shutil

# Clean previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

print("Starting guarded dashboard client build (Windows onefile GUI)...")

# Define PyInstaller arguments
args = [
    "main.py",
    "--name=SchoolDismissalSystem",
    "--noconfirm",
    "--clean",
    "--windowed",
    # Keep onefile native desktop packaging for low-spec Windows hosts.
    # Do not introduce browser runtimes or heavyweight embedded web engines.
    "--onefile",
    "--hidden-import=sqlite3",
    "--hidden-import=pyttsx3.drivers",
    "--hidden-import=pyttsx3.drivers.sapi5",
    "--hidden-import=requests",
    "--add-data=src;src",
    "--add-binary=vendor/rfpro/win64/comPro.dll;vendor/rfpro/win64",
]

PyInstaller.__main__.run(args)

print("Build complete. Guard dashboard Windows client is in 'dist/SchoolDismissalSystem.exe'.")

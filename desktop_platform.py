"""Native desktop integration, independent of the UI and PDF libraries."""
import os
from pathlib import Path
import subprocess
import sys


IS_MAC = sys.platform == "darwin"
UI_FONT = "PingFang SC" if IS_MAC else "Microsoft YaHei UI"
SHORTCUT_MODIFIER = "Command" if IS_MAC else "Control"
SHORTCUT_LABEL = "⌘" if IS_MAC else "Ctrl"


def application_data_dir():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PDF简作"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PDF简作"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "pdf-jianzuo"


def open_folder(path):
    path = Path(path).resolve()
    if not path.is_dir(): raise FileNotFoundError(f"目录不存在：{path}")
    if sys.platform == "win32":
        os.startfile(str(path))
    else:
        subprocess.Popen(["/usr/bin/open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

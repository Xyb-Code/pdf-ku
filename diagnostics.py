import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from desktop_platform import application_data_dir

_fault_file = None


def shutdown_logging():
    global _fault_file
    faulthandler.cancel_dump_traceback_later()
    faulthandler.disable()
    if _fault_file:
        _fault_file.close()
        _fault_file = None
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


def setup_logging(role="ui", directory=None):
    global _fault_file
    folder = Path(directory) if directory else application_data_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(folder / f"{role}.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s pid=%(process)d %(message)s"))
    logger.addHandler(handler)
    _fault_file = (folder / f"{role}-fault.log").open("a", encoding="utf-8")
    faulthandler.enable(_fault_file)
    if role == "worker":
        faulthandler.dump_traceback_later(60, repeat=True, file=_fault_file)
    def unhandled(kind, value, tb):
        logger.critical("Unhandled exception", exc_info=(kind, value, tb))
    sys.excepthook = unhandled
    logging.info("Startup role=%s python=%s frozen=%s", role, sys.version, getattr(sys, "frozen", False))
    return folder

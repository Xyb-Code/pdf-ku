"""Spawn-only worker: native PDF calls cannot block the Tk process."""
import logging
from pathlib import Path
from diagnostics import setup_logging


def run_job(args, events, log_directory):
    setup_logging("worker", log_directory)
    try:
        from pdf_core import process
        def progress(message):
            logging.info("Stage: %s", message)
            events.put(("status", message))
        logging.info("Job start args=%r", args)
        before = sum(Path(p).stat().st_size for p in args[0])
        folder, files = process(*args, progress=progress)
        after = sum(p.stat().st_size for p in files)
        note = ""
        if len(args) > 6 and args[6]:
            target = args[6] * 1048576
            missed = sum(p.stat().st_size > target for p in files)
            note = f"目标 {args[6]:g} MB/份：" + (f"{missed} 份未达标，已保留尝试中最小的结果。" if missed else "全部达标。")
        logging.info("Job complete files=%s input_bytes=%s output_bytes=%s", len(files), before, after)
        events.put(("done", (folder, len(files), before, after, args[2], note)))
    except BaseException as exc:
        logging.exception("Job failed")
        events.put(("error", str(exc)))

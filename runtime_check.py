"""Optional executable self-check: exercises the frozen UI -> worker -> DLL path."""
import json
from pathlib import Path
import random
import time
import sys
import platform


def run(app_class, directory):
    import pymupdf
    from tkinter import messagebox
    from diagnostics import shutdown_logging
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root / "selfcheck-input.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=400)
        pix = pymupdf.Pixmap(pymupdf.csRGB, 800, 800, random.Random(7).randbytes(800*800*3), False)
        page.insert_image(page.rect, pixmap=pix)
        page.insert_text((30, 30), "PDF RUNTIME CHECK")
        doc.save(source)
    window = app_class(log_directory=root / "logs")
    window.withdraw()
    report = {"success": False, "ui_ticks": 0, "messages": [], "drag_drop_ready": window.dnd_ready,
              "platform": sys.platform, "architecture": platform.machine(), "frozen": bool(getattr(sys, "frozen", False))}
    messagebox.showinfo = lambda title, text: report["messages"].append(str(text))
    messagebox.showerror = lambda title, text: report["messages"].append("ERROR: " + str(text))
    window.paths = [str(source)]
    window.output.set(str(root / "results"))
    start = time.monotonic()
    def check():
        report["ui_ticks"] += 1
        if window.busy and time.monotonic() - start < 45:
            window.after(50, check)
            return
        try:
            if window.busy:
                window.cancel()
                raise RuntimeError("Self-check timed out")
            if not window.last_output: raise RuntimeError("No result from worker")
            if not window.dnd_ready: raise RuntimeError("Drag-and-drop runtime failed to load")
            files = list(window.last_output.glob("*.pdf"))
            with pymupdf.open(files[0]) as doc:
                assert len(doc) == 1
                assert "PDF RUNTIME CHECK" in doc[0].get_text()
                assert doc[0].get_pixmap().width == 400
            report.update(success=True, input_bytes=source.stat().st_size, output_bytes=files[0].stat().st_size)
        except Exception as exc:
            report["error"] = repr(exc)
        finally:
            report["seconds"] = round(time.monotonic() - start, 2)
            (root / "selfcheck.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            window.destroy()
            shutdown_logging()
    window.after(0, window.start)
    window.after(50, check)
    window.mainloop()

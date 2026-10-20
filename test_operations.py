"""Integration checks: synthetic PDFs, page order, images and all levels."""
import tempfile
import unittest
from pathlib import Path
import pymupdf
import multiprocessing as mp
import queue
import time
from unittest.mock import patch
from worker import run_job
from pdf_core import process, page_groups, LEVELS


class OperationsTest(unittest.TestCase):
    def test_operations(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as root:
            root = Path(root)
            sources = []
            for name, pages in (("A", 3), ("B", 2)):
                path = root / f"{name}.pdf"
                with pymupdf.open() as doc:
                    for number in range(pages):
                        page = doc.new_page()
                        page.insert_text((72, 72), f"{name}{number+1}")
                        pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 1200, 1200), False)
                        pix.clear_with(180)
                        page.insert_image(pymupdf.Rect(72, 100, 272, 300), pixmap=pix)
                    doc.save(path)
                sources.append(path)
            originals = [p.read_bytes() for p in sources]
            def texts(paths):
                result = []
                for path in paths:
                    with pymupdf.open(path) as doc:
                        result.extend(p.get_text().strip() for p in doc)
                        for page in doc:
                            self.assertGreater(len(page.get_pixmap().samples), 0)
                return result
            for level in LEVELS:
                _, files = process(sources, root, "压缩 PDF", level)
                self.assertEqual(texts(files), ["A1", "A2", "A3", "B1", "B2"])
                self.assertLessEqual(sum(p.stat().st_size for p in files), sum(len(b) for b in originals))
            for level in (None, "标准压缩 · 推荐"):
                _, files = process(sources[::-1], root, "合并 PDF", level)
                self.assertEqual(texts(files), ["B1", "B2", "A1", "A2", "A3"])
                _, files = process(sources[:1], root, "拆分 PDF", level, split_every=2)
                self.assertEqual(len(files), 2)
                self.assertEqual(texts(files), ["A1", "A2", "A3"])
                _, files = process(sources[:1], root, "拆分 PDF", level, ranges="3,1-2")
                self.assertEqual(texts(files), ["A3", "A1", "A2"])
            self.assertEqual([p.read_bytes() for p in sources], originals)
            for invalid in ("0", "4", "3-1", "1,", "abc"):
                with self.assertRaises(ValueError): page_groups(invalid, 3)

    def test_spawn_worker_success_and_error_logs(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as root:
            root = Path(root)
            source = root / "input.pdf"
            with pymupdf.open() as doc:
                doc.new_page().insert_text((50, 50), "Worker test")
                doc.save(source)
            context = mp.get_context("spawn")
            for path, expected in ((source, "done"), (root / "missing.pdf", "error")):
                events = context.Queue()
                job = context.Process(target=run_job, args=(([str(path)], str(root), "压缩 PDF", "标准压缩 · 推荐", 1, ""), events, str(root / "logs")))
                job.start()
                deadline = time.monotonic() + 20
                kinds = []
                while time.monotonic() < deadline:
                    try:
                        kind, _ = events.get(timeout=0.2)
                        kinds.append(kind)
                        if kind in ("done", "error"): break
                    except queue.Empty:
                        if job.exitcode is not None: break
                job.join(5)
                if job.is_alive():
                    job.terminate()
                    job.join(5)
                self.assertIn(expected, kinds)
                self.assertEqual(job.exitcode, 0)
                events.close()
                events.join_thread()
            log = (root / "logs" / "worker.log").read_text(encoding="utf-8")
            self.assertIn("Ghostscript begin", log)
            self.assertIn("Job complete", log)
            self.assertIn("Traceback", log)

    def test_target_size_and_raster_opt_in(self):
        from pdf_core import raster_compress
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            source = root / "input.pdf"
            with pymupdf.open() as doc:
                page = doc.new_page()
                page.insert_text((50, 50), "SEARCHABLE")
                doc.save(source)
            for invalid in (0, -1, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    process([source], root, "压缩 PDF", "强力压缩 · 小体积", target_mb=invalid)
            # Unachievable target must retain a valid file and all original text.
            _, files = process([source], root, "压缩 PDF", "极限压缩 · 低清", target_mb=0.0001, gray=True)
            self.assertGreater(files[0].stat().st_size, 0.0001*1048576)
            with pymupdf.open(files[0]) as result:
                self.assertIn("SEARCHABLE", result[0].get_text())
            # Raster is used only when explicitly enabled, and renders every page.
            _, files = process([source], root, "压缩 PDF", "极限压缩 · 低清", target_mb=0.0001, allow_raster=True)
            with pymupdf.open(files[0]) as result:
                self.assertEqual(len(result), 1)
            with pymupdf.open(source) as doc:
                raster_compress(doc, root / "raster.pdf", 72, 35, True, lambda s: None)
            with pymupdf.open(root / "raster.pdf") as result:
                self.assertEqual(result[0].get_text(), "")
                self.assertEqual(len(result[0].get_images()), 1)
                self.assertGreater(len(result[0].get_pixmap().samples), 0)

    def test_ui_remains_responsive_and_cancel(self):
        import app
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as root:
            window = app.App(log_directory=Path(root) / "logs")
            window.withdraw()
            try:
                source = Path(root) / "ui-input.pdf"
                with pymupdf.open() as doc:
                    doc.new_page().insert_text((50, 50), "UI compression")
                    doc.save(source)
                window.paths = [str(source)]
                window.output.set(root)
                with patch("app.messagebox.showinfo") as complete, patch("app.messagebox.showerror") as error:
                    window.start()
                    ticks_during_job = []
                    window.after(50, lambda: ticks_during_job.append(window.busy))
                    deadline = time.monotonic() + 20
                    while window.busy and time.monotonic() < deadline:
                        window.update()
                        time.sleep(0.01)
                    self.assertFalse(window.busy)
                    self.assertTrue(any(ticks_during_job))
                    error.assert_not_called()
                    complete.assert_not_called()
                    self.assertTrue(list(window.last_output.glob("*.pdf")))
                window.worker.join(5)
                # A blocked worker cannot stop the Tk event loop or cancel action.
                window.worker = window.context.Process(target=time.sleep, args=(20,))
                window.worker.start()
                window.busy = True
                window.started = time.monotonic()
                ticks = []
                window.after(50, lambda: ticks.append(True))
                deadline = time.monotonic() + 0.4
                while time.monotonic() < deadline:
                    window.update()
                    time.sleep(0.01)
                self.assertTrue(ticks)
                window.cancel()
                window.worker.join(5)
                self.assertFalse(window.worker.is_alive())
                self.assertFalse(window.busy)
                # A native crash must reset the UI instead of spinning forever.
                window.busy = True
                window.exit_seen = time.monotonic() - 2
                with patch("app.messagebox.showerror") as error:
                    window.poll()
                    error.assert_called_once()
                self.assertFalse(window.busy)
            finally:
                window.destroy()
                from diagnostics import shutdown_logging
                shutdown_logging()

    def test_workspace_import_order_and_hidden_ranges(self):
        import app
        from types import SimpleNamespace
        from diagnostics import shutdown_logging
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            paths = [root / name for name in ("first file.pdf", "second.pdf", "third.pdf")]
            for path in paths:
                with pymupdf.open() as doc:
                    doc.new_page().insert_text((50, 50), path.stem)
                    doc.save(path)
            window = app.App(log_directory=root / "logs")
            window.withdraw()
            try:
                window.add_paths([str(p) for p in paths] + [str(paths[0]), str(root / "missing.txt")])
                self.assertEqual(len(window.paths), 3)
                window.drop_files(SimpleNamespace(data="{" + str(paths[0]) + "}"))
                self.assertEqual(len(window.paths), 3)
                window.set_operation("合并 PDF")
                window.drag_row = "2"
                window.files.move("2", "", 0)
                window.drag_end(None)
                self.assertEqual(window.paths, [str(paths[2]), str(paths[0]), str(paths[1])])
                window.files.selection_set(["0", "1"])
                window.move(1)
                self.assertEqual(window.paths, [str(paths[1]), str(paths[2]), str(paths[0])])
                window.files.selection_set(["0", "2"])
                window.remove()
                self.assertEqual(window.paths, [str(paths[2])])
                window.output.set(str(root / "output"))
                window.target_mb.set("2")
                window.change_method("按大小")
                window.save_settings()
                window.target_mb.set("9")
                window.load_settings()
                self.assertEqual(window.target_mb.get(), "2")
                # An old, invalid hidden range must not affect the every-N-pages mode.
                window.set_operation("拆分 PDF")
                window.ranges.set("99-100")
                window.split_mode.set("每 N 页")
                window.update_options()
                with patch("app.messagebox.showerror") as error:
                    window.start()
                    deadline = time.monotonic() + 20
                    while window.busy and time.monotonic() < deadline:
                        window.update()
                        time.sleep(0.01)
                    self.assertFalse(window.busy)
                    error.assert_not_called()
                    self.assertTrue(window.last_output)
                    self.assertEqual(len(list(window.last_output.glob("*.pdf"))), 1)
                window.worker.join(5)
                self.assertEqual(window.open_result_button.cget("state"), "normal")
            finally:
                if window.busy: window.cancel()
                window.destroy()
                shutdown_logging()


if __name__ == "__main__": unittest.main()

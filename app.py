import os
from pathlib import Path
import queue
import multiprocessing as mp
import logging
import time
import math
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD
from diagnostics import setup_logging
from worker import run_job
from ui_shell import Workspace, size_text
from desktop_platform import open_folder


class App(Workspace, ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, log_directory=None):
        super().__init__()
        self.log_directory = setup_logging(directory=log_directory)
        self.context = mp.get_context("spawn")
        self.worker = None
        self.exit_seen = None
        self.stage = "准备就绪"
        self.paths = []
        self.events = None
        self.busy = False
        self.last_output = None
        self.build_workspace()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.poll)

    def start(self):
        if self.busy: return
        try:
            if not self.paths: raise ValueError("请先添加 PDF 文件。")
            if self.operation.get() == "合并 PDF" and len(self.paths) < 2:
                raise ValueError("合并操作至少需要两个 PDF。")
            if not self.output.get().strip(): raise ValueError("请选择输出目录。")
            every = 1
            ranges = self.ranges.get() if self.split_mode.get() == "指定页码" else ""
            if self.operation.get() == "拆分 PDF" and not ranges.strip():
                if self.split_mode.get() == "指定页码": raise ValueError("请填写页码范围，例如 1-3,4-6,7。")
                every = int(self.every.get())
                if every < 1: raise ValueError("每份页数必须为正整数。")
            compression_enabled = self.operation.get() == "压缩 PDF" or self.compress.get()
            target = None
            if compression_enabled and self.use_target.get():
                target = float(self.target_mb.get())
                if not math.isfinite(target) or not 0 < target <= 100000:
                    raise ValueError("目标大小应大于 0 且不超过 100000 MB。")
            if compression_enabled and self.gray.get() and self.level.get() == "无损压缩" and target is None:
                raise ValueError("转为灰度请选择轻度、标准、强力、极限压缩，或启用目标大小。")
            args = (list(self.paths), self.output.get(), self.operation.get(),
                    self.level.get() if compression_enabled else None,
                    every, ranges, target, self.gray.get() if compression_enabled else False,
                    self.allow_raster.get() if target else False)
        except ValueError as exc:
            messagebox.showerror("请检查设置", str(exc))
            return
        self.busy = True
        self.save_settings()
        self.started = time.monotonic()
        self.stage = "正在启动处理进程…"
        self.exit_seen = None
        self.events = self.context.Queue()
        self.set_controls_busy(True)
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self.status_label.configure(text_color="#6558E8")
        self.result_detail.configure(text="正在处理，请稍候；可随时取消。")
        self.status.set("正在处理…")
        logging.info("Launching job args=%r", args)
        try:
            self.worker = self.context.Process(target=run_job, args=(args, self.events, str(self.log_directory)), daemon=True)
            self.worker.start()
        except Exception as exc:
            logging.exception("Worker launch failed")
            self.finish()
            messagebox.showerror("无法启动处理进程", str(exc))

    def finish(self):
        self.busy = False
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar.set(0)
        self.set_controls_busy(False)

    def cancel(self):
        if not self.busy: return
        logging.warning("User cancelled pid=%s", self.worker.pid if self.worker else None)
        if self.worker and self.worker.is_alive():
            self.worker.terminate()
        self.finish()
        self.status_label.configure(text_color="#A6794A")
        self.status.set("已取消。原文件未修改；输出目录可能含部分结果或临时文件。")

    def report_callback_exception(self, kind, value, tb):
        logging.error("UI callback failed", exc_info=(kind, value, tb))
        messagebox.showerror("界面错误", f"{value}\n日志目录：{self.log_directory}")

    def poll(self):
        try:
            for _ in range(30):
                if not self.busy or self.events is None: break
                kind, data = self.events.get_nowait()
                if kind == "status": self.stage = data
                else:
                    self.finish()
                    if kind == "error":
                        logging.error("Worker error: %s", data)
                        self.status.set("处理失败，请检查文件和输出目录。")
                        self.status_label.configure(text_color="#C8646C")
                        self.result_detail.configure(text="可打开左侧调试日志查看详细原因。")
                        messagebox.showerror("处理失败", f"{data}\n日志目录：{self.log_directory}")
                    else:
                        folder, count, before, after, operation, note = data
                        self.last_output = folder
                        detail = f"已完成 · 生成 {count} 个 PDF"
                        if operation == "压缩 PDF" and before:
                            detail += f" 体积减少 {(1-after/before)*100:.1f}%。"
                        if note: detail += f" {note}"
                        self.status.set(detail)
                        self.status_label.configure(text_color="#248568" if "未达标" not in note else "#A6794A")
                        self.result_detail.configure(text=f"{size_text(before)}  →  {size_text(after)}    ·    结果已保存")
                        self.open_result_button.configure(state="normal")
                        self.bar.configure(mode="determinate")
                        self.bar.set(1)
        except queue.Empty: pass
        if self.busy:
            elapsed = int(time.monotonic() - self.started)
            self.status.set(f"{self.stage}  ·  已用时 {elapsed} 秒")
            if self.worker and self.worker.exitcode is not None:
                # Allow the queue feeder a short interval to deliver its final event.
                if self.exit_seen is None: self.exit_seen = time.monotonic()
                elif time.monotonic() - self.exit_seen > 1:
                    code = self.worker.exitcode
                    logging.error("Worker exited without result code=%s", code)
                    self.finish()
                    self.status.set(f"处理进程异常退出（代码 {code}），详细信息见日志。")
                    messagebox.showerror("处理进程异常", f"退出代码：{code}\n日志目录：{self.log_directory}")
        self.after(100, self.poll)

    def open_output(self):
        folder = self.last_output or Path(self.output.get())
        if Path(folder).is_dir(): open_folder(folder)
        else: messagebox.showinfo("结果目录", "完成一次处理后即可打开结果目录。")

    def close(self):
        self.save_settings()
        if self.busy:
            self.cancel()
            self.destroy()
        else: self.destroy()

    def destroy(self):
        # Cancel Tk/CTk timers before destroying their Tcl callback commands.
        for callback in self.tk.splitlist(self.tk.call("after", "info")):
            try: self.after_cancel(callback)
            except tk.TclError: pass
        super().destroy()


if __name__ == "__main__":
    mp.freeze_support()
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--self-check":
        from runtime_check import run
        run(App, sys.argv[2])
    else:
        App().mainloop()

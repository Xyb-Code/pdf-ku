"""Desktop workspace layout and file queue interactions."""
import json
import logging
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from compression_profiles import LEVELS
from desktop_platform import UI_FONT, SHORTCUT_MODIFIER, SHORTCUT_LABEL, IS_MAC, open_folder

BG = "#F5F6FA"
INK = "#21283D"
MUTED = "#7B8499"
ACCENT = "#6558E8"
BORDER = "#E6E9F1"


def size_text(size):
    return f"{size / 1048576:.2f} MB" if size >= 1048576 else f"{size / 1024:.1f} KB"


class Workspace:
    def label(self, parent, text="", size=13, color=INK, bold=False, **kw):
        return ctk.CTkLabel(parent, text=text, text_color=color,
                            font=(UI_FONT, size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command, primary=False, width=90, **kw):
        height = kw.pop("height", 34)
        widget = ctk.CTkButton(parent, text=text, command=command, width=width, height=height,
                              corner_radius=8, fg_color=ACCENT if primary else "#F0F1F8",
                              hover_color="#5548D4" if primary else "#E5E7F2",
                              text_color="white" if primary else "#545D76",
                              font=(UI_FONT, 12), **kw)
        self.controls.append(widget)
        return widget

    def build_workspace(self):
        ctk.set_appearance_mode("light")
        ctk.set_widget_scaling(1)
        ctk.set_window_scaling(1)
        self.title("PDF 简作")
        self.geometry("1180x800")
        self.minsize(1080, 740)
        self.configure(fg_color=BG)
        self.controls = []
        self.file_sizes = {}
        self.drag_row = None
        self.advanced_open = False
        self.operation = tk.StringVar(value="压缩 PDF")
        self.compress = tk.BooleanVar(value=True)
        self.level = tk.StringVar(value="标准压缩 · 推荐")
        self.use_target = tk.BooleanVar(value=False)
        self.target_mb = tk.StringVar(value="1")
        self.gray = tk.BooleanVar(value=False)
        self.allow_raster = tk.BooleanVar(value=False)
        self.every = tk.StringVar(value="1")
        self.ranges = tk.StringVar()
        self.split_mode = tk.StringVar(value="每 N 页")
        self.output = tk.StringVar(value=str(Path.home() / "Documents" / "PDF简作"))
        self.method = tk.StringVar(value="按质量")
        self.settings_path = self.log_directory.parent / "settings.json"
        self.load_settings()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        rail = ctk.CTkFrame(self, width=174, corner_radius=0, fg_color="#1A2035")
        rail.grid(row=0, column=0, sticky="ns")
        rail.grid_propagate(False)
        self.label(rail, "P /", 35, "#AAA3FF", True).pack(anchor="w", padx=27, pady=(27, 0))
        self.label(rail, "PDF 简作", 21, "white", True).pack(anchor="w", padx=27)
        self.label(rail, "让文件处理更简单", 11, "#929AB3").pack(anchor="w", padx=27, pady=(3, 40))
        self.label(rail, "文件工具", 10, "#7E87A1").pack(anchor="w", padx=27, pady=(0, 10))
        self.nav = {}
        for symbol, name in (("↘", "压缩 PDF"), ("⊕", "合并 PDF"), ("⋮", "拆分 PDF")):
            button = ctk.CTkButton(rail, text=f"{symbol}    {name}", anchor="w", height=46, width=146,
                                  corner_radius=9, fg_color="transparent", hover_color="#2C3452",
                                  text_color="#B8C0D6", font=(UI_FONT, 14),
                                  command=lambda value=name: self.set_operation(value))
            button.pack(padx=14, pady=4)
            self.nav[name] = button
            self.controls.append(button)
        bottom = ctk.CTkFrame(rail, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=24, pady=24)
        ctk.CTkButton(bottom, text="调试日志  ↗", anchor="w", width=125, height=32,
                     fg_color="transparent", hover_color="#2C3452", text_color="#A8B1CC",
                     command=lambda: open_folder(self.log_directory), font=(UI_FONT, 12)).pack(anchor="w", pady=(0, 22))
        self.label(bottom, "●  本地处理", 12, "#7BDCC1").pack(anchor="w")
        self.label(bottom, "文件无需上传\n始终保留原文件", 10, "#8E98B4", justify="left").pack(anchor="w", pady=(6, 0))

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=26, pady=22)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        heading = ctk.CTkFrame(main, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 21))
        self.label(heading, "WORKSPACE  /  文件工作台", 10, MUTED).pack(anchor="w")
        self.page_title = self.label(heading, size=27, bold=True)
        self.page_title.pack(anchor="w", pady=(6, 2))
        self.page_subtitle = self.label(heading, size=12, color=MUTED)
        self.page_subtitle.pack(anchor="w")
        body = ctk.CTkFrame(main, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=316)

        file_card = ctk.CTkFrame(body, fg_color="white", corner_radius=14, border_width=1, border_color=BORDER)
        file_card.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        file_card.grid_columnconfigure(0, weight=1)
        file_card.grid_rowconfigure(2, weight=1)
        toolbar = ctk.CTkFrame(file_card, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=(17, 5))
        self.label(toolbar, "待处理文件", 15, bold=True).pack(side="left")
        self.count = self.label(toolbar, "0 个文件", 11, MUTED)
        self.count.pack(side="left", padx=12)
        self.button(toolbar, "+ 添加文件", self.add, width=96, primary=True).pack(side="right")
        self.queue_hint = self.label(file_card, "支持多个 PDF，也可以直接拖入文件", 11, MUTED)
        self.queue_hint.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))
        self.table_area = ctk.CTkFrame(file_card, fg_color="white", corner_radius=0)
        self.table_area.grid(row=2, column=0, sticky="nsew", padx=14)
        self.table_area.grid_columnconfigure(0, weight=1)
        self.table_area.grid_rowconfigure(0, weight=1)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Files.Treeview", background="white", fieldbackground="white", foreground=INK,
                        rowheight=54, borderwidth=0, font=(UI_FONT, 10), relief="flat")
        style.configure("Files.Treeview.Heading", background="#F7F8FC", foreground=MUTED,
                        padding=(8, 10), borderwidth=0, font=(UI_FONT, 9))
        style.layout("Files.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.map("Files.Treeview", background=[("selected", "#EEEBFF")], foreground=[("selected", ACCENT)])
        self.files = ttk.Treeview(self.table_area, columns=("order", "name", "size"), show="headings", selectmode="extended", style="Files.Treeview")
        for key, title, width in (("order", "序号", 46), ("name", "文件名称", 260), ("size", "大小", 90)):
            self.files.heading(key, text=title, anchor="w")
            self.files.column(key, width=width, minwidth=40, stretch=key == "name", anchor="w")
        self.files.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(self.table_area, command=self.files.yview, width=12, button_color="#CBD0DF", button_hover_color="#AAB2C9")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.files.configure(yscrollcommand=scrollbar.set)
        self.files.bind("<<TreeviewSelect>>", lambda e: self.selection_changed())
        self.files.bind("<Delete>", lambda e: self.remove())
        if IS_MAC:
            self.files.bind("<BackSpace>", lambda e: self.remove())
        self.files.bind("<ButtonPress-1>", self.drag_start, add="+")
        self.files.bind("<B1-Motion>", self.drag_move, add="+")
        self.files.bind("<ButtonRelease-1>", self.drag_end, add="+")
        self.empty = ctk.CTkFrame(self.table_area, fg_color="#FAFAFE", corner_radius=12, border_width=1, border_color="#DCD8F7")
        self.empty.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.empty_content = ctk.CTkFrame(self.empty, fg_color="transparent")
        self.empty_content.place(relx=0.5, rely=0.5, anchor="center")
        icon = self.empty_icon = tk.Canvas(self.empty_content, width=68, height=64, bg="#FAFAFE", highlightthickness=0)
        icon.pack(pady=(0, 12))
        icon.create_rectangle(12, 4, 49, 50, outline="#C5BFF5", width=2, fill="#EFECFF")
        icon.create_line(22, 19, 40, 19, fill="#A79DE9", width=2)
        icon.create_line(22, 29, 36, 29, fill="#A79DE9", width=2)
        icon.create_oval(38, 35, 66, 63, fill=ACCENT, outline="#FAFAFE", width=3)
        icon.create_line(46, 49, 58, 49, fill="white", width=2)
        icon.create_line(52, 43, 52, 55, fill="white", width=2)
        self.empty_title = self.label(self.empty_content, "将 PDF 文件拖到这里", 19, bold=True)
        self.empty_title.pack()
        self.table_area.bind("<Configure>", self.resize_empty)
        self.label(self.empty_content, "支持批量导入，无需打开或预览文件", 12, MUTED).pack(pady=(6, 19))
        self.button(self.empty_content, "选择 PDF 文件", self.add, primary=True, width=160, height=42).pack()
        self.label(self.empty_content, f"或按 {SHORTCUT_LABEL} + O 选择文件", 10, "#9CA3B6").pack(pady=12)
        queue_footer = ctk.CTkFrame(file_card, fg_color="transparent")
        queue_footer.grid(row=3, column=0, sticky="ew", padx=18, pady=12)
        self.remove_button = self.button(queue_footer, "移除选中", self.remove, width=82)
        self.remove_button.pack(side="left")
        self.order_tools = ctk.CTkFrame(queue_footer, fg_color="transparent")
        self.button(self.order_tools, "↑", lambda: self.move(-1), width=34).pack(side="left", padx=(6, 3))
        self.button(self.order_tools, "↓", lambda: self.move(1), width=34).pack(side="left")
        self.button(queue_footer, "清空", self.clear, width=50).pack(side="right")
        self.path_hint = self.label(file_card, "选择文件后可查看所在位置", 10, MUTED, anchor="w", wraplength=430)
        self.path_hint.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 15))

        self.settings = ctk.CTkScrollableFrame(body, width=288, fg_color="white", corner_radius=14,
                                                border_width=1, border_color=BORDER, scrollbar_button_color="#CBD0DF", scrollbar_button_hover_color="#AAB2C9")
        self.settings.grid(row=0, column=1, sticky="nsew")
        self.settings.grid_columnconfigure(0, weight=1)
        self.label(self.settings, "处理设置", 15, bold=True).pack(anchor="w", padx=16, pady=(14, 4))
        self.settings_hint = self.label(self.settings, "调整体积与清晰度的平衡", 11, MUTED)
        self.settings_hint.pack(anchor="w", padx=16, pady=(0, 15))
        self.split_box = ctk.CTkFrame(self.settings, fg_color="transparent")
        self.label(self.split_box, "拆分方式", 12, bold=True).pack(anchor="w", pady=(0, 9))
        self.split_selector = ctk.CTkSegmentedButton(self.split_box, values=["每 N 页", "指定页码"], variable=self.split_mode,
                                                    command=lambda _: self.update_options(), selected_color=ACCENT, unselected_color="#F0F1F8", text_color=INK,
                                                    fg_color="#F0F1F8", text_color_disabled=MUTED, font=(UI_FONT, 12), height=34)
        self.split_selector.pack(fill="x")
        self.controls.append(self.split_selector)
        self.every_box = ctk.CTkFrame(self.split_box, fg_color="transparent")
        self.every_entry = ctk.CTkEntry(self.every_box, textvariable=self.every, width=80, height=36)
        self.every_entry.pack(side="left")
        self.label(self.every_box, "页生成一份 PDF", 12, MUTED).pack(side="left", padx=10)
        self.range_box = ctk.CTkFrame(self.split_box, fg_color="transparent")
        self.range_entry = ctk.CTkEntry(self.range_box, textvariable=self.ranges, placeholder_text="例如 1-3,4-6,7", height=36)
        self.range_entry.pack(fill="x")
        self.label(self.range_box, "每个逗号分隔的范围生成一份文件", 10, MUTED).pack(anchor="w", pady=5)
        self.controls.extend([self.every_entry, self.range_entry])
        self.compress_check = ctk.CTkSwitch(self.settings, text="完成后压缩", variable=self.compress, command=self.update_options,
                                           progress_color=ACCENT, font=(UI_FONT, 12))
        self.controls.append(self.compress_check)
        self.compression_box = ctk.CTkFrame(self.settings, fg_color="transparent")
        self.method_selector = ctk.CTkSegmentedButton(self.compression_box, values=["按质量", "按大小"], variable=self.method,
                                                       command=self.change_method, selected_color=ACCENT, unselected_color="#F0F1F8", text_color=INK,
                                                       fg_color="#F0F1F8", height=36, font=(UI_FONT, 12))
        self.method_selector.pack(fill="x", pady=(0, 15))
        self.controls.append(self.method_selector)
        self.quality_box = ctk.CTkFrame(self.compression_box, fg_color="transparent")
        self.level_buttons = {}
        for value, caption in zip(LEVELS, ("保留清晰度，清理多余数据", "适合打印与高清阅读", "清晰度与体积兼顾", "适合发送和日常分享", "体积优先，图片会更模糊")):
            button = ctk.CTkButton(self.quality_box, text=value + "\n" + caption, anchor="w", height=46,
                                   fg_color="#F7F8FC", hover_color="#EEEBFF", text_color="#58627A", border_width=1,
                                   border_color=BORDER, font=(UI_FONT, 11), command=lambda val=value: self.set_level(val))
            button.pack(fill="x", pady=(0, 4))
            self.level_buttons[value] = button
            self.controls.append(button)
        self.target_box = ctk.CTkFrame(self.compression_box, fg_color="transparent")
        self.label(self.target_box, "每份文件的目标大小", 12, bold=True).pack(anchor="w", pady=(0, 10))
        target_row = ctk.CTkFrame(self.target_box, fg_color="transparent")
        target_row.pack(fill="x")
        self.target_entry = ctk.CTkEntry(target_row, textvariable=self.target_mb, height=43, width=185, font=(UI_FONT, 20))
        self.target_entry.pack(side="left")
        self.controls.append(self.target_entry)
        self.label(target_row, "MB", 13, MUTED).pack(side="left", padx=12)
        presets = ctk.CTkFrame(self.target_box, fg_color="transparent")
        presets.pack(fill="x", pady=10)
        for size in (1, 2, 5, 10):
            self.button(presets, f"{size} MB", lambda val=size: self.target_mb.set(str(val)), width=55).pack(side="left", padx=(0, 5))
        self.label(self.target_box, "逐档降低图片质量，尽量达到目标。\n实际大小取决于内容，未达标会提示。", 11, MUTED, justify="left").pack(anchor="w", pady=(0, 10))
        self.advanced_toggle = self.button(self.compression_box, "高级选项  +", self.toggle_advanced, width=260)
        self.advanced_toggle.pack(fill="x", pady=(9, 0))
        self.advanced = ctk.CTkFrame(self.compression_box, fg_color="#F7F8FC", corner_radius=8)
        self.gray_check = ctk.CTkCheckBox(self.advanced, text="转为灰度（去除颜色）", variable=self.gray, fg_color=ACCENT,
                                          command=self.update_options, font=(UI_FONT, 11), checkbox_width=18, checkbox_height=18)
        self.gray_check.pack(anchor="w", padx=12, pady=(13, 12))
        self.raster_check = ctk.CTkCheckBox(self.advanced, text="允许整页转为图片", variable=self.allow_raster, fg_color=ACCENT,
                                           command=self.update_options, font=(UI_FONT, 11), checkbox_width=18, checkbox_height=18)
        self.raster_check.pack(anchor="w", padx=12)
        self.label(self.advanced, "仅在目标大小未达标时使用；会失去\n文字搜索、复制及链接。", 10, "#A6794A", justify="left").pack(anchor="w", padx=12, pady=(6, 12))
        self.controls.extend([self.gray_check, self.raster_check])
        self.no_compress_hint = self.label(self.settings, "按原页面内容输出，不进行压缩。", 11, MUTED)

        footer = ctk.CTkFrame(main, fg_color="white", corner_radius=14, border_width=1, border_color=BORDER)
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        output_row = ctk.CTkFrame(footer, fg_color="transparent")
        output_row.pack(fill="x", padx=20, pady=(14, 10))
        self.label(output_row, "保存到", 12, bold=True).pack(side="left", padx=(0, 12))
        self.output_entry = ctk.CTkEntry(output_row, textvariable=self.output, height=32, border_width=0, fg_color="#F5F6FA", text_color="#68728B")
        self.output_entry.pack(side="left", fill="x", expand=True)
        self.controls.append(self.output_entry)
        self.button(output_row, "更改", self.choose_output, width=55).pack(side="left", padx=(8, 0))
        self.bar = ctk.CTkProgressBar(footer, height=3, corner_radius=0, progress_color=ACCENT, fg_color="#ECEEF5", mode="determinate")
        self.bar.pack(fill="x", padx=20)
        self.bar.set(0)
        action = ctk.CTkFrame(footer, fg_color="transparent")
        action.pack(fill="x", padx=20, pady=14)
        status_box = ctk.CTkFrame(action, fg_color="transparent")
        status_box.pack(side="left", fill="x", expand=True)
        self.status = tk.StringVar(value="添加 PDF 文件即可开始")
        self.status_label = self.label(status_box, size=12, bold=True, textvariable=self.status, anchor="w", wraplength=480)
        self.status_label.pack(anchor="w")
        self.result_detail = self.label(status_box, f"原文件保持不变  ·  {SHORTCUT_LABEL} + Enter 开始处理", 10, MUTED)
        self.result_detail.pack(anchor="w", pady=(3, 0))
        self.open_result_button = ctk.CTkButton(action, text="打开结果 ↗", command=self.open_output, width=100, height=40,
                                               fg_color="#E9F7F1", text_color="#248568", hover_color="#DAF0E5", state="disabled",
                                               font=(UI_FONT, 12))
        self.open_result_button.pack(side="right", padx=(10, 0))
        self.go = ctk.CTkButton(action, text="开始压缩 →", command=self.start, width=140, height=40, fg_color=ACCENT,
                                hover_color="#5548D4", font=(UI_FONT, 13, "bold"))
        self.go.pack(side="right")
        self.cancel_button = ctk.CTkButton(action, text="取消处理", command=self.cancel, width=95, height=40,
                                           fg_color="#FCEEEF", text_color="#C8646C", hover_color="#F8E0E3", font=(UI_FONT, 12))
        self.dnd_ready = False
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            for widget in (self, self.files, self.empty):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.drop_files)
            self.dnd_ready = True
        except Exception:
            logging.exception("Drag and drop initialization failed")
            self.empty_title.configure(text="添加需要处理的 PDF")
        self.bind(f"<{SHORTCUT_MODIFIER}-o>", lambda e: self.add())
        self.bind(f"<{SHORTCUT_MODIFIER}-Return>", lambda e: self.start())
        self.bind("<Escape>", lambda e: self.cancel())
        for number, mode in enumerate(self.nav, 1):
            self.bind(f"<Alt-Key-{number}>", lambda e, value=mode: self.set_operation(value))
        self.update_options()
        self.refresh()

    def load_settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            for name in ("output", "level", "target_mb", "gray", "compress"):
                if name in data and (name != "level" or data[name] in LEVELS):
                    getattr(self, name).set(data[name])
            self.use_target.set(bool(data.get("use_target", False)))
            self.method.set("按大小" if self.use_target.get() else "按质量")
        except (OSError, ValueError, tk.TclError): pass

    def save_settings(self):
        try:
            self.settings_path.write_text(json.dumps({name: getattr(self, name).get() for name in
                                          ("output", "level", "target_mb", "gray", "compress", "use_target")}, ensure_ascii=False), encoding="utf-8")
        except OSError: logging.exception("Could not save preferences")

    def set_operation(self, value):
        if self.busy: return
        self.operation.set(value)
        self.update_options()

    def change_method(self, value):
        self.method.set(value)
        self.use_target.set(value == "按大小")
        self.update_options()

    def set_level(self, value):
        self.level.set(value)
        self.update_options()

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        self.update_options()

    def update_options(self):
        operation = self.operation.get()
        split = operation == "拆分 PDF"
        merge = operation == "合并 PDF"
        for name, button in self.nav.items():
            button.configure(fg_color="#373264" if operation == name else "transparent", text_color="white" if operation == name else "#B8C0D6")
        titles = {"压缩 PDF": ("压缩 PDF", "减小文件体积，让发送与分享更轻松。", "开始压缩 →"),
                  "合并 PDF": ("合并 PDF", "按你的顺序，把多个文件整理成一份。", "开始合并 →"),
                  "拆分 PDF": ("拆分 PDF", "按页数或指定范围，灵活拆分文件。", "开始拆分 →")}
        title, subtitle, action = titles[operation]
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        self.settings_hint.configure(text="指定拆分规则，可继续压缩" if split else "合并后可选择继续压缩" if merge else "调整体积与清晰度的平衡")
        self.go.configure(text=action)
        self.queue_hint.configure(text="拖动文件行可调整合并顺序，也可使用 ↑ ↓" if merge else "支持多个 PDF，可继续拖入文件或点击添加")
        self.split_box.pack_forget()
        self.compress_check.pack_forget()
        self.compression_box.pack_forget()
        self.no_compress_hint.pack_forget()
        if split:
            self.split_box.pack(fill="x", padx=16, pady=(0, 16))
            self.every_box.pack_forget()
            self.range_box.pack_forget()
            (self.every_box if self.split_mode.get() == "每 N 页" else self.range_box).pack(fill="x", pady=(12, 0))
        if operation != "压缩 PDF":
            self.compress_check.pack(anchor="w", padx=16, pady=(0, 16))
        enabled = operation == "压缩 PDF" or self.compress.get()
        if enabled:
            self.compression_box.pack(fill="x", padx=16, pady=(0, 16))
        else: self.no_compress_hint.pack(anchor="w", padx=16, pady=(0, 20))
        self.quality_box.pack_forget()
        self.target_box.pack_forget()
        (self.target_box if self.use_target.get() else self.quality_box).pack(fill="x", before=self.advanced_toggle)
        for name, button in self.level_buttons.items():
            selected = self.level.get() == name
            button.configure(fg_color="#F0EDFF" if selected else "#F7F8FC", border_color="#ADA3F5" if selected else BORDER,
                             text_color=ACCENT if selected else "#58627A")
        active = int(self.gray.get()) + int(self.allow_raster.get() and self.use_target.get())
        advanced_text = "高级选项" + (f" · {active} 项启用" if active else "") + ("  −" if self.advanced_open else "  +")
        self.advanced_toggle.configure(text=advanced_text)
        if self.advanced_open: self.advanced.pack(fill="x", pady=(8, 0))
        else: self.advanced.pack_forget()
        self.raster_check.configure(state="normal" if self.use_target.get() and not self.busy else "disabled")
        if merge: self.order_tools.pack(side="left")
        else: self.order_tools.pack_forget()
        self.selection_changed()
        if not self.busy:
            self.go.configure(state="normal" if len(self.paths) >= (2 if merge else 1) else "disabled")

    def set_controls_busy(self, busy):
        for widget in self.controls:
            widget.configure(state="disabled" if busy else "normal")
        if busy:
            self.go.pack_forget()
            self.cancel_button.pack(side="right")
            self.open_result_button.configure(state="disabled")
        else:
            self.cancel_button.pack_forget()
            self.go.pack(side="right")
            self.go.configure(state="normal")
            self.update_options()

    def resize_empty(self, event):
        if event.height < 265: self.empty_icon.pack_forget()
        elif not self.empty_icon.winfo_manager(): self.empty_icon.pack(pady=(0, 12), before=self.empty_title)

    def add_paths(self, paths):
        if self.busy: return
        existing = {os.path.normcase(os.path.abspath(p)) for p in self.paths}
        rejected = 0
        for raw in paths:
            path = Path(raw)
            key = os.path.normcase(os.path.abspath(path))
            if path.suffix.lower() != ".pdf" or not path.is_file():
                rejected += 1
                continue
            if key not in existing:
                self.paths.append(str(path.resolve()))
                self.file_sizes[str(path.resolve())] = path.stat().st_size
                existing.add(key)
        self.refresh()
        if rejected: self.status.set(f"已忽略 {rejected} 项，请添加 PDF 文件。")

    def add(self):
        if self.busy: return
        self.add_paths(filedialog.askopenfilenames(title="选择 PDF 文件（支持多选）", filetypes=[("PDF 文件", "*.pdf")]))

    def drop_files(self, event):
        self.add_paths(self.tk.splitlist(event.data))
        return "copy"

    def refresh(self, selected=()):
        self.files.delete(*self.files.get_children())
        for n, path in enumerate(self.paths):
            size = self.file_sizes.get(path)
            if size is None:
                try: size = Path(path).stat().st_size
                except OSError: size = 0
                self.file_sizes[path] = size
            self.files.insert("", "end", iid=str(n), values=(f"{n+1:02d}", Path(path).name, size_text(size)))
        self.files.selection_set([str(i) for i in selected if i < len(self.paths)])
        total = sum(self.file_sizes.get(p, 0) for p in self.paths)
        self.count.configure(text=f"{len(self.paths)} 个文件  ·  {size_text(total)}" if self.paths else "0 个文件")
        if self.paths: self.empty.place_forget()
        else: self.empty.place(relx=0, rely=0, relwidth=1, relheight=1)
        if not self.busy:
            self.status.set(f"已就绪 · {len(self.paths)} 个文件" if self.paths else "添加 PDF 文件即可开始")
        self.selection_changed()
        self.go.configure(state="normal" if len(self.paths) >= (2 if self.operation.get() == "合并 PDF" else 1) else "disabled")

    def selection_changed(self):
        selected = self.files.selection()
        self.remove_button.configure(state="normal" if selected and not self.busy else "disabled")
        self.path_hint.configure(text=str(Path(self.paths[int(selected[0])]).parent) if selected else f"{SHORTCUT_LABEL} 多选 · Delete 移除" if self.paths else "文件仅在本机处理，不会上传")

    def clear(self):
        if self.busy: return
        self.paths.clear()
        self.file_sizes.clear()
        self.refresh()

    def remove(self):
        if self.busy: return
        for index in sorted((int(i) for i in self.files.selection()), reverse=True):
            self.file_sizes.pop(self.paths[index], None)
            del self.paths[index]
        self.refresh()

    def move(self, delta):
        if self.busy: return
        selected = sorted(int(i) for i in self.files.selection())
        if not selected or (delta < 0 and selected[0] == 0) or (delta > 0 and selected[-1] == len(self.paths)-1): return
        for i in selected if delta < 0 else reversed(selected):
            self.paths[i], self.paths[i+delta] = self.paths[i+delta], self.paths[i]
        self.refresh([i+delta for i in selected])

    def drag_start(self, event):
        self.drag_row = self.files.identify_row(event.y)

    def drag_move(self, event):
        if self.busy or self.operation.get() != "合并 PDF" or not self.drag_row: return
        target = self.files.identify_row(event.y)
        if target:
            self.files.move(self.drag_row, "", self.files.index(target))
            self.files.selection_set(self.drag_row)

    def drag_end(self, event):
        if not self.busy and self.operation.get() == "合并 PDF" and self.drag_row:
            order = self.files.get_children()
            chosen = order.index(self.drag_row)
            self.paths = [self.paths[int(i)] for i in order]
            self.refresh([chosen])
        self.drag_row = None

    def choose_output(self):
        path = filedialog.askdirectory(title="选择结果保存位置", initialdir=self.output.get() if Path(self.output.get()).is_dir() else None)
        if path: self.output.set(path)

"""Bundled Ghostscript adapter for Windows and macOS; no system install needed."""
import ctypes as C
from collections import deque
import logging
from pathlib import Path
import re
import sys


def engine_path():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    relative = Path("bin/gsdll64.dll") if sys.platform == "win32" else Path("lib/libgs.dylib") if sys.platform == "darwin" else Path("lib/libgs.so")
    candidates = [base / "ghostscript" / relative, base / "tools" / "ghostscript" / relative]
    for path in candidates:
        if path.is_file(): return path
    raise FileNotFoundError("程序内置的 PDF 压缩引擎不完整，请使用完整安装包。")


def compress(source, destination, dpi, quality, gray=False, progress=lambda s: None):
    dll_path = engine_path()
    dll = C.WinDLL(str(dll_path)) if sys.platform == "win32" else C.CDLL(str(dll_path))
    pointer = C.c_void_p
    callback_factory = C.WINFUNCTYPE if sys.platform == "win32" else C.CFUNCTYPE
    callback_type = callback_factory(C.c_int, pointer, pointer, C.c_int)
    dll.gsapi_new_instance.argtypes = [C.POINTER(pointer), pointer]
    dll.gsapi_new_instance.restype = C.c_int
    dll.gsapi_delete_instance.argtypes = [pointer]
    dll.gsapi_delete_instance.restype = None
    dll.gsapi_set_arg_encoding.argtypes = [pointer, C.c_int]
    dll.gsapi_set_arg_encoding.restype = C.c_int
    dll.gsapi_set_stdio.argtypes = [pointer, callback_type, callback_type, callback_type]
    dll.gsapi_set_stdio.restype = C.c_int
    dll.gsapi_init_with_args.argtypes = [pointer, C.c_int, C.POINTER(C.c_char_p)]
    dll.gsapi_init_with_args.restype = C.c_int
    dll.gsapi_exit.argtypes = [pointer]
    dll.gsapi_exit.restype = C.c_int
    errors = deque(maxlen=20)
    def output(handle, data, size):
        text = C.string_at(data, size).decode("utf-8", errors="replace").strip()
        if text:
            logging.info("Ghostscript: %s", text)
            errors.append(text)
            match = re.search(r"Page\s+(\d+)", text)
            if match:
                progress(f"Ghostscript 压缩第 {match[1]} 页 · {dpi} DPI / 质量 {quality}")
        return size
    out_cb = callback_type(output)
    in_cb = callback_type(lambda *_: 0)
    root = dll_path.parent.parent
    search_path = (";" if sys.platform == "win32" else ":").join(str(root / part) for part in ("Resource/Init", "Resource/Font", "lib"))
    # Force JPEG re-encoding: existing JPEG/JPX data must not pass through unchanged.
    args = ["pdf-simple", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7", "-dAutoRotatePages=/None",
            "-dDetectDuplicateImages=true", "-dCompressFonts=true", "-dSubsetFonts=true",
            "-dPassThroughJPEGImages=false", "-dPassThroughJPXImages=false",
            f"-sColorConversionStrategy={'Gray' if gray else 'RGB'}",
            f"-I{search_path}",
            f"-sOutputFile={Path(destination).resolve()}"]
    for color in ("Color", "Gray", "Mono"):
        resolution = max(dpi, 150) if color == "Mono" else dpi
        args += [f"-dDownsample{color}Images=true", f"-d{color}ImageResolution={resolution}",
                 f"-d{color}ImageDownsampleThreshold=1.0",
                 f"-d{color}ImageDownsampleType=/{'Subsample' if color == 'Mono' else 'Bicubic'}"]
    args += ["-dAutoFilterColorImages=false", "-dAutoFilterGrayImages=false",
             "-dColorImageFilter=/DCTEncode", "-dGrayImageFilter=/DCTEncode"]
    # QFactor is the JPEG quantisation scale (smaller => higher quality).
    qfactor = round(max(0.1, 1.0 - quality / 100), 2)
    image_dict = f"<< /QFactor {qfactor} /Blend 1 /HSamples [2 1 1 2] /VSamples [2 1 1 2] >>"
    args += ["-c", f"<< /NeverEmbed [] /ColorImageDict {image_dict} /GrayImageDict {image_dict} >> setdistillerparams",
             "-f", str(Path(source).resolve())]
    logging.info("Ghostscript begin dll=%s args=%r", dll_path, args)
    encoded = [arg.encode("utf-8") for arg in args]
    argv = (C.c_char_p * len(encoded))(*encoded)
    instance = pointer()
    status = dll.gsapi_new_instance(C.byref(instance), None)
    if status < 0: raise RuntimeError(f"Ghostscript 初始化失败：{status}")
    initialized = False
    try:
        if dll.gsapi_set_arg_encoding(instance, 1) < 0:
            raise RuntimeError("Ghostscript 无法启用 UTF-8 路径。")
        dll.gsapi_set_stdio(instance, in_cb, out_cb, out_cb)
        initialized = True
        status = dll.gsapi_init_with_args(instance, len(encoded), argv)
        exit_status = dll.gsapi_exit(instance)
        initialized = False
        if status not in (0, -101) or exit_status < 0:
            raise RuntimeError(f"Ghostscript 压缩失败（{status}/{exit_status}）：\n" + "\n".join(errors))
    finally:
        if initialized: dll.gsapi_exit(instance)
        dll.gsapi_delete_instance(instance)
    if not Path(destination).is_file(): raise RuntimeError("Ghostscript 未生成输出文件。")
    logging.info("Ghostscript complete bytes=%s", Path(destination).stat().st_size)

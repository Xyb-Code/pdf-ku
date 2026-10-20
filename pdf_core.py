"""PDF operations, independent of the desktop interface."""
from pathlib import Path
import re
import tempfile
import logging
import shutil
import time
import pymupdf
from compression_profiles import LEVELS, TARGET_PROFILES
from gs_engine import compress as gs_compress


def raster_compress(doc, destination, dpi, quality, gray, progress):
    """Opt-in last resort; the UI explicitly explains that searchable text is lost."""
    with pymupdf.open() as result:
        for n, page in enumerate(doc, 1):
            progress(f"整页图像压缩 {n}/{len(doc)} · {dpi} DPI")
            # Bound peak raster allocation for unusually large page dimensions.
            scale = min(dpi / 72, (16_000_000 / max(1, page.rect.width * page.rect.height)) ** 0.5)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY if gray else pymupdf.csRGB, alpha=False)
            image = pix.tobytes("jpeg", jpg_quality=quality)
            new_page = result.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=image)
            logging.info("Raster page=%s dpi=%s quality=%s image_bytes=%s", n, dpi, quality, len(image))
            del pix, image
        result.save(destination, garbage=3, deflate=True, use_objstms=1)


def open_pdf(path):
    doc = pymupdf.open(path)
    if not doc.is_pdf or doc.needs_pass or not doc.page_count:
        doc.close()
        raise ValueError(f"无法处理空文件、非 PDF 或需要密码的文件：{Path(path).name}")
    return doc


def page_groups(text, count):
    """Comma separates output files; hyphen selects an inclusive range."""
    groups = []
    for part in text.replace("，", ",").split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
        if not match:
            raise ValueError("页码格式应为 1-3,4-6,7；每个逗号分隔的范围生成一个 PDF。")
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= count:
            raise ValueError(f"页码必须在 1 至 {count} 之间，且起始页不能大于结束页。")
        groups.append((start - 1, end - 1))
    return groups


def save_pdf(doc, target, level, fallback=None, progress=lambda s: None, target_mb=None, gray=False, allow_raster=False):
    target = Path(target)
    if target.exists():
        raise FileExistsError(f"目标文件已存在，请更换输出位置：{target.name}")
    started = time.monotonic()
    logging.info("Save start target=%s pages=%s level=%s", target, len(doc), level)
    # Avoid garbage=4's expensive stream comparisons and full-PDF byte copies.
    with tempfile.TemporaryDirectory(prefix=".work_", dir=target.parent) as tmp:
        baseline = Path(tmp) / "lossless.pdf"
        progress(f"正在优化数据并写入：{target.name}")
        doc.save(baseline, garbage=3, deflate=True, use_objstms=1)
        best = Path(fallback) if fallback and Path(fallback).stat().st_size < baseline.stat().st_size else baseline
        logging.info("Lossless saved bytes=%s elapsed=%.2fs", baseline.stat().st_size, time.monotonic()-started)
        budget = int(target_mb * 1048576) if target_mb else None
        profiles = TARGET_PROFILES if budget else ([LEVELS[level]] if level and LEVELS[level] else [])
        for attempt, (dpi, quality) in enumerate(profiles, 1):
            if budget and best.stat().st_size <= budget and (not gray or attempt > 1): break
            progress(f"深度压缩 {attempt}/{len(profiles)} · {dpi} DPI：{target.name}")
            candidate = Path(tmp) / f"gs_{attempt}.pdf"
            gs_compress(baseline, candidate, dpi, quality, gray, progress)
            with open_pdf(candidate) as check:
                if len(check) != len(doc): raise RuntimeError("压缩结果页数不一致。")
            size = candidate.stat().st_size
            logging.info("Compression attempt=%s dpi=%s quality=%s bytes=%s target_bytes=%s", attempt, dpi, quality, size, budget)
            if size < best.stat().st_size or (gray and attempt == 1): best = candidate
        if budget and allow_raster and best.stat().st_size > budget:
            for attempt, (dpi, quality) in enumerate(((96, 50), (72, 35), (60, 28), (48, 20)), 1):
                candidate = Path(tmp) / f"raster_{attempt}.pdf"
                raster_compress(doc, candidate, dpi, quality, gray, progress)
                if candidate.stat().st_size < best.stat().st_size: best = candidate
                if best.stat().st_size <= budget: break
        if budget:
            logging.info("Target result achieved=%s target_bytes=%s actual_bytes=%s selected=%s", best.stat().st_size <= budget, budget, best.stat().st_size, best)
        with best.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024*1024)
    logging.info("Save complete bytes=%s elapsed=%.2fs", target.stat().st_size, time.monotonic()-started)
    return target


def process(paths, output, operation, level=None, split_every=1, ranges="", target_mb=None, gray=False, allow_raster=False, progress=lambda s: None):
    if target_mb is not None and (not isinstance(target_mb, (int, float)) or not 0 < target_mb <= 100000):
        raise ValueError("目标大小必须是大于 0 的数值（最多 100000 MB）。")
    if target_mb and not level: raise ValueError("目标大小模式需要启用输出压缩。")
    if gray and (not level or (level == "无损压缩" and target_mb is None)):
        raise ValueError("灰度转换需要启用有损压缩或目标大小模式。")
    def save(doc, path, fallback=None):
        return save_pdf(doc, path, level, fallback, progress, target_mb, gray, allow_raster)
    paths = [Path(p) for p in paths]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # A separate directory isolates every run, including partially completed jobs.
    run = Path(tempfile.mkdtemp(prefix="PDF_", dir=output))
    results = []
    try:
        if operation == "合并 PDF":
            with pymupdf.open() as merged:
                for index, path in enumerate(paths, 1):
                    progress(f"合并 {index}/{len(paths)}：{path.name}")
                    with open_pdf(path) as source:
                        merged.insert_pdf(source)
                progress("正在保存合并文件…")
                results.append(save(merged, run / "合并结果.pdf"))
        else:
            for index, path in enumerate(paths, 1):
                progress(f"处理 {index}/{len(paths)}：{path.name}")
                with open_pdf(path) as source:
                    if operation == "压缩 PDF":
                        results.append(save(source, run / f"{index:03d}_{path.stem}_压缩.pdf", path))
                    else:
                        if split_every < 1:
                            raise ValueError("每份页数必须至少为 1。")
                        groups = page_groups(ranges, len(source)) if ranges.strip() else [
                            (i, min(i + split_every - 1, len(source) - 1))
                            for i in range(0, len(source), split_every)]
                        for n, (start, end) in enumerate(groups, 1):
                            progress(f"拆分 {path.name}：{n}/{len(groups)}")
                            with pymupdf.open() as part:
                                part.insert_pdf(source, from_page=start, to_page=end)
                                results.append(save(part, run / f"{index:03d}_{path.stem}_{n:03d}_p{start+1}-{end+1}.pdf"))
        return run, results
    except Exception as exc:
        raise RuntimeError(f"{exc}\n本次输出目录：{run}\n已完成的文件：{len(results)} 个。原文件未修改。") from exc

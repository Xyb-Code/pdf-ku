"""Reproducible >100 MiB noisy scan fixture. No customer document is used."""
import json
from pathlib import Path
import random
import tempfile
import time
import pymupdf
from pdf_core import process, open_pdf


def main():
    report = {}
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
        root = Path(folder)
        source = root / "synthetic_scan.pdf"
        rng = random.Random(42)
        table = bytes(224 + i % 32 for i in range(256))
        with pymupdf.open() as doc:
            for n in range(10):
                samples = rng.randbytes(1800 * 2400 * 3).translate(table)
                pix = pymupdf.Pixmap(pymupdf.csRGB, 1800, 2400, samples, False)
                page = doc.new_page(width=540, height=720)
                page.insert_image(page.rect, pixmap=pix)
                for row in range(26):
                    page.insert_text((40, 40 + row * 24), f"Synthetic scanned document - page {n+1} line {row+1}", fontsize=12)
                del samples, pix
            doc.save(source)
        report["fixture"] = "10 synthetic noisy image pages with text; uncompressed source image streams"
        report["input_bytes"] = source.stat().st_size
        for label, options in (("lossless", {"level": "无损压缩"}),
                               ("strong", {"level": "强力压缩 · 小体积"}),
                               ("target_1MiB", {"level": "强力压缩 · 小体积", "target_mb": 1})):
            start = time.monotonic()
            _, files = process([source], root, "压缩 PDF", **options)
            with open_pdf(files[0]) as doc:
                assert len(doc) == 10
                assert all(f"page {n+1} " in page.get_text() for n, page in enumerate(doc))
                assert all(page.get_pixmap().width > 0 for page in doc)
            report[label] = {"output_bytes": files[0].stat().st_size, "seconds": round(time.monotonic()-start, 2), "pages": 10, "text_retained": True}
            print(label, report[label], flush=True)
    Path("compression_benchmark.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__": main()

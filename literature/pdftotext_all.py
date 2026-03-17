#!/usr/bin/env python3
"""Convert all PDFs in the current directory to .txt using `pdftotext`.

Usage:
  cd literature
  python3 pdftotext_all.py

Behavior:
- Finds `*.pdf` in the current working directory (non-recursive).
- Runs: pdftotext <input.pdf> <output.txt>
- Writes `<input>.txt` next to the PDF.

Requirements:
- `pdftotext` must be installed (usually via poppler-utils).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    exe = shutil.which("pdftotext")
    if not exe:
        print("error: `pdftotext` not found. Install poppler-utils (e.g., `sudo apt install poppler-utils`).")
        return 2

    pdfs = sorted(Path(".").glob("*.pdf"))
    if not pdfs:
        print("No .pdf files found in current directory.")
        return 0

    failures: list[tuple[Path, int]] = []

    for pdf in pdfs:
        out_txt = pdf.with_suffix(".txt")
        cmd = [exe, str(pdf), str(out_txt)]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append((pdf, proc.returncode))
            err = (proc.stderr or proc.stdout or "").strip()
            if err:
                print(f"FAILED: {pdf} -> {out_txt} (exit {proc.returncode})\n{err}\n")
            else:
                print(f"FAILED: {pdf} -> {out_txt} (exit {proc.returncode})")
        else:
            print(f"OK: {pdf} -> {out_txt}")

    if failures:
        print(f"\nDone with failures: {len(failures)}/{len(pdfs)}")
        return 1

    print(f"\nDone: {len(pdfs)}/{len(pdfs)} converted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

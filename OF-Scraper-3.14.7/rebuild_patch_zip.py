"""
Rebuild the ZIP_B64 in patch_ofscraper_3.14.7_gui.py from the current source files.
Run from the OF-Scraper-3.14.7 directory.

FILE_COUNT is always rewritten to match the FILES list.

Optional args:
  --patch-id <ID>   Update PATCH_ID in the patch script to this value.
  --sync-root       Also copy the rebuilt patch over ../patch_ofscraper_3.14.7_gui.py
                    (the repo-root copy).
"""
import argparse
import base64
import io
import os
import re
import shutil
import zipfile

_ap = argparse.ArgumentParser()
_ap.add_argument("--patch-id", default=None, help="New PATCH_ID value to write into the patch script.")
_ap.add_argument("--sync-root", action="store_true", help="Also update the repo-root copy of the patch script.")
_args = _ap.parse_args()

PATCH_FILE = os.path.join(os.path.dirname(__file__), "patch_ofscraper_3.14.7_gui.py")
ROOT_PATCH_FILE = os.path.join(os.path.dirname(__file__), "..", "patch_ofscraper_3.14.7_gui.py")
SRC_DIR = os.path.join(os.path.dirname(__file__), "ofscraper")  # OF-Scraper-3.14.7/ofscraper

# Read the patch file as text
with open(PATCH_FILE, "r", encoding="utf-8") as f:
    patch_text = f.read()

# Extract the FILES list
m = re.search(r'^FILES\s*=\s*(\[.*?\])', patch_text, re.MULTILINE | re.DOTALL)
if not m:
    raise RuntimeError("Could not find FILES = [...] in patch script")

files_raw = m.group(1)
files: list = eval(files_raw)
print(f"Found {len(files)} files in FILES list")

patch_text, _n = re.subn(
    r'^FILE_COUNT\s*=\s*\d+',
    f'FILE_COUNT = {len(files)}',
    patch_text,
    count=1,
    flags=re.MULTILINE,
)
if not _n:
    raise RuntimeError("Could not find FILE_COUNT = <n> in patch script")

if _args.patch_id:
    patch_text = re.sub(
        r'^PATCH_ID\s*=\s*["\'][^"\']*["\']',
        f'PATCH_ID = "{_args.patch_id}"',
        patch_text,
        count=1,
        flags=re.MULTILINE,
    )
    _pv_path = os.path.join(os.path.dirname(__file__), "ofscraper", "gui", "patch_version.py")
    with open(_pv_path, "w", encoding="utf-8") as _pv_f:
        _pv_f.write(f'# Auto-updated by rebuild_patch_zip.py — do not edit manually.\nPATCH_ID = "{_args.patch_id}"\n')
    print(f"patch_version.py updated to: {_args.patch_id}")

# Build the zip in memory
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for rel_path in files:
        abs_path = os.path.join(SRC_DIR, rel_path.replace("/", os.sep))
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"Missing source file: {abs_path}")
        with open(abs_path, "rb") as fh:
            data = fh.read()
        zf.writestr(rel_path, data)
        print(f"  Added: {rel_path} ({len(data):,} bytes)")

zip_bytes = buf.getvalue()
b64 = base64.b64encode(zip_bytes).decode("ascii")
print(f"\nNew ZIP size: {len(zip_bytes):,} bytes  B64 length: {len(b64):,} chars")

# Replace the ZIP_B64 line in the patch file (handles both single and double quotes)
# (count matches rather than comparing text: an unchanged rebuild yields identical text)
new_patch, _n = re.subn(
    r'^ZIP_B64\s*=\s*["\'][^"\']*["\']',
    f'ZIP_B64 = "{b64}"',
    patch_text,
    count=1,
    flags=re.MULTILINE,
)
if not _n:
    raise RuntimeError("ZIP_B64 replacement had no effect — pattern not found")

with open(PATCH_FILE, "w", encoding="utf-8") as f:
    f.write(new_patch)

print(f"\nPatch file updated: {PATCH_FILE}")

if _args.sync_root:
    if not os.path.isfile(ROOT_PATCH_FILE):
        raise FileNotFoundError(f"Repo-root patch not found: {os.path.abspath(ROOT_PATCH_FILE)}")
    shutil.copyfile(PATCH_FILE, ROOT_PATCH_FILE)
    print(f"Repo-root copy updated: {os.path.abspath(ROOT_PATCH_FILE)}")

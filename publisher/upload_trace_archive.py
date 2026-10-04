#!/usr/bin/env python3
"""Upload one trace archive to the shared FONDA folder in HU-Box.

No HU-Box account is needed: the file goes through the folder's upload link.
The link only takes files in, so the archive is not public after the upload.
A small note file with the address of the run is uploaded beside it; the
folder's owner uses it to create the public link and add it to the run in VIVO.

Usage: upload_trace_archive.py ARCHIVE [--run-uri URI] [--check]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple


DEFAULT_UPLOAD_LINK = "https://box.hu-berlin.de/u/d/5c2fded0afbf4e2c95da/"
# Folder of that link in its HU-Box library; used when the link's page does not name it.
DEFAULT_PARENT_DIR = "/Traces of FONDA Workflows"
LINK_RE = re.compile(r"^(https?://[^/\s]+)/u/d/([0-9a-f]{8,64})/?$")
NOTE_SUFFIX = ".run.json"
USER_AGENT = "fonda-kubernetes-vivo-publisher/1.0"
TIMEOUT_SECONDS = 120


class UploadError(RuntimeError):
    """The shared folder did not take the file."""


def fetch(url: str, data=None, headers: Optional[Dict[str, str]] = None, what: str = "") -> bytes:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise UploadError(f"{what}: HU-Box answered HTTP {exc.code}: {body[:300] or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UploadError(f"{what}: HU-Box could not be reached: {exc}") from exc


def parse_link(link: str) -> Tuple[str, str]:
    match = LINK_RE.match(link.strip())
    if not match:
        raise UploadError("the upload link must look like https://box.hu-berlin.de/u/d/<letters and digits>/")
    return match.group(1), match.group(2)


def upload_address(server: str, token: str) -> str:
    """Ask HU-Box where files for this upload link are sent to."""
    body = fetch(f"{server}/api/v2.1/upload-links/{token}/upload/", headers={"Accept": "application/json"},
                 what="asking for the upload address")
    try:
        address = json.loads(body)["upload_link"]
    except (ValueError, KeyError, TypeError) as exc:
        raise UploadError(f"asking for the upload address: unexpected answer {body[:200]!r}") from exc
    if not re.match(r"^https?://[^\s]+$", str(address)):
        raise UploadError(f"asking for the upload address: unexpected answer {body[:200]!r}")
    return address


def folder_of_link(server: str, token: str) -> Dict[str, object]:
    """Read the folder behind the upload link from the link's own page."""
    page = fetch(f"{server}/u/d/{token}/", what="opening the upload link").decode("utf-8", errors="replace")
    block = re.search(r"uploadLink\s*=\s*\{(.*?)\}\s*;", page, re.S)
    text = block.group(1) if block else page

    def value(name: str) -> Optional[str]:
        found = re.search(name + r"""\s*:\s*(['"])((?:\\.|(?!\1).)*)\1""", text)
        if not found:
            return None
        raw = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), found.group(2))
        return re.sub(r"\\(.)", r"\1", raw)

    limit = re.search(r"maxUploadFileSize\s*:\s*(-?\d+)", text)
    return {"path": value("path"), "name": value("dirName"),
            "no_quota": bool(re.search(r"noQuota\s*:\s*true", text)),
            "max_bytes": int(limit.group(1)) if limit and int(limit.group(1)) > 0 else None}


def post_file(address: str, parent_dir: str, name: str, source: Path) -> Dict[str, object]:
    """Send one file as a multipart form; the form is written to disk first, so large files need no memory."""
    boundary = "----fonda" + uuid.uuid4().hex
    with tempfile.TemporaryFile() as form:
        form.write((f"--{boundary}\r\nContent-Disposition: form-data; name=\"parent_dir\"\r\n\r\n{parent_dir}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                    "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8"))
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                form.write(chunk)
        form.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        length = form.tell()
        form.seek(0)
        body = fetch(address + "?ret-json=1", data=form,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(length)},
                     what=f"uploading {name}")
    try:
        stored = json.loads(body)[0]
        return {"name": str(stored["name"]), "size": int(stored["size"])}
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise UploadError(f"uploading {name}: unexpected answer {body[:200]!r}") from exc


def run_uri_in_archive(archive: Path) -> str:
    """The run address that the archive scripts write to MANIFEST.json (vivo_run_uri)."""
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as bundle:
                names = [n for n in bundle.namelist() if n.lstrip("./") == "MANIFEST.json"]
                manifest = bundle.read(names[0]) if names else None
        else:
            with tarfile.open(archive) as bundle:
                members = [m for m in bundle.getmembers() if m.name.lstrip("./") == "MANIFEST.json" and m.isfile()]
                manifest = bundle.extractfile(members[0]).read() if members else None
        return str(json.loads(manifest).get("vivo_run_uri", "")) if manifest else ""
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile, AttributeError):
        return ""


def check_run_uri(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or re.search(r"[\s<>\"{}|^`\\]", value):
        raise UploadError("the run address must be the address of the run in VIVO, for example "
                          "http://example.org/vivo-import/run-metadata/run/...")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", nargs="?", type=Path, help="The reviewed trace archive (.tar.gz or .zip)")
    parser.add_argument("--run-uri", default="", help="Address of the run in VIVO; read from the archive's "
                        "MANIFEST.json when the archive was made by the archive scripts")
    parser.add_argument("--link", default=os.environ.get("HU_BOX_UPLOAD_LINK", "") or DEFAULT_UPLOAD_LINK,
                        help="Upload link of the shared folder (default: the FONDA folder, or HU_BOX_UPLOAD_LINK)")
    parser.add_argument("--check", action="store_true", help="Only ask HU-Box whether the link works; upload nothing")
    args = parser.parse_args(argv)
    if not args.check and args.archive is None:
        parser.error("name the archive to upload, or use --check")
    return args


def main(argv=None) -> int:
    args = build_args(argv)
    try:
        server, token = parse_link(args.link)
        address = upload_address(server, token)     # also tells whether the link still exists
        try:
            folder = folder_of_link(server, token)
        except UploadError:
            folder = {"path": None, "name": None, "no_quota": False, "max_bytes": None}
        parent_dir = (os.environ.get("HU_BOX_UPLOAD_PARENT_DIR", "") or folder["path"]
                      or (DEFAULT_PARENT_DIR if args.link.strip() == DEFAULT_UPLOAD_LINK else ""))
        if not parent_dir:
            raise UploadError("could not read the folder of the upload link from its page; set "
                              "HU_BOX_UPLOAD_PARENT_DIR to the folder's path in its HU-Box library")
        if folder["no_quota"]:
            raise UploadError("the shared folder is full; write to yagmur.kati@hu-berlin.de")
        print(f"Shared folder: {folder['name'] or parent_dir} ({server})")
        if args.check:
            limit = folder["max_bytes"]
            print("The upload link works." + (f" Largest file: {limit / 1e6:.0f} MB." if limit else ""))
            return 0

        archive = args.archive
        if not archive.is_file():
            raise UploadError(f"no such file: {archive}")
        size = archive.stat().st_size
        if size == 0:
            raise UploadError(f"the file is empty: {archive}")
        if folder["max_bytes"] and size > folder["max_bytes"]:
            raise UploadError(f"the file has {size / 1e6:.0f} MB; the folder takes at most "
                              f"{folder['max_bytes'] / 1e6:.0f} MB per file")
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", archive.name):
            raise UploadError("the file name may contain only letters, digits, dot, underscore and hyphen")
        run_uri = args.run_uri or run_uri_in_archive(archive)
        if not run_uri:
            raise UploadError("the archive does not name its run; add --run-uri with the address of the run in VIVO")
        run_uri = check_run_uri(run_uri)

        stored = post_file(address, parent_dir, archive.name, archive)
        if stored["size"] != size:
            raise UploadError(f"HU-Box stored {stored['size']} of {size} bytes of {archive.name}; upload it again")
        note = {"archive": stored["name"], "run_uri": run_uri, "size_bytes": size, "sha256": sha256_file(archive),
                "uploaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with tempfile.TemporaryDirectory() as directory:
            note_file = Path(directory) / (stored["name"] + NOTE_SUFFIX)
            note_file.write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
            post_file(upload_address(server, token), parent_dir, note_file.name, note_file)
    except UploadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Uploaded: {stored['name']} ({size} bytes)")
    print(f"Run:      {run_uri}")
    print("The archive is not public yet. The administrator creates its public link and adds it to the run")
    print("in VIVO as \"trace archive\"; nothing more is needed from you.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

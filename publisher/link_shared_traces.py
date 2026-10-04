#!/usr/bin/env python3
"""Make the trace archives in the shared HU-Box folder public and add them to their runs in VIVO.

For the owner of the shared folder. Members without an HU-Box account upload
archives with upload_trace_archive.py; each archive comes with a note file
(<archive>.run.json) that names its run. For every archive that has no public
link yet, this command shows the archive and the run, asks, creates the HU-Box
share link of the file and adds it to the run as rm:traceArchive.

Usage: link_shared_traces.py [--dry-run] [--yes] [--relink ARCHIVE]

Settings (written by scripts/configure-hu-box.sh, read from the environment):
  HU_BOX_SERVER_URL, HU_BOX_REPOSITORY_ID, HU_BOX_API_TOKEN_FILE
  HU_BOX_SHARED_DIR   folder of the upload link in that library
"""

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_vivo import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_GRAPH,
    PublishError,
    publish_with_retries,
    read_secret_file,
    validate_absolute_iri,
)

NOTE_SUFFIX = ".run.json"
DEFAULT_SHARED_DIR = "/Traces of FONDA Workflows"
ONTOLOGY = "http://example.org/ontology/run-metadata#"
USER_AGENT = "fonda-kubernetes-vivo-publisher/1.0"
MAX_NOTE_BYTES = 10_000


class LinkError(RuntimeError):
    """HU-Box or VIVO did not do what was asked."""


class HuBox:
    def __init__(self, server: str, repo_id: str, token: str, shared_dir: str):
        self.server, self.repo_id, self.token = server.rstrip("/"), repo_id, token
        self.shared_dir = "/" + shared_dir.strip("/")

    def call(self, url: str, body: Optional[dict] = None, what: str = "", with_token: bool = True) -> bytes:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if with_token:
            headers["Authorization"] = f"Token {self.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace").strip()
            raise LinkError(f"{what}: HU-Box answered HTTP {exc.code}: {text[:300] or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LinkError(f"{what}: HU-Box could not be reached: {exc}") from exc

    def path(self, name: str) -> str:
        return f"{self.shared_dir}/{name}"

    def files(self) -> Dict[str, int]:
        query = urllib.parse.urlencode({"p": self.shared_dir})
        entries = json.loads(self.call(f"{self.server}/api2/repos/{self.repo_id}/dir/?{query}", what="listing the folder"))
        return {str(e["name"]): int(e.get("size", 0)) for e in entries if e.get("type") == "file"}

    def read(self, name: str) -> bytes:
        query = urllib.parse.urlencode({"p": self.path(name)})
        address = json.loads(self.call(f"{self.server}/api2/repos/{self.repo_id}/file/?{query}", what=f"reading {name}"))
        return self.call(str(address), what=f"reading {name}", with_token=False)

    def links(self, name: str) -> List[str]:
        query = urllib.parse.urlencode({"repo_id": self.repo_id, "path": self.path(name)})
        found = json.loads(self.call(f"{self.server}/api/v2.1/share-links/?{query}", what=f"looking up the links of {name}"))
        return [str(e["link"]) for e in found if e.get("link") and not e.get("is_expired")]

    def share(self, name: str) -> str:
        body = {"repo_id": self.repo_id, "path": self.path(name), "permissions": {"can_edit": False, "can_download": True}}
        link = json.loads(self.call(f"{self.server}/api/v2.1/share-links/", body=body, what=f"sharing {name}")).get("link", "")
        if not re.match(r'^https?://[^\s"<>]+$', str(link)):
            raise LinkError(f"sharing {name}: HU-Box returned no link")
        return str(link)


def read_note(box: HuBox, note_name: str, files: Dict[str, int]) -> Optional[dict]:
    """Return the checked note of one upload, or None with the reason printed."""
    archive = note_name[: -len(NOTE_SUFFIX)]
    if files[note_name] > MAX_NOTE_BYTES:
        print(f"  skipped {note_name}: the note file is too large")
        return None
    try:
        note = json.loads(box.read(note_name))
        run_uri = str(note["run_uri"])
        validate_absolute_iri(run_uri, "run address")
        if re.search(r"\s", run_uri) or not run_uri.startswith(("http://", "https://")):
            raise PublishError("run address is not an http(s) address")
    except (ValueError, KeyError, TypeError, PublishError) as exc:
        print(f"  skipped {note_name}: the note cannot be used ({exc})")
        return None
    if note.get("archive") != archive or archive not in files:
        print(f"  skipped {note_name}: its archive {archive} is not in the folder")
        return None
    if int(note.get("size_bytes", -1)) != files[archive]:
        print(f"  skipped {archive}: its size in HU-Box differs from the note (upload not complete?)")
        return None
    return {"archive": archive, "run_uri": run_uri, "size": files[archive], "sha256": str(note.get("sha256", ""))}


def sparql_ask(endpoint: str, email: str, password: str, pattern: str) -> Optional[bool]:
    """Ask VIVO a yes/no question; None when the query address cannot be used."""
    query_endpoint = endpoint.replace("sparqlUpdate", "sparqlQuery")
    payload = urllib.parse.urlencode({"email": email, "password": password,
                                      "query": f"PREFIX rm: <{ONTOLOGY}>\nASK {{ {pattern} }}"}).encode("utf-8")
    request = urllib.request.Request(query_endpoint, data=payload, headers={
        "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        return bool(json.loads(text)["boolean"])
    except (ValueError, KeyError, TypeError):
        word = text.strip().lower()
        return True if word in {"true", "yes"} else False if word in {"false", "no"} else None


def add_link_update(run_uri: str, link: str, graph: str) -> str:
    """Add the link only when the run exists in VIVO."""
    validate_absolute_iri(run_uri, "run address")
    validate_absolute_iri(link, "link")
    validate_absolute_iri(graph, "graph")
    return (f"PREFIX rm: <{ONTOLOGY}>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
            f"INSERT {{ GRAPH <{graph}> {{ <{run_uri}> rm:traceArchive \"{link}\"^^xsd:anyURI }} }}\n"
            f"WHERE {{ GRAPH <{graph}> {{ <{run_uri}> a rm:RunMetadata }} }}\n")


def build_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="List the uploads; change nothing")
    parser.add_argument("--yes", action="store_true", help="Do not ask before each archive")
    parser.add_argument("--relink", action="append", default=[], metavar="ARCHIVE",
                        help="Add the existing public link of this archive to its run again (repeatable)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument("--email-file", type=Path, help="File with the VIVO e-mail address (default: ask)")
    parser.add_argument("--password-file", type=Path, help="File with the VIVO password (default: ask, hidden)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = build_args(argv)
    try:
        repo_id = os.environ.get("HU_BOX_REPOSITORY_ID", "")
        token_file = Path(os.environ.get("HU_BOX_API_TOKEN_FILE", "") or Path.home() / ".config/fonda/hu-box-api-token")
        if not re.match(r"^[0-9a-fA-F-]{36}$", repo_id) or not token_file.is_file():
            raise LinkError("HU-Box is not set up on this computer; run scripts/configure-hu-box.sh and choose "
                            "the library that holds the shared folder")
        box = HuBox(os.environ.get("HU_BOX_SERVER_URL", "") or "https://box.hu-berlin.de", repo_id,
                    token_file.read_text(encoding="utf-8").strip(),
                    os.environ.get("HU_BOX_SHARED_DIR", "") or DEFAULT_SHARED_DIR)
        files = box.files()
        notes = sorted(name for name in files if name.endswith(NOTE_SUFFIX))
        print(f"Shared folder {box.shared_dir}: {len(files) - len(notes)} file(s), {len(notes)} with a run note.")
        without_note = sorted(n for n in files if not n.endswith(NOTE_SUFFIX) and n + NOTE_SUFFIX not in files)
        for name in without_note:
            print(f"  no run note: {name} (uploaded in the browser; link it by hand)")

        pending = []
        for note_name in notes:
            note = read_note(box, note_name, files)
            if not note:
                continue
            existing = box.links(note["archive"])
            if existing and note["archive"] not in args.relink:
                print(f"  already public: {note['archive']}")
                continue
            note["link"] = existing[0] if existing else ""
            pending.append(note)
        if not pending:
            print("Nothing to do.")
            return 0
        if args.dry_run:
            for note in pending:
                print(f"  to do: {note['archive']} ({note['size']} bytes) -> {note['run_uri']}")
            print("Dry run: nothing was changed.")
            return 0

        email = read_secret_file(args.email_file, "VIVO e-mail") if args.email_file else input("VIVO e-mail: ").strip()
        password = (read_secret_file(args.password_file, "VIVO password") if args.password_file
                    else getpass.getpass("VIVO password (hidden): "))
        failed = 0
        for note in pending:
            archive, run_uri = note["archive"], note["run_uri"]
            print(f"\nArchive: {archive} ({note['size']} bytes)\nRun:     {run_uri}")
            exists = sparql_ask(args.endpoint, email, password, f"<{run_uri}> a rm:RunMetadata")
            if exists is False:
                print("  skipped: VIVO has no run with this address")
                failed += 1
                continue
            if not args.yes and input("  Make this archive public and add it to the run? [y/N] ").strip().lower() != "y":
                print("  left as it is")
                continue
            link = note["link"] or box.share(archive)
            print(f"  public link: {link}")
            publish_with_retries(args.endpoint, email, password, add_link_update(run_uri, link, args.graph), 3, 5.0, 120)
            added = sparql_ask(args.endpoint, email, password, f"<{run_uri}> rm:traceArchive ?link . FILTER(STR(?link) = \"{link}\")")
            if added is False:
                print(f"  NOT added to VIVO. Try again with: --relink {archive}")
                failed += 1
            else:
                print("  added to the run in VIVO" + ("" if added else " (could not be checked: open the run page)"))
        return 1 if failed else 0
    except (LinkError, PublishError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Review or publish one validated RNA-seq/RAPL run using the shared transport."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "publisher"))
from publish_vivo import (DEFAULT_ENDPOINT, DEFAULT_GRAPH, run_owned_resource_iris,
                          turtle_to_insert_update, post_update_once)


def check_absent(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise RuntimeError(f"Cannot check existing VIVO record: HTTP {exc.code}") from exc
    raise RuntimeError(f"VIVO record already exists (HTTP {status}); refusing to change it: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Collector output directory")
    parser.add_argument("--publish", action="store_true", help="Send reviewed metadata; default is dry run")
    parser.add_argument("--credentials-secret", help="Optional Kubernetes secret with email/password keys")
    args = parser.parse_args()
    summary = json.loads((args.directory / "validation.json").read_text())
    ttl = (args.directory / "run.ttl").read_text()
    digest = hashlib.sha256(ttl.encode()).hexdigest()
    if summary["status"] != "validated" or summary.get("ttl_sha256") != digest:
        raise RuntimeError("Metadata no longer matches the validated collection")
    if hashlib.sha256((args.directory / "trace-archive.tar.gz").read_bytes()).hexdigest() != summary["archive_sha256"]:
        raise RuntimeError("Evidence archive checksum mismatch")
    owned = run_owned_resource_iris(ttl)
    if owned[0] != summary["run_uri"]:
        raise RuntimeError("Run identity does not match validation")
    update = turtle_to_insert_update(ttl, DEFAULT_GRAPH)
    url = "https://vivo-fonda.hu-berlin.de/vivo/individual?" + urllib.parse.urlencode({"uri": owned[0]})
    if not args.publish:
        print(f"Validated dry run: {owned[0]}\nTTL SHA-256: {digest}\nOnly metadata would be uploaded; the archive stays local.")
        return
    historical = json.loads((HERE / "publication-summary.json").read_text())
    if summary["session_id"] == historical["nextflow_session_id"]:
        raise RuntimeError("This historical session is already published: " + historical["run_uri"])
    receipt_path = args.directory / "publication-receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("ttl_sha256") == digest and 200 <= receipt.get("http_status", 0) < 300:
            print("Successful receipt already exists: " + receipt["url"])
            return
        raise RuntimeError("An unsuccessful or different receipt exists; preserve it and review the VIVO page")
    if (args.directory / "publication-attempt.json").exists():
        raise RuntimeError("A prior publication attempt needs review before any further write")
    # Refuse existing run resources before an insert. Never delete or replace.
    for resource in owned:
        check_absent("https://vivo-fonda.hu-berlin.de/vivo/individual?" + urllib.parse.urlencode({"uri": resource}))
    if args.credentials_secret:
        result = subprocess.check_output(["kubectl", "-n", summary["namespace"], "get", "secret",
                                          args.credentials_secret, "-o", "json"])
        data = json.loads(result)["data"]
        email, password = (base64.b64decode(data[k]).decode().strip() for k in ("email", "password"))
    else:
        email = input("VIVO publisher email: ").strip()
        password = getpass.getpass("VIVO publisher password: ")
    if not email or not password:
        raise RuntimeError("Empty publisher credentials")
    # Keep a durable attempt marker even if the network response is uncertain.
    with (args.directory / "publication-attempt.json").open("x") as stream:
        json.dump(dict(run_uri=owned[0], endpoint=DEFAULT_ENDPOINT, graph=DEFAULT_GRAPH,
                       ttl_sha256=digest, started_at=datetime.now(timezone.utc).isoformat()), stream, indent=2)
    status, response = post_update_once(DEFAULT_ENDPOINT, email, password, update, 120)
    receipt = dict(run_uri=owned[0], url=url, endpoint=DEFAULT_ENDPOINT, graph=DEFAULT_GRAPH,
                   ttl_sha256=digest, http_status=status, published_at=datetime.now(timezone.utc).isoformat())
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
    if not 200 <= status < 300:
        raise RuntimeError(f"VIVO returned HTTP {status}; retain the attempt and receipt for review")
    with urllib.request.urlopen(url, timeout=60) as page:
        visible = page.status == 200 and b"Succeeded" in page.read()
    with (args.directory / "page-verification.json").open("x") as stream:
        json.dump(dict(url=url, succeeded_visible=visible), stream, indent=2)
    if not visible:
        raise RuntimeError("Update accepted, but successful status is not yet visible; check the VIVO page before retrying")
    print("Published and page verified: " + url)


if __name__ == "__main__":
    main()

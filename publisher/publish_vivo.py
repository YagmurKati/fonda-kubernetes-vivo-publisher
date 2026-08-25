#!/usr/bin/env python3
"""Publish collector-generated Turtle to VIVO through its SPARQL Update API."""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple


DEFAULT_ENDPOINT = "https://vivo-fonda.hu-berlin.de/vivo/api/sparqlUpdate"
DEFAULT_GRAPH = "http://vitro.mannlib.cornell.edu/default/vitro-kb-2"

PREFIX_RE = re.compile(
    r"^\s*@prefix\s+([A-Za-z][A-Za-z0-9_-]*)?:\s*"
    r"<([^<>\"{}|^`\\\x00-\x20]+)>\s*\.\s*(?:#.*)?$",
    re.IGNORECASE,
)
BLANK_NODE_LABEL_RE = re.compile(r"(^|[\s;,])_:[A-Za-z0-9_]", re.MULTILINE)
ANONYMOUS_NODE_RE = re.compile(r"(^|[\s;,])\[(?=\s|\])", re.MULTILINE)


class PublishError(RuntimeError):
    """A permanent or exhausted VIVO publication failure."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_absolute_iri(value: str, label: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https", "urn"}:
        raise PublishError(f"{label} must be an absolute HTTP(S) or URN IRI")
    if any(character in value for character in '<>"{}|^`\\'):
        raise PublishError(f"{label} contains a character that is unsafe in SPARQL")


def turtle_to_insert_update(turtle: str, graph: str) -> str:
    """Convert the collector's named-resource Turtle to SPARQL INSERT DATA."""
    validate_absolute_iri(graph, "graph")
    prefixes = []
    body_lines = []
    body_started = False

    for line_number, line in enumerate(turtle.splitlines(), start=1):
        stripped = line.strip()
        if not body_started and (not stripped or stripped.startswith("#")):
            continue
        prefix_match = PREFIX_RE.fullmatch(line)
        if not body_started and prefix_match:
            prefix_name = prefix_match.group(1) or ""
            prefix_iri = prefix_match.group(2)
            validate_absolute_iri(prefix_iri, f"prefix on line {line_number}")
            prefixes.append(f"PREFIX {prefix_name}: <{prefix_iri}>")
            continue
        body_started = True
        if stripped.lower().startswith(("@prefix", "@base")):
            raise PublishError(
                f"unsupported Turtle directive on line {line_number}"
            )
        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not prefixes:
        raise PublishError("the Turtle file has no @prefix declarations")
    if not body:
        raise PublishError("the Turtle file contains no RDF statements")
    if BLANK_NODE_LABEL_RE.search(body) or ANONYMOUS_NODE_RE.search(body):
        raise PublishError(
            "blank nodes are not allowed because retries would create new identities"
        )

    return (
        "\n".join(prefixes)
        + "\n\nINSERT DATA {\n"
        + f"  GRAPH <{graph}> {{\n"
        + body
        + "\n  }\n}\n"
    )


def read_secret_file(path: Path, label: str) -> str:
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as exc:
        raise PublishError(f"could not read {label} file {path}: {exc}") from exc
    if not value:
        raise PublishError(f"{label} file {path} is empty")
    return value


def load_receipt(path: Path) -> Optional[Dict[str, object]]:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def receipt_matches(
    path: Path, ttl_sha256: str, endpoint: str, graph: str
) -> bool:
    receipt = load_receipt(path)
    return bool(
        receipt
        and receipt.get("ttl_sha256") == ttl_sha256
        and receipt.get("endpoint") == endpoint
        and receipt.get("graph") == graph
        and receipt.get("http_status") in range(200, 300)
    )


def write_receipt_atomic(path: Path, receipt: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def post_update_once(
    endpoint: str,
    email: str,
    password: str,
    update: str,
    timeout_seconds: int,
) -> Tuple[int, str]:
    payload = urllib.parse.urlencode(
        {"email": email, "password": password, "update": update}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html, text/plain;q=0.9, */*;q=0.1",
            "User-Agent": "fonda-kubernetes-vivo-publisher/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, response.read().decode(
                "utf-8", errors="replace"
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def publish_with_retries(
    endpoint: str,
    email: str,
    password: str,
    update: str,
    max_attempts: int,
    retry_delay_seconds: float,
    timeout_seconds: int,
) -> Tuple[int, str, int]:
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            status, response_text = post_update_once(
                endpoint, email, password, update, timeout_seconds
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status = 0
            response_text = ""
            last_error = str(exc)
        else:
            if 200 <= status < 300:
                return status, response_text, attempt
            last_error = response_text.strip() or f"HTTP {status}"
            if status not in transient_statuses:
                raise PublishError(
                    f"VIVO rejected the update with HTTP {status}: "
                    f"{last_error[:500]}"
                )

        if attempt < max_attempts:
            delay = retry_delay_seconds * attempt
            print(
                f"VIVO publication attempt {attempt} failed; retrying in "
                f"{delay:g} seconds.",
                file=sys.stderr,
            )
            time.sleep(delay)

    raise PublishError(
        f"VIVO publication failed after {max_attempts} attempts: "
        f"{last_error[:500]}"
    )


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish one collector-generated TTL file to the VIVO ABox graph."
        )
    )
    parser.add_argument("ttl_file", type=Path)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument("--email-file", type=Path, default=None)
    parser.add_argument("--password-file", type=Path, default=None)
    parser.add_argument("--receipt-file", type=Path, default=None)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--retry-delay-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and prepare the update without contacting VIVO.",
    )
    return parser.parse_args()


def main() -> None:
    args = build_args()
    if args.max_attempts < 1:
        raise PublishError("--max-attempts must be at least 1")
    if args.retry_delay_seconds < 0:
        raise PublishError("--retry-delay-seconds cannot be negative")
    if args.timeout_seconds < 1:
        raise PublishError("--timeout-seconds must be at least 1")

    endpoint_parts = urllib.parse.urlparse(args.endpoint)
    if endpoint_parts.scheme != "https":
        raise PublishError("the VIVO endpoint must use HTTPS")
    validate_absolute_iri(args.endpoint, "endpoint")

    try:
        turtle = args.ttl_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublishError(f"could not read TTL file {args.ttl_file}: {exc}") from exc
    update = turtle_to_insert_update(turtle, args.graph)
    ttl_sha256 = sha256_text(turtle)
    receipt_path = args.receipt_file or args.ttl_file.with_suffix(
        ".published.json"
    )

    if args.dry_run:
        print(f"TTL validated: {args.ttl_file}")
        print(f"TTL SHA-256: {ttl_sha256}")
        print(f"Target graph: {args.graph}")
        return

    if not args.force and receipt_matches(
        receipt_path, ttl_sha256, args.endpoint, args.graph
    ):
        print(f"Already published: {args.ttl_file}")
        print(f"Receipt: {receipt_path}")
        return

    if args.email_file is None or args.password_file is None:
        raise PublishError(
            "--email-file and --password-file are required unless --dry-run is used"
        )
    email = read_secret_file(args.email_file, "email")
    password = read_secret_file(args.password_file, "password")
    if "@" not in email:
        raise PublishError("the VIVO email credential is not a valid email address")

    status, response_text, attempts = publish_with_retries(
        endpoint=args.endpoint,
        email=email,
        password=password,
        update=update,
        max_attempts=args.max_attempts,
        retry_delay_seconds=args.retry_delay_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    receipt = {
        "attempts": attempts,
        "endpoint": args.endpoint,
        "graph": args.graph,
        "http_status": status,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "response_excerpt": response_text.strip()[:500],
        "ttl_file": str(args.ttl_file),
        "ttl_sha256": ttl_sha256,
    }
    write_receipt_atomic(receipt_path, receipt)
    print(f"Published TTL to VIVO: {args.ttl_file}")
    print(f"HTTP {status}")
    print(f"Receipt: {receipt_path}")


if __name__ == "__main__":
    try:
        main()
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

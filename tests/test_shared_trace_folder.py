import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.parse
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "publisher"))
sys.path.insert(0, str(ROOT / "tests"))
import link_shared_traces as linker  # noqa: E402
import upload_trace_archive as uploader  # noqa: E402

TOKEN = "5c2fded0afbf4e2c95da"
REPO = "e51f80a8-f1a3-4dfd-b73f-48da07650b03"
FOLDER = "/Traces of FONDA Workflows/"
RUN = "http://example.org/vivo-import/run-metadata/run/yagmur-geoflow-test-2026-10-04t10-00-00"
GRAPH = "http://vitro.mannlib.cornell.edu/default/vitro-kb-2"


class FakeServices(BaseHTTPRequestHandler):
    """HU-Box (Seafile) upload link, folder and share links, and VIVO's two SPARQL addresses."""

    files = {}          # name -> bytes, the content of the shared folder
    links = {}          # name -> public link
    vivo_runs = set()
    vivo_links = set()  # (run, link)
    updates = []
    posts = []

    @classmethod
    def reset(cls):
        cls.files, cls.links, cls.vivo_runs, cls.vivo_links, cls.updates, cls.posts = {}, {}, {RUN}, set(), [], []

    def log_message(self, *args):
        pass

    def _send(self, body, status=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _base(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def _authorized(self):
        return self.headers.get("Authorization") == "Token box-token"

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == f"/u/d/{TOKEN}/":
            page = ("<html><script>window.uploadLink = {\n  dirName: 'Traces of FONDA Workflows',\n"
                    "  sharedBy: { name: 'Owner', avatar: '<img src=\"a.png\">' },\n  noQuota: false,\n"
                    f"  maxUploadFileSize: -1,\n  token: '{TOKEN}',\n  repoID: '{REPO}',\n"
                    "  path: '/Traces of FONDA Workflows/'\n};</script></html>")
            self._send(page.encode())
        elif url.path == f"/api/v2.1/upload-links/{TOKEN}/upload/":
            self._send({"upload_link": f"{self._base()}/seafhttp/upload-api/access-1"})
        elif url.path.startswith("/api/v2.1/upload-links/"):
            self._send({"error_msg": "token not found."}, 404)
        elif url.path == f"/api2/repos/{REPO}/dir/" and self._authorized():
            if query["p"][0].strip("/") != FOLDER.strip("/"):
                return self._send({"error_msg": "Folder not found."}, 404)
            self._send([{"type": "file", "name": n, "size": len(c)} for n, c in sorted(self.files.items())])
        elif url.path == f"/api2/repos/{REPO}/file/" and self._authorized():
            name = query["p"][0].rsplit("/", 1)[-1]
            self._send(f"{self._base()}/seafhttp/files/x/{urllib.parse.quote(name)}")
        elif url.path.startswith("/seafhttp/files/x/"):
            self._send(self.files[urllib.parse.unquote(url.path.rsplit("/", 1)[-1])])
        elif url.path == "/api/v2.1/share-links/" and self._authorized():
            name = query["path"][0].rsplit("/", 1)[-1]
            self._send([{"link": self.links[name], "is_expired": False}] if name in self.links else [])
        else:
            self._send({"error_msg": "not found"}, 404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        url = urllib.parse.urlparse(self.path)
        FakeServices.posts.append(url.path)
        if url.path == "/seafhttp/upload-api/access-1":
            boundary = self.headers["Content-Type"].split("boundary=")[1].encode()
            fields = {}
            for part in body.split(b"--" + boundary)[1:-1]:
                head, _, content = part.partition(b"\r\n\r\n")
                name = re.search(rb'name="([^"]+)"', head).group(1).decode()
                filename = re.search(rb'filename="([^"]+)"', head)
                fields[name] = (filename.group(1).decode() if filename else None, content[:-2])
            if fields["parent_dir"][1].decode().strip("/") != FOLDER.strip("/"):
                return self._send(b"Permission denied.", 403)
            name, content = fields["file"]
            stored, number = name, 0
            while stored in self.files:      # HU-Box keeps both files and renames the new one
                number += 1
                stem, dot, ext = name.partition(".")
                stored = f"{stem} ({number}){dot}{ext}"
            FakeServices.files[stored] = content
            self._send([{"name": stored, "id": "0" * 40, "size": len(content)}])
        elif url.path == "/api/v2.1/share-links/" and self._authorized():
            path = json.loads(body)["path"]
            name = path.rsplit("/", 1)[-1]
            if name not in self.files:        # a folder: refused, as HU-Box does
                return self._send({"error_msg": "Permission denied."}, 403)
            FakeServices.links[name] = f"{self._base()}/f/{hashlib.md5(name.encode()).hexdigest()[:10]}/"
            self._send({"link": self.links[name]})
        elif url.path == "/vivo/api/sparqlUpdate":
            form = urllib.parse.parse_qs(body.decode())
            update = form["update"][0]
            FakeServices.updates.append(update)
            found = re.search(r'<([^>]+)> rm:traceArchive "([^"]+)"\^\^xsd:anyURI', update)
            guard = re.search(r"WHERE \{ GRAPH <[^>]+> \{ <([^>]+)> a rm:RunMetadata \} \}", update)
            if found and guard and guard.group(1) in self.vivo_runs:
                FakeServices.vivo_links.add((found.group(1), found.group(2)))
            self._send(b"<html>200 SPARQL update accepted.</html>")
        elif url.path == "/vivo/api/sparqlQuery":
            query = urllib.parse.parse_qs(body.decode())["query"][0]
            run = re.search(r"ASK \{ <([^>]+)>", query).group(1)
            if "rm:traceArchive" in query:
                link = re.search(r'STR\(\?link\) = "([^"]+)"', query).group(1)
                self._send({"boolean": (run, link) in self.vivo_links})
            else:
                self._send({"boolean": run in self.vivo_runs})
        else:
            self._send({"error_msg": "not found"}, 404)


class Base(unittest.TestCase):
    def setUp(self):
        FakeServices.reset()
        self.server = HTTPServer(("127.0.0.1", 0), FakeServices)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.upload_link = f"{self.base}/u/d/{TOKEN}/"
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def archive(self, name="my-run-01-trace-bundle-20261004T100000Z.tar.gz", run=RUN, manifest=True):
        path = self.dir / name
        with tarfile.open(path, "w:gz") as bundle:
            entries = {"./nextflow/trace.txt": b"task_id\thash\n1\taa/bb\n"}
            if manifest:
                entries["./MANIFEST.json"] = json.dumps({"vivo_run_uri": run}).encode()
            for member, content in entries.items():
                info = tarfile.TarInfo(member)
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
        return path

    def upload(self, *args, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}), redirect_stdout(out), redirect_stderr(err):
            os.environ.pop("HU_BOX_UPLOAD_PARENT_DIR", None) if not env else None
            code = uploader.main([*map(str, args), "--link", self.upload_link])
        return code, out.getvalue(), err.getvalue()


class UploadTests(Base):
    def test_check_asks_hu_box_and_uploads_nothing(self):
        code, out, err = self.upload("--check")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Shared folder: Traces of FONDA Workflows", out)
        self.assertIn("The upload link works.", out)
        self.assertEqual(FakeServices.posts, [])

    def test_archive_and_its_run_note_arrive_in_the_folder(self):
        archive = self.archive()
        code, out, err = self.upload(archive)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(FakeServices.files[archive.name], archive.read_bytes())
        note = json.loads(FakeServices.files[archive.name + ".run.json"])
        self.assertEqual(note["archive"], archive.name)
        self.assertEqual(note["run_uri"], RUN)
        self.assertEqual(note["size_bytes"], archive.stat().st_size)
        self.assertEqual(note["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertIn(f"Uploaded: {archive.name}", out)
        self.assertIn("not public yet", out)
        self.assertEqual(FakeServices.links, {})

    def test_a_second_upload_of_the_same_name_keeps_both_and_notes_the_stored_name(self):
        archive = self.archive()
        self.upload(archive)
        code, out, _ = self.upload(archive)
        self.assertEqual(code, 0)
        stored = "my-run-01-trace-bundle-20261004T100000Z (1).tar.gz"
        self.assertIn(stored, FakeServices.files)
        self.assertEqual(json.loads(FakeServices.files[stored + ".run.json"])["archive"], stored)
        self.assertIn(f"Uploaded: {stored}", out)

    def test_archive_of_another_workflow_system_needs_the_run_address(self):
        plain = self.dir / "snakemake-run-7-trace-bundle-20261004.zip"
        with zipfile.ZipFile(plain, "w") as bundle:
            bundle.writestr("log.txt", "done")
        code, _, err = self.upload(plain)
        self.assertEqual(code, 1)
        self.assertIn("add --run-uri", err)
        self.assertEqual(FakeServices.files, {})
        code, _, err = self.upload(plain, "--run-uri", RUN)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(FakeServices.files[plain.name + ".run.json"])["run_uri"], RUN)

    def test_unsafe_run_address_or_file_name_is_refused_before_anything_is_sent(self):
        code, _, err = self.upload(self.archive(manifest=False), "--run-uri", 'http://x/run> } . <http://evil')
        self.assertEqual(code, 1)
        self.assertIn("run address", err)
        odd = self.dir / "my run.tar.gz"
        odd.write_bytes(self.archive().read_bytes())
        code, _, err = self.upload(odd)
        self.assertEqual(code, 1)
        self.assertIn("file name", err)
        self.assertEqual(FakeServices.files, {})

    def test_errors_of_hu_box_are_reported(self):
        archive = self.archive()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = uploader.main([str(archive), "--link", f"{self.base}/u/d/0000000000aaaaaaaaaa/"])
        self.assertEqual(code, 1)
        self.assertIn("HTTP 404", err.getvalue())
        code, _, err = self.upload(archive, env={"HU_BOX_UPLOAD_PARENT_DIR": "/Another folder"})
        self.assertEqual(code, 1)
        self.assertIn("HTTP 403", err)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err2:
            self.assertEqual(uploader.main([str(archive), "--link", "https://box.hu-berlin.de/d/abc/"]), 1)
        self.assertIn("upload link must look like", err2.getvalue())
        self.assertEqual(FakeServices.files, {})

    def test_upload_works_when_the_page_of_the_link_does_not_name_the_folder(self):
        archive = self.archive()
        blank = {"path": None, "name": None, "no_quota": False, "max_bytes": None}
        with mock.patch.object(uploader, "folder_of_link", return_value=blank):
            code, _, err = self.upload(archive)
            self.assertEqual(code, 1)
            self.assertIn("HU_BOX_UPLOAD_PARENT_DIR", err)
            code, _, err = self.upload(archive, env={"HU_BOX_UPLOAD_PARENT_DIR": "/Traces of FONDA Workflows"})
            self.assertEqual((code, err), (0, ""))
        with mock.patch.object(uploader, "folder_of_link", side_effect=uploader.UploadError("page refused")), \
                mock.patch.object(uploader, "DEFAULT_UPLOAD_LINK", self.upload_link):
            code, _, err = self.upload(self.archive(name="second-trace-bundle-1.tar.gz"))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("second-trace-bundle-1.tar.gz", FakeServices.files)
        self.assertEqual(uploader.DEFAULT_PARENT_DIR, linker.DEFAULT_SHARED_DIR)

    def test_default_link_is_the_fonda_folder_and_the_page_is_read_with_escapes(self):
        self.assertEqual(uploader.DEFAULT_UPLOAD_LINK, f"https://box.hu-berlin.de/u/d/{TOKEN}/")
        page = (b"window.uploadLink = { dirName: 'Sp\\u00E4te L\\u002Dufe', noQuota: true, "
                b"maxUploadFileSize: 209715200, path: '/A\\u0027s folder/B\\u002DC/' };")
        with mock.patch.object(uploader, "fetch", return_value=page):
            folder = uploader.folder_of_link("https://box.hu-berlin.de", TOKEN)
        self.assertEqual(folder, {"path": "/A's folder/B-C/", "name": "Späte L-ufe", "no_quota": True,
                                  "max_bytes": 209715200})


class LinkTests(Base):
    def setUp(self):
        super().setUp()
        token = self.dir / "token"
        token.write_text("box-token\n")
        (self.dir / "email").write_text("admin@example.org\n")
        (self.dir / "password").write_text("secret\n")
        self.env = {"HU_BOX_SERVER_URL": self.base, "HU_BOX_REPOSITORY_ID": REPO, "HU_BOX_API_TOKEN_FILE": str(token),
                    "HU_BOX_SHARED_DIR": FOLDER}
        self.vivo = ["--endpoint", f"{self.base}/vivo/api/sparqlUpdate", "--email-file", str(self.dir / "email"),
                     "--password-file", str(self.dir / "password")]

    def run_linker(self, *args, answers=()):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env), redirect_stdout(out), redirect_stderr(err), \
                mock.patch("builtins.input", side_effect=list(answers)):
            code = linker.main([*args, *self.vivo])
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_lists_the_upload_and_changes_nothing(self):
        archive = self.archive()
        self.upload(archive)
        code, out, err = self.run_linker("--dry-run")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"to do: {archive.name}", out)
        self.assertIn(RUN, out)
        self.assertEqual((FakeServices.links, FakeServices.updates), ({}, []))

    def test_upload_gets_a_public_link_that_is_added_to_its_run(self):
        archive = self.archive()
        self.upload(archive)
        code, out, err = self.run_linker("--yes")
        self.assertEqual((code, err), (0, ""))
        link = FakeServices.links[archive.name]
        self.assertRegex(link, r"/f/[0-9a-f]+/$")
        self.assertEqual(FakeServices.vivo_links, {(RUN, link)})
        self.assertEqual(len(FakeServices.updates), 1)
        self.assertIn(f'INSERT {{ GRAPH <{GRAPH}> {{ <{RUN}> rm:traceArchive "{link}"^^xsd:anyURI }} }}', FakeServices.updates[0])
        self.assertIn(f"WHERE {{ GRAPH <{GRAPH}> {{ <{RUN}> a rm:RunMetadata }} }}", FakeServices.updates[0])
        self.assertIn("added to the run in VIVO", out)
        code, out, _ = self.run_linker("--yes")             # a second round has nothing to do
        self.assertEqual(code, 0)
        self.assertIn(f"already public: {archive.name}", out)
        self.assertIn("Nothing to do.", out)
        self.assertEqual(len(FakeServices.updates), 1)

    def test_owner_is_asked_and_can_say_no(self):
        archive = self.archive()
        self.upload(archive)
        code, out, _ = self.run_linker(answers=["n"])
        self.assertEqual(code, 0)
        self.assertIn("left as it is", out)
        self.assertEqual((FakeServices.links, FakeServices.updates), ({}, []))
        code, _, _ = self.run_linker(answers=["y"])
        self.assertEqual(code, 0)
        self.assertEqual(len(FakeServices.vivo_links), 1)

    def test_upload_for_a_run_that_vivo_does_not_have_stays_private(self):
        archive = self.archive(run="http://example.org/vivo-import/run-metadata/run/unknown")
        self.upload(archive)
        code, out, _ = self.run_linker("--yes")
        self.assertEqual(code, 1)
        self.assertIn("VIVO has no run with this address", out)
        self.assertEqual((FakeServices.links, FakeServices.updates), ({}, []))

    def test_unusable_notes_and_browser_uploads_are_reported_and_skipped(self):
        FakeServices.files["browser-upload.zip"] = b"zip"
        FakeServices.files["bad.tar.gz"] = b"x"
        FakeServices.files["bad.tar.gz.run.json"] = json.dumps(
            {"archive": "bad.tar.gz", "size_bytes": 1, "run_uri": 'http://x/run> } } ; DROP ALL ; <http://y'}).encode()
        FakeServices.files["short.tar.gz"] = b"half"
        FakeServices.files["short.tar.gz.run.json"] = json.dumps(
            {"archive": "short.tar.gz", "size_bytes": 99, "run_uri": RUN}).encode()
        FakeServices.files["alone.tar.gz.run.json"] = json.dumps(
            {"archive": "alone.tar.gz", "size_bytes": 1, "run_uri": RUN}).encode()
        code, out, err = self.run_linker("--yes")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("no run note: browser-upload.zip", out)
        self.assertIn("skipped bad.tar.gz.run.json: the note cannot be used", out)
        self.assertIn("skipped short.tar.gz: its size in HU-Box differs", out)
        self.assertIn("skipped alone.tar.gz.run.json: its archive alone.tar.gz is not in the folder", out)
        self.assertIn("Nothing to do.", out)
        self.assertEqual((FakeServices.links, FakeServices.updates), ({}, []))

    def test_relink_adds_the_existing_link_again(self):
        archive = self.archive()
        self.upload(archive)
        self.run_linker("--yes")
        link = FakeServices.links[archive.name]
        FakeServices.vivo_links.clear()               # as if the VIVO step had failed
        code, out, _ = self.run_linker("--yes", "--relink", archive.name)
        self.assertEqual(code, 0)
        self.assertEqual(FakeServices.vivo_links, {(RUN, link)})
        self.assertEqual(FakeServices.links[archive.name], link)

    def test_missing_setup_is_explained(self):
        self.env["HU_BOX_REPOSITORY_ID"] = ""
        code, _, err = self.run_linker("--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("configure-hu-box.sh", err)


class ScriptTests(Base):
    def test_slurm_archive_script_can_send_its_bundle_to_the_shared_folder(self):
        import test_slurm_archive_script as slurm_tests
        harness = slurm_tests.ArchiveSlurmJobTests("test_package_only_builds_a_checked_bundle_without_network")
        harness.setUp()
        try:
            env = dict(os.environ, HOME=str(harness.home), HU_BOX_CONFIG_FILE=str(harness.hu_config),
                       HU_BOX_UPLOAD_LINK=self.upload_link)
            env.pop("FONDA_SLURM_ENV", None)
            env.pop("EVIDENCE_ROOT", None)
            env.pop("HU_BOX_UPLOAD_PARENT_DIR", None)
            result = subprocess.run([str(slurm_tests.SCRIPT), slurm_tests.JOB_ID, "--shared-folder"], env=env,
                                    cwd=harness.tmp.name, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Uploaded: ", result.stdout)
            self.assertEqual(slurm_tests.FakeHuBox.requests, [])      # the personal library is not used
            archives = [n for n in FakeServices.files if n.endswith(".tar.gz")]
            self.assertEqual(len(archives), 1)
            note = json.loads(FakeServices.files[archives[0] + ".run.json"])
            self.assertRegex(note["run_uri"], r"/run/hpc-at-hu-slurm-1595874-")
        finally:
            harness.tearDown()

    def test_kubernetes_archive_script_uploads_before_any_hu_box_account_is_needed(self):
        script = (ROOT / "scripts" / "archive-publish-run.sh").read_text(encoding="utf-8")
        shared = script.index('python3 "$ROOT_DIR/publisher/upload_trace_archive.py" "$archive"')
        self.assertLess(script.index("Package-only mode"), shared)
        self.assertLess(shared, script.index("Set HU_BOX_REPOSITORY_ID"))
        self.assertLess(shared, script.index("Missing HU-Box token file"))
        self.assertIn("--shared-folder) shared_folder=1 ;;", script)


def anchors(markdown: str) -> set:
    return {re.sub(r"[^a-z0-9 \-]", "", title.lower()).replace(" ", "-")
            for title in re.findall(r"^#{1,6} (.+)$", markdown, re.M)}


class GuideTests(unittest.TestCase):
    def test_guides_name_the_commands_and_link_to_existing_sections(self):
        guide = (ROOT / "docs" / "HU_BOX_TRACE_ARCHIVE.md").read_text(encoding="utf-8")
        for section in ("three-ways-to-keep-the-traces-of-a-run", "without-an-hu-box-account-the-shared-fonda-folder",
                        "another-place-zenodo-or-your-own-storage"):
            self.assertIn(section, anchors(guide))
        self.assertIn(uploader.DEFAULT_UPLOAD_LINK, guide)
        self.assertIn('./scripts/archive-publish-run.sh "$RUN_ID" --shared-folder', guide)
        self.assertIn("--run-trace-archive", guide)
        for path, prefix in (("README.md", "docs/"), ("docs/USER_GUIDE.md", ""), ("docs/ADMIN_SETUP.md", "")):
            text = (ROOT / path).read_text(encoding="utf-8")
            targets = re.findall(r"\(" + re.escape(prefix) + r"HU_BOX_TRACE_ARCHIVE\.md#([a-z0-9-]+)\)", text)
            self.assertTrue(targets, path)
            for target in targets:
                self.assertIn(target, anchors(guide), path)
        admin = (ROOT / "docs" / "ADMIN_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("./scripts/link-shared-traces.sh --dry-run", admin)
        self.assertIn(linker.DEFAULT_SHARED_DIR.strip("/"), admin)
        slurm = (ROOT / "examples/hpc-at-hu-slurm/ARCHIVE_TRACES.md").read_text(encoding="utf-8")
        self.assertIn("--shared-folder", slurm)
        self.assertIn("trace-archive-url.txt", slurm)

    def test_slurm_publish_script_reads_the_saved_link(self):
        script = (ROOT / "examples/hpc-at-hu-slurm/publish-slurm-job.sh").read_text(encoding="utf-8")
        self.assertIn('"$EVIDENCE_DIR/trace-archive-url.txt"', script)

    def test_owner_command_is_executable_and_reads_the_hu_box_settings(self):
        wrapper = ROOT / "scripts" / "link-shared-traces.sh"
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertIn("config/hu-box.env", wrapper.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

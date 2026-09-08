import hashlib
import json
import os
import subprocess
import textwrap
from datetime import datetime, timezone
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from collector import collect_snakemake_kubernetes_metadata as adapter

class MG3EvidenceTests(unittest.TestCase):
    def fixture(self, root):
        sam = root / 'data/MG3/mapped_reads/all_sorted.sam'
        sam.parent.mkdir(parents=True)
        sam.write_text('@HD\tVN:1.4\nr1\t0\tref\t1\t60\t1M\t*\t0\t0\tA\tI\n')
        results = root / 'results'
        results.mkdir()
        files = {'COMPLETED': '2026-09-08T07:27:16Z', 'record-count.txt': '1',
                 'output.sha256': hashlib.sha256(sam.read_bytes()).hexdigest()+'  /run/data/MG3/mapped_reads/all_sorted.sam',
                 'run.log': 'Successfully installed snakemake-7.32.4',
                 'flagstat.txt': '1 mapped', 'compatibility.patch': 'patch',
                 'snakemake-stats.json': '{}'}
        for name, value in files.items(): (results / name).write_text(value)
        (root / 'source/.git').mkdir(parents=True)
        (root / 'source/.git/HEAD').write_text('d235f908a4a4336cfce297bf2f302c5e33ee4e6d')
        for name in ['simulation_config.yaml', 'search_config.yaml']:
            (root / 'source' / name).write_text('')
        return sam

    def test_validates_actual_sam_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sam = self.fixture(root)
            self.assertEqual(adapter.read_mg3_result_metadata(root)['mapped_record_count'], 1)
            sam.write_text(sam.read_text().replace('r1', 'r2'))
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                adapter.read_mg3_result_metadata(root)

    def test_rejects_stale_count_and_missing_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'results/record-count.txt').write_text('2')
            with self.assertRaisesRegex(RuntimeError, 'record count'):
                adapter.read_mg3_result_metadata(root)
            (root / 'results/COMPLETED').unlink()
            with self.assertRaisesRegex(RuntimeError, 'completed'):
                adapter.read_mg3_result_metadata(root)

    def test_requires_version_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'results/run.log').write_text('')
            with self.assertRaisesRegex(RuntimeError, 'version'):
                adapter.read_mg3_result_metadata(root)


class MG3RuntimeProvenanceTests(MG3EvidenceTests):
    def manifest(self, root):
        data = {"schema_version": 1, "run_id": "new-run", "workflow_commit": "d235f908a4a4336cfce297bf2f302c5e33ee4e6d",
                "snakemake": "7.32.4", "snakemake_cores": 4, "simulator_commit": "a"*40,
                "dream_yara_commit": "b"*40, "dependency_mode": "built",
                "dependency_provenance_scope": "Tools built inside this pod.", "tool_sha256": {"mapper": "c"*64}}
        (root/'results/provenance.json').write_text(json.dumps(data))
        (root/'results/snakemake-version.txt').write_text('7.32.4')
        return data

    def test_runtime_manifest_is_preserved_and_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            data = self.manifest(root)
            value = adapter.read_mg3_result_metadata(root)['provenance']
            self.assertEqual(value['snakemake_cores'], 4)
            self.assertEqual(value['simulator_commit'], 'a'*40)
            data['workflow_commit'] = 'e'*40
            (root/'results/provenance.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(RuntimeError, 'revision'):
                adapter.read_mg3_result_metadata(root)

    def test_legacy_does_not_invent_dependency_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            provenance = adapter.read_mg3_result_metadata(root)['provenance']
            self.assertNotIn('simulator_commit', provenance)
            self.assertNotIn('snakemake_cores', provenance)

    def test_rejects_unrelated_run_and_stale_completion(self):
        result = {'completed_at': '2026-09-08T07:27:16Z', 'provenance': {'run_id':'new-run'}}
        task = SimpleNamespace(status='COMPLETED', submit=datetime(2026,9,8,7,26,tzinfo=timezone.utc),end=datetime(2026,9,8,7,28,tzinfo=timezone.utc))
        adapter.validate_mg3_attempt_evidence(result,[task],'new-run')
        with self.assertRaisesRegex(RuntimeError,'run_id'):
            adapter.validate_mg3_attempt_evidence(result,[task],'other-run')
        result['completed_at']='2026-09-07T07:27:16Z'
        with self.assertRaisesRegex(RuntimeError,'outside'):
            adapter.validate_mg3_attempt_evidence(result,[task],'new-run')

class HistoricalReceiptGuardTests(unittest.TestCase):
    def test_existing_plain_receipt_blocks_duplicate_publication(self):
        template = (Path(__file__).resolve().parents[1]/'k8s/snakemake-publisher-job.yaml').read_text()
        guard = textwrap.dedent(template.split('            - |\n',1)[1].split('              python3 /opt/fonda-vivo/collector.py',1)[0])
        with tempfile.TemporaryDirectory() as directory:
            outbox = Path(directory)/'vivo-outbox'
            outbox.mkdir()
            (outbox/'example.published.json').write_text('{"http_status":200}')
            env = dict(os.environ,RUN_ROOT=directory,RUN_ID='example',OUTPUT_STAMP='stamp',DRY_RUN='0',FORCE_REPUBLISH='0')
            proc = subprocess.run(['bash','-c',guard],env=env,capture_output=True,text=True)
            self.assertEqual(proc.returncode,4,proc.stderr)
            self.assertIn('already exists',proc.stderr)
            env['DRY_RUN']='1'
            self.assertEqual(subprocess.run(['bash','-c',guard],env=env,capture_output=True).returncode,0)

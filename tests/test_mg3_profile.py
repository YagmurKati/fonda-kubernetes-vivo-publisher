import hashlib
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

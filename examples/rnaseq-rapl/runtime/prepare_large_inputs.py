"""Stage a fresh, checksummed public-data run; preserve every original source file."""
import difflib
import gzip
import hashlib
import io
import json
import pathlib
import shutil
import tarfile
import time
import urllib.request

P = pathlib.Path
w = P('/workspace')
for name in ('run', 'work', 'provenance', 'inputs', 'source-backups'):
    (w / name).mkdir(exist_ok=False)
for source in sorted(P('/config').iterdir()):
    if source.is_file():
        with (w / 'provenance' / source.name).open('xb') as out:
            out.write(source.read_bytes())

archives = []
for owner, repo, commit, dest in [
    ('CRC-FONDA', 'RAPL_measurement_workflows', '8786ab77fe4761fefb150957050d862c02c3dde8', 'measurement-source'),
    ('nextflow-io', 'rnaseq-nf', '5c89d3859abbe54893d4e1ae0f21115dcebd9d1d', 'rnaseq-source'),
]:
    url = f'https://codeload.github.com/{owner}/{repo}/tar.gz/{commit}'
    data = urllib.request.urlopen(url, timeout=120).read()
    with (w / 'provenance' / f'{repo}-{commit}.tar.gz').open('xb') as out:
        out.write(data)
    stage = w / (dest + '-archive')
    stage.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        archive.extractall(stage, filter='data')
    entries = list(stage.iterdir())
    assert len(entries) == 1 and entries[0].is_dir()
    shutil.copytree(entries[0], w / dest)
    archives.append(dict(repository=f'{owner}/{repo}', commit=commit, url=url, sha256=hashlib.sha256(data).hexdigest()))
    print(f'Prepared source {repo} at {commit}', flush=True)
(w / 'provenance/archives.json').write_text(json.dumps(archives, indent=2) + '\n')

# Preserve and checksum the exact upstream file before the single required edit.
module = w / 'rnaseq-source/modules/quant/main.nf'
original = module.read_bytes()
assert original.count(b'--libType=U') == 1
backup = w / 'source-backups/quant-main.nf.original'
with backup.open('xb') as out:
    out.write(original)
assert hashlib.sha256(backup.read_bytes()).digest() == hashlib.sha256(original).digest()
updated = original.replace(b'--libType=U', b'--libType=A')
module.write_bytes(updated)
assert module.read_bytes() == updated and backup.read_bytes() == original
(w / 'provenance/library-type.patch').write_text(''.join(difflib.unified_diff(
    original.decode().splitlines(True), updated.decode().splitlines(True),
    fromfile='upstream/modules/quant/main.nf', tofile='run/modules/quant/main.nf')))
(w / 'provenance/source-change.json').write_text(json.dumps({
    'original_path': str(module), 'backup_path': str(backup),
    'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'original_sha256': hashlib.sha256(original).hexdigest(),
    'new_sha256': hashlib.sha256(updated).hexdigest(),
    'reason': 'Detect library orientation and strandedness for the larger paired-end input.'
}, indent=2) + '\n')

sample = json.loads(P('/config/ena-input.json').read_text())[0]
assert sample['run_accession'] == 'SRR16287545' and sample['library_layout'] == 'PAIRED'
records = []
urls = sample['fastq_ftp'].split(';')
md5s = sample['fastq_md5'].split(';')
sizes = [int(v) for v in sample['fastq_bytes'].split(';')]
for remote, md5, size in zip(urls, md5s, sizes):
    url = 'https://' + remote
    dest = w / 'inputs' / remote.rsplit('/', 1)[-1]
    sha = hashlib.sha256()
    digest = hashlib.md5()
    written = 0
    next_log = 256 * 1024 * 1024
    with urllib.request.urlopen(url, timeout=180) as response, dest.open('xb') as out:
        while chunk := response.read(4 * 1024 * 1024):
            out.write(chunk)
            sha.update(chunk)
            digest.update(chunk)
            written += len(chunk)
            if written >= next_log:
                print(f'{dest.name}: {written:,}/{size:,} bytes', flush=True)
                next_log += 256 * 1024 * 1024
    assert written == size and digest.hexdigest() == md5, f'Input checksum mismatch: {dest.name}'
    with gzip.open(dest, 'rt') as inp:
        first = [inp.readline().rstrip('\n') for _ in range(4)]
    assert first[0].startswith('@') and first[2].startswith('+') and len(first[1]) == len(first[3])
    records.append(dict(file=str(dest), url=url, bytes=written, md5=md5, sha256=sha.hexdigest()))
    print(f'Verified {dest.name}', flush=True)

url = json.loads(P('/config/sources.json').read_text())['ensembl_transcriptome_url']
compressed = w / 'inputs' / url.rsplit('/', 1)[-1]
sha = hashlib.sha256()
bsd = 0
size = 0
with urllib.request.urlopen(url, timeout=120) as response, compressed.open('xb') as out:
    while chunk := response.read(1024 * 1024):
        out.write(chunk)
        sha.update(chunk)
        size += len(chunk)
        for byte in chunk:
            bsd = (((bsd >> 1) | ((bsd & 1) << 15)) + byte) & 0xffff
assert sha.hexdigest() == '007c99289b98db767cd9822c9d78c20ae5ee17084559ed68da82df2e7a333b31'
assert bsd == 46740 and (size + 1023) // 1024 == 17208, 'Reference checksum mismatch'
reference = w / 'inputs/transcriptome.fa'
uncompressed_sha = hashlib.sha256()
transcripts = 0
with gzip.open(compressed, 'rb') as inp, reference.open('xb') as out:
    for line in inp:
        transcripts += line.startswith(b'>')
        uncompressed_sha.update(line)
        out.write(line)
assert transcripts > 10000
records.append(dict(file=str(compressed), url=url, bytes=size, bsd_checksum=bsd, sha256=sha.hexdigest(),
                    uncompressed_file=str(reference), uncompressed_sha256=uncompressed_sha.hexdigest(),
                    transcript_count=transcripts))
(w / 'provenance/inputs.json').write_text(json.dumps(records, indent=2) + '\n')
print(f'Inputs ready: complete SRR16287545 sample and {transcripts:,} reference transcripts', flush=True)

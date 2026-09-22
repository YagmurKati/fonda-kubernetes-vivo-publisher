import datetime,json,os,pathlib,subprocess,time
P=pathlib.Path
out=P('/workspace/rapl')
out.mkdir(exist_ok=False)
metadata={'node':os.environ['NODE_NAME'],'units':'microjoules','scope':'whole-node CPU package and DRAM; includes other activity','domains':[]}
for p in sorted(P('/host-powercap').rglob('energy_uj')):
    name=(p.parent/'name').read_text().strip()
    metadata['domains'].append({'name':name,'path':str(p),'max_energy_range_uj':int((p.parent/'max_energy_range_uj').read_text()),'initial_uj':int(p.read_text())})
assert {d['name'] for d in metadata['domains']}=={'package-0','dram'}
(out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
P('/workspace/collector.ready').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
deadline=time.monotonic()+14300
while not P('/workspace/run/start.signal').exists():
    if time.monotonic()>deadline or P('/workspace/run/stop.signal').exists(): raise SystemExit('No workload start signal')
    time.sleep(.2)
(out/'collector-start.txt').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
rc=subprocess.call(['bash','/config/collect_energy_data.sh',str(out/'package-energy.txt'),str(out/'dram-energy.txt')],env={**os.environ,'TZ':'UTC'})
(out/'collector-end.txt').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
P('/workspace/collector.finished').write_text(str(rc)+'\n')
print(json.dumps({'collector_exit_code':rc,'node':os.environ['NODE_NAME']}),flush=True)
raise SystemExit(rc)

"""Snapshot public GitHub metadata/tree/README; no clones or execution."""
import json, urllib.request, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parent/'repos'
REPOS=['EAST-J/Dynhor','NVlabs/BundleSDF','zc-alexfan/hold','Isabella98Liu/DG-Mesh','Open3DVLab/DynaSurfGS','gemmechu/ObjectCarver','DavidXu-JJ/DebSDF','IRMVLab/GPU-SDF','xmeng525/NeAT','19reborn/NeuS2','NVlabs/neuralangelo','Anttwo/MILo','VAST-AI-Research/TripoSF','Fan-Treasure/ExMesh']
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'mesh-research-audit','Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=40) as r:return r.read()
def audit(repo):
 try:
  dest=ROOT/repo.replace('/','__');dest.mkdir(parents=True,exist_ok=True)
  meta=json.loads(fetch('https://api.github.com/repos/'+repo))
  tree=json.loads(fetch('https://api.github.com/repos/'+repo+'/git/trees/'+meta['default_branch']+'?recursive=1'))
  paths=[i['path'] for i in tree['tree'] if i['type']=='blob']
  record={'repo':repo,'branch':meta['default_branch'],'tree_sha':tree['sha'],'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'paths':paths}
  (dest/'snapshot.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
  readme=next((p for p in paths if p.lower()=='readme.md'),None)
  if readme:(dest/'README.md').write_bytes(fetch('https://raw.githubusercontent.com/'+repo+'/'+meta['default_branch']+'/'+readme))
  return {'repo':repo,'branch':meta['default_branch'],'sha':tree['sha'],'files':len(paths),'paths':paths[:8]}
 except Exception as e:return {'repo':repo,'error':str(e)}
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:
  for r in pool.map(audit,REPOS):print(json.dumps(r),flush=True)

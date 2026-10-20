"""Append image evidence without changing or discarding the original samples."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--first",type=Path,required=True);p.add_argument("--second",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True)
    first,second=np.load(a.first),np.load(a.second)
    joined={k:np.concatenate([first[k],second[k]]) for k in ("surface","normals","free","inside")}
    np.savez(out/"evidence.npz",**joined)
    sources=[dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (a.first,a.second)]
    (out/"manifest.json").write_text(json.dumps(dict(sources=sources,first_samples_retained=True,
        counts={k:len(v) for k,v in joined.items()},new_observations_are_no_longer_holdout=True),indent=2))

if __name__=="__main__":main()

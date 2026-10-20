"""Fit image evidence with an exact LP diagnostic and a sparse convex QP.

The fit never reads the renderer's ground-truth shape. Scaffolded OBJ output is
separately labeled as a visualization fixture. Run evaluate_rgb.py afterwards.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from scipy import sparse
import osqp
from scipy.optimize import linprog
from skimage.measure import marching_cubes
from run_smoke import solve, constraints, grid_points, evaluate, object_field, write_obj, csv_write


def smooth_qp(e, fit):
    n = fit["n"]
    ids = np.arange(n**3).reshape((n,)*3)
    edges = []
    for axis in range(3):
        a, b = [slice(None)]*3, [slice(None)]*3
        a[axis], b[axis] = slice(None,-1), slice(1,None)
        edges.append((ids[tuple(a)].ravel(),ids[tuple(b)].ravel()))
    i,j = [np.concatenate([e[k] for e in edges]) for k in range(2)]
    d = sparse.coo_matrix((np.r_[np.ones(len(i)),-np.ones(len(j))],
        (np.r_[np.arange(len(i)),np.arange(len(i))],np.r_[i,j])), shape=(len(i),n**3)).tocsc()
    q = d.T@d + 1e-6*sparse.eye(n**3,format="csc")
    a,b,u = constraints(e,n)
    aa = sparse.vstack([a,sparse.eye(n**3)],format="csc")
    bound = b+(fit["eta"]+1e-6)*u
    s = osqp.OSQP()
    s.setup(P=sparse.triu(q,format="csc"),q=np.zeros(n**3),A=aa,
            l=np.r_[np.full(len(b),-np.inf),np.full(n**3,-2.)],
            u=np.r_[bound,np.full(n**3,2.)],verbose=False,eps_abs=1e-7,eps_rel=1e-7,
            max_iter=100000,polishing=True)
    s.warm_start(x=fit["z"])
    r=s.solve()
    if r.info.status_val not in (1,2):
        raise RuntimeError(r.info.status)
    verified = float(np.maximum((a@r.x-b)/u,0).max())
    if verified > fit["eta"]+1e-4:
        raise RuntimeError(f"QP residual {verified} exceeds certified slack {fit['eta']}")
    return {**fit,"z":r.x,"qp_status":r.info.status,"qp_seconds":r.info.run_time,"verified_eta":verified}


def smooth_tv(e, fit):
    """Linear total-variation tie break at the same minimax optimum.

    Used for all image-study arms after QP convergence failed. This optimizer
    change is recorded; it does not alter the diagnostic LP or its eta.
    """
    n=fit["n"]; count=n**3;ids=np.arange(count).reshape((n,)*3)
    edges=[]
    for axis in range(3):
        lo,hi=[slice(None)]*3,[slice(None)]*3
        lo[axis],hi[axis]=slice(None,-1),slice(1,None)
        edges.append((ids[tuple(lo)].ravel(),ids[tuple(hi)].ravel()))
    i,j=[np.concatenate([e[k] for e in edges]) for k in range(2)]
    d=sparse.coo_matrix((np.r_[np.ones(len(i)),-np.ones(len(i))],
        (np.r_[np.arange(len(i)),np.arange(len(i))],np.r_[i,j])),shape=(len(i),count)).tocsr()
    a,b,u=constraints(e,n);eye=sparse.eye(len(i),format="csr")
    mat=sparse.vstack([sparse.hstack([a,sparse.csr_matrix((a.shape[0],len(i)))]),
        sparse.hstack([d,-eye]),sparse.hstack([-d,-eye])],format="csr")
    start=time.perf_counter()
    r=linprog(np.r_[np.zeros(count),np.ones(len(i))],A_ub=mat,
        b_ub=np.r_[b+(fit["eta"]+1e-8)*u,np.zeros(2*len(i))],
        bounds=[(-2,2)]*count+[(0,None)]*len(i),method="highs")
    if not r.success: raise RuntimeError(r.message)
    z=r.x[:count]; verified=float(np.maximum((a@z-b)/u,0).max())
    if verified>fit["eta"]+1e-4: raise RuntimeError("TV violated minimax slack")
    return {**fit,"z":z,"qp_status":"TV LP solved","qp_seconds":time.perf_counter()-start,"verified_eta":verified}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--fit-method",choices=["tv","qp"],default="tv")
    a=p.parse_args()
    out=a.output.resolve()
    if out.exists() and any(out.iterdir()): raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True)
    raw=np.load(a.evidence)
    e={k:raw[k] for k in ("surface","normals","free","inside")}
    start=time.perf_counter();rows=[];fits={}
    for n in (2,3,5):
        fit=solve(e,n)
        row=dict(nodes=n**3,n=n,eta=fit["eta"],lp_seconds=fit["seconds"],qp_status="pending",qp_seconds=0.,verified_eta=None)
        rows.append(row);csv_write(out/"diagnostics.csv",rows)
        print(f"{n**3} nodes: LP eta={fit['eta']:.8g}",flush=True)
        try:
            fit=(smooth_tv if a.fit_method=="tv" else smooth_qp)(e,fit)
            row.update(qp_status=fit["qp_status"],qp_seconds=fit["qp_seconds"],verified_eta=fit["verified_eta"])
            fits[f"nodes_{n**3}"]=fit
        except RuntimeError as ex:
            row["qp_status"]=str(ex)
        csv_write(out/"diagnostics.csv",rows)
    np.savez(out/"fields.npz",**{k:f["z"] for k,f in fits.items()})
    pts=grid_points(81)
    for name,fit in fits.items():
        field=object_field(pts,evaluate(pts,fit)).reshape((81,)*3)
        if field.min()<0<field.max():
            v,f,_,_=marching_cubes(field,0,spacing=(1/80,)*3)
            write_obj(out/f"{name}_shared_scaffold.obj",v,f)
    report=dict(evidence=str(a.evidence.resolve()),elapsed_seconds=time.perf_counter()-start,diagnostics=rows,
                status="completed" if len(fits)==3 else "partial_fit_failure",fit_method=a.fit_method,osqp=osqp.__version__,
                known_scaffold_for_display=True,no_gt_geometry_used_for_fit=True)
    (out/"summary.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=="__main__": main()

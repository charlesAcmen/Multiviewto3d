"""Evaluation-only GT access, after all image-derived fields are saved."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
import cv2
from skimage.measure import marching_cubes
from run_smoke import (box_field, object_field, constraints, grid_points, evaluate, csv_write)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--train",type=Path,required=True)
    p.add_argument("--validation",type=Path,required=True)
    p.add_argument("--fit",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--validation-role",choices=["development","training_replay"],default="development")
    a=p.parse_args();out=a.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit("Choose fresh output directory")
    out.mkdir(parents=True)
    boxes=np.asarray(json.loads((a.data/"ground_truth_only.json").read_text())["boxes"])
    def truth(points):
        return np.min(np.stack([box_field(points,(lo+hi)/2,(hi-lo)/2) for lo,hi in boxes]),axis=0)
    tr=np.load(a.train/"evidence.npz");va=np.load(a.validation/"evidence.npz")
    e={k:va[k] for k in ("surface","normals","free","inside")}
    evid=[]
    second_role="development_validation" if a.validation_role=="development" else "appended_training_observations"
    for label,data in [("initial_train",tr),(second_role,va)]:
        surface_distance=np.abs(truth(data["surface"]))
        evid.append(dict(split=label,surface_count=len(surface_distance),
            surface_sdf_abs_median=float(np.median(surface_distance)),surface_sdf_abs_p95=float(np.quantile(surface_distance,.95)),
            free_gt_occupied_fraction=float(np.mean(truth(data["free"])<=0)),
            inside_probe_gt_outside_fraction=float(np.mean(truth(data["inside"])>0))))
    csv_write(out/"evidence_quality.csv",evid)
    fields=np.load(a.fit/"fields.npz")
    rng=np.random.default_rng(20261021)
    ep=rng.uniform([.05,.34,.17],[.95,.84,.83],(150000,3))
    gap=(ep[:,0]>.39)&(ep[:,0]<.61)
    body=(ep[:,0]<.36)|(ep[:,0]>.64)
    y,z=np.meshgrid(np.linspace(.32,.93,151),np.linspace(.15,.85,41),indexing="ij")
    path=np.column_stack([np.full(y.size,.5),y.ravel(),z.ravel()])
    metrics=[];meshes={};pts=grid_points(81)
    gt=truth(pts).reshape((81,)*3)
    v,f,_,_=marching_cubes(gt,0,spacing=(1/80,)*3);meshes["ground_truth"]=(v,f)
    for name in fields.files:
        count=len(fields[name]);n=round(count**(1/3));fit=dict(z=fields[name],n=n)
        aaa,b,u=constraints(e,n)
        violation=np.maximum((aaa@fit["z"]-b)/u,0)
        occupancy=object_field(ep,evaluate(ep,fit))<=0
        path_free=object_field(path,evaluate(path,fit)).reshape(y.shape)>0
        row=dict(method=name,nodes=count,observation_role=a.validation_role,check_max_eta=float(violation.max()),
                 check_p95_eta=float(np.quantile(violation,.95)),
                 check_free_occupied_fraction=float(np.mean(evaluate(va["free"],fit)<=0)),
                 gap_roi_occupied_fraction=float(occupancy[gap].mean()),
                 solid_probe_recall=float(occupancy[body].mean()),
                 notch_straight_path_fraction=float(path_free.all(axis=0).mean()))
        metrics.append(row)
        value=object_field(pts,evaluate(pts,fit)).reshape((81,)*3)
        v,f,_,_=marching_cubes(value,0,spacing=(1/80,)*3);meshes[name]=(v,f)
    csv_write(out/"metrics.csv",metrics)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig=plt.figure(figsize=(13,4.8))
    for i,(name,(v,f)) in enumerate(meshes.items(),1):
        ax=fig.add_subplot(1,len(meshes),i,projection="3d")
        ax.add_collection3d(Poly3DCollection(v[:,[0,2,1]][f],shade=True,linewidths=0,
            facecolors=["#9aa7b1","#d58257","#63a79b","#447eac"][i-1]))
        ax.set(xlim=(0,1),ylim=(0,1),zlim=(0,1),title=name.replace("_"," "))
        ax.set_box_aspect((1,1,1));ax.view_init(elev=12,azim=-80);ax.set_axis_off()
    fig.suptitle("RGB-matched local surfaces + mask FREE evidence (GT cameras / masks)")
    fig.text(.5,.035,"Outer shape/base are shared known fixtures; only the gap field is fitted. One development object.",ha="center")
    fig.tight_layout(rect=(0,.05,1,.92));fig.savefig(out/"rgb_local_meshes.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,4,figsize=(12,3.5))
    for ax,view in zip(axes,[0,2,4,12]):
        im=cv2.imread(str(a.data/"rgb"/f"{view:03d}.png"))
        ax.imshow(cv2.cvtColor(im,cv2.COLOR_BGR2RGB));ax.set_title(f"RGB view {view}");ax.axis("off")
    fig.suptitle("Actual rendered inputs to SIFT / triangulation; no GT depth fed to frontend")
    fig.tight_layout();fig.savefig(out/"input_views.png",dpi=160);plt.close(fig)
    snapshots={}
    for name in ["run_smoke.py","render_synthetic.py","rgb_frontend.py","fit_image_evidence.py","evaluate_rgb.py"]:
        src=Path(__file__).with_name(name);shutil.copyfile(src,out/(name+".snapshot"));snapshots[name]=hashlib.sha256(src.read_bytes()).hexdigest()
    summary=dict(status="completed",validation_role=a.validation_role,evidence_quality=evid,metrics=metrics,source_sha256=snapshots,
        interpretation="Single synthetic development object; image-derived local surfaces with GT poses/masks, known outer scaffold",
        limitations=["All-view debugging preceded the even/odd development split", "No untouched test object or estimated-pose/SAM evaluation",
                     "Sparse SIFT triangulation, not complete MVS", "Extra inferred inward probes and manually shared ROI",
                     "No automatic block selection or same-capacity comparison", "No GPU training/VRAM peak measured"])
    (out/"summary.json").write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))


if __name__=="__main__":main()

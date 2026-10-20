# RGB接口重放（CPU）

结果说明见[RGB实测报告](../../research/2026-10-20_RGB_INTERFACE_RESULTS.md)。常规Python3.12环境先按[README](README.md)安装`requirements.lock.txt`。当前本机已有独立环境。各脚本要求新输出目录，不覆盖记录。

```powershell
Set-Location 'D:\repos\Multiviewto3d'
. .\.venv-gap-smoke\Scripts\Activate.ps1
$env:MPLCONFIGDIR = Join-Path (Get-Location) '.work-tmp\matplotlib'
$rgbRun = Join-Path (Get-Location) ('experiments\gap_representability\results\replay-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))

# Generate RGB, masks and cameras. No GT depth/normal maps are exported.
python .\experiments\gap_representability\render_synthetic.py --output "$rgbRun\data"

# Extract evidence from separate groups. These are development views.
python .\experiments\gap_representability\rgb_frontend.py --data "$rgbRun\data" --output "$rgbRun\train" --view-stride 2 --view-offset 0 --evidence-only
python .\experiments\gap_representability\rgb_frontend.py --data "$rgbRun\data" --output "$rgbRun\validation" --view-stride 2 --view-offset 1 --evidence-only

# Fit the first group, then inspect the independent development group.
python .\experiments\gap_representability\fit_image_evidence.py --evidence "$rgbRun\train\evidence.npz" --output "$rgbRun\fit-before" --fit-method tv
python .\experiments\gap_representability\evaluate_rgb.py --data "$rgbRun\data" --train "$rgbRun\train" --validation "$rgbRun\validation" --fit "$rgbRun\fit-before" --output "$rgbRun\evaluation-before" --validation-role development

# Retain every original sample, append new observations, and refit locally.
python .\experiments\gap_representability\append_evidence.py --first "$rgbRun\train\evidence.npz" --second "$rgbRun\validation\evidence.npz" --output "$rgbRun\appended"
python .\experiments\gap_representability\fit_image_evidence.py --evidence "$rgbRun\appended\evidence.npz" --output "$rgbRun\fit-after" --fit-method tv
python .\experiments\gap_representability\evaluate_rgb.py --data "$rgbRun\data" --train "$rgbRun\train" --validation "$rgbRun\validation" --fit "$rgbRun\fit-after" --output "$rgbRun\evaluation-after" --validation-role training_replay

deactivate
```

每一步先确认退出成功再继续；错误时对应目录保留原始输入/中间文件。预期：`evaluation-before/metrics.csv`显示细层打开缝隙但有实体损失；`evaluation-after/metrics.csv`中27节点在指定ROI恢复，而125节点仍有局部误桥。单次随机化/库版本可能产生微小差别；不能仅以截图完全一致作为验收。

主要输入：`rgb/*.png`、`mask/*.png`、`cameras.npz`。`ground_truth_only.json`只在渲染和`evaluate_rgb.py`中使用。拟合读`evidence.npz`而不读GT。共享解析外壳/底座用于OBJ局部示范，它们仍是真值结构先验，不能将整个OBJ宣称为端到端RGB输出。

前端SIFT、三角化、PCA法线、推断向内探针与GT Mask保守FREE均可分别替换。当前没有SAM、相机估计、完整稠密MVS、全局粗场、自动选块、纹理导出或GPU驻留管理。`--fit-method qp`保留失败复查路径；默认`tv`为实际成功的线性拟合路径。

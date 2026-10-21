# 孔宽扫描：用户运行与结果判读

2026-10-21。**代码已写入并做静态审查，尚未运行。本文没有新实验结果。**不需要编译，不使用 GPU；复用已有 CPU 环境。

## 这一步检验什么

旧实验只在一个宽缝叉子上证明“容量和覆盖都可能限制几何”。本轮改用带矩形通孔的厚板 `window`，冻结原来的相机、ROI、SIFT/PCA、约束权重和 TV 拟合设置，扫描孔宽 `0.24 / 0.12 / 0.06 / 0.03`。数值是归一化坐标，不是毫米。

新几何的孔口闭合，但仍是盒子组合、相同材质与相机族，不能称真实物体泛化。孔变窄也会改变内壁可见性，所以失败未必由表示容量导致。`nominal_front_mouth_pixels` 只表示某个正面视图中的投影孔口宽，不是实际可恢复分辨率。

每个算例的流程：

```text
20 张合成 RGB + GT 相机/Mask
  → 不读 GT 几何的 SIFT 三角化 / PCA 表面与 Mask FREE
  → 相同证据下 8 / 27 / 125 节点 LP 诊断 + TV 拟合
  → 单独评价程序读 GT，测局部场并导出局部 Mesh
  → 与两种直接 Mask 雕刻比较
```

两个基线分别是：`mask_raw`，任何一幅原始 Mask 的背景投影即可排空；`mask_conservative`，背景先用 5×5 核腐蚀，至少两视图支持才排空，与前端 FREE 规则相同。图像外的投影不投票。**未被雕掉的体积只是候选外壳，并不等于已观测实体。**目前没有遮挡者，不能把本轮二值 Mask 规则直接用于被手遮挡的真实物体。

所有方法使用相同视图、评价 ROI 和 81³ 提取网格；Mask 基线可以直接查询整幅 Mask，LP 只拟合前端抽样的有限约束，因此这不是同监督采样量、同内存或同时间预算比较。它检验的是“整个局部接口是否优于足够简单的输入利用方式”。

## 1. 首次建立环境

在本机仓库根目录运行，换机器只需进入对应的目录。示例路径适用于当前机器：

```powershell
Set-Location 'D:\coding\repo\multiview3d\Multiviewto3d'
py -3.12 -m venv .venv-gap-smoke
if ($LASTEXITCODE -ne 0) { throw '创建环境失败，请保留报错。' }
& '.\.venv-gap-smoke\Scripts\python.exe' -m pip install -r '.\experiments\gap_representability\requirements.lock.txt'
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请勿继续实验或静默更换版本。' }
```

已有该环境则跳过创建/安装步骤。这里直接调用环境中的 Python，不需要激活或修改 PowerShell 执行策略。依赖锁来自上次实验机器，不代表本机已经安装成功。

## 2. 先做一个接口冒烟

```powershell
$gapPython = '.\.venv-gap-smoke\Scripts\python.exe'
$env:MPLCONFIGDIR = Join-Path (Get-Location) '.work-tmp\matplotlib'
$gapRun = Join-Path (Get-Location) ('experiments\gap_representability\results\window-smoke-' + $env:COMPUTERNAME + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $gapPython '.\experiments\gap_representability\run_width_study.py' --output $gapRun --shape window --widths 0.24 --seeds 20261022
$gapExit = $LASTEXITCODE
Get-Content (Join-Path $gapRun 'summary.json')
Import-Csv (Join-Path $gapRun 'cases.csv') | Format-Table
if (Test-Path (Join-Path $gapRun 'metrics.csv')) {
    Import-Csv (Join-Path $gapRun 'metrics.csv') | Format-Table method,training_eta,gap_occupied_fraction,solid_recall,near_wall_solid_recall,gap_path_fraction
}
Write-Output "实验退出码：$gapExit；结果目录：$gapRun"
```

**接口成功的预期，不是算法胜出的预期：**退出码为 0、根目录 `summary.json.status=completed`，`cases.csv` 有一例且状态为 `completed`，`metrics.csv` 有两个 Mask 基线与三个节点模型，共五行。该例 `evaluation/comparison.png` 显示六个局部切片，红线为 GT，黑色为各方法的实体/候选占据。存在零交叉时还会导出 `*_local_open.obj`。

OBJ 只覆盖固定 ROI，边界可以开放；没有加真值底座或外壳。整体不像完整孔板是预期，不能用补齐外壳的方式美化本轮结果。`mesh_status=no_zero_crossing` 时不生成该方法的 OBJ，应查看占据指标，可能是全填满或全刻空。

退出码 2 表示至少一例前端/求解/评价失败或部分模型拟合失败。查看该例 `RUN_LOG.md`、`evidence/failure.json`（若存在）和 `fit/diagnostics.csv`。渲染完成但 RGB 前端或拟合失败时仍尝试计算 Mask 基线；这时可能只有两个基线，**不能据此把实验记为成功，或从汇总中删除失败例**。中断/依赖导入失败可能没有最终 CSV，应保留已有目录并记录终端报错。

## 3. 接口接通后，固定设置跑宽度扫描

```powershell
$gapRun = Join-Path (Get-Location) ('experiments\gap_representability\results\window-widths-' + $env:COMPUTERNAME + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $gapPython '.\experiments\gap_representability\run_width_study.py' --output $gapRun --shape window --widths 0.24 0.12 0.06 0.03 --seeds 20261022 20261023 20261024
```

共 4 孔宽 × 3 纹理种子 = 12 例；若全部拟合完成则汇总 60 行方法指标。尚无本机耗时数据，不承诺分钟数。三个种子改变纹理，并不代表三个独立物体。第一次宽孔冒烟已经接触过 `20261022`，因此整组只叫开发扫描，不能冒充最终未见测试集。若要改权重、ROI 或采样策略，另开新运行，保留原始失败，并重新冻结后续独立几何测试。

## 4. 怎样判断有价值

| 指标 | 含义 | 希望看到的变化 |
|---|---|---|
| `gap_occupied_fraction` | GT 局部空域探针被误填的比例 | 降低，同时保住实体 |
| `solid_recall` | GT 局部实体探针被保留的比例 | 不能用削掉实体换开孔 |
| `near_wall_solid_recall` | 距解析边界较近的内部探针保留率 | 补充总实体指标，暴露削壁 |
| `gap_path_fraction` | 77 条孔内路径各取 151 个深度样点，整条为空的比例 | 与体积指标一起看，不是连续拓扑证明 |
| `training_eta` | 同一归一化约束下的训练最小违例 | 只能辅助解释，不能单独决定接受更新 |
| `gap_with_two_safe_mask_votes_fraction` | GT 空域中满足保守 Mask 支持规则的比例 | 帮助判断实际输入是否支持排空 |
| `surface_gt_distance_p95` 等质量字段 | 事后检查图像证据与解析几何是否一致 | GT 只用于诊断，不能用来筛训练点或调权重 |

所有几何指标都是局部**场查询**。它们不等于从 OBJ 测得的 Chamfer、最小壁厚、连通性或拓扑。体积探针共 60000 个，排除距解析边界 0.002 以内的点；近壁实体取解析场值在 `(-0.01,-0.002)` 的探针。路径横跨孔宽中央 70%，高度范围 `[0.36,0.68]`、深度 `[0.17,0.83]`；没有检查整个孔的每一个位置。

第一轮不自动设“通过阈值”，先完整报告各指标和所有失败。结果决定下一步：

1. **Mask 基线已开孔且实体保留好：**不能声称 LP 创造了新的恢复能力。下一实验应是同预算自动选块，而非继续拿 8 节点作弱对手。
2. **Mask 能保孔，RGB 没提够表面或误差大：**先定位内壁可见性、匹配与 PCA 支持；不能把前端不足包装成后端容量问题。
3. **证据可靠，细层比粗层同时改善空域和实体：**支持继续研究容量诊断，但尚不证明自动调度有用或有创新。
4. **更细后误雕刻/误桥增加：**沿用已发现的覆盖与稳定性问题；不要仅因 eta 降低就接受更新。

## 5. 如何同步这次运行

每例命令和错误写入 `RUN_LOG.md`，根目录 `summary.json` 保存参数、Git HEAD、源码 SHA256、实际依赖版本与案例状态，逐例更新。源码 hash 对应实际执行文件，不能只凭 HEAD 假定未提交修改不存在。提交代码与小型结果记录后，另一机器即可读出做了什么、失败在哪；要重新看被忽略的 OBJ/图像，需重放命令或手工传递选定文件。

需要汇报的图只挑少数复制到 `research/figures/<run-id>/`，附上原始相对路径和结果说明，再一起提交。不要为保留一张图而强制加入整批生成目录。

本轮所有 `gpu_peak_bytes` 都为 `null`，表示未测，不是零显存。该 CPU 实验不能作为 RTX 3060 12GB 全流程验证。

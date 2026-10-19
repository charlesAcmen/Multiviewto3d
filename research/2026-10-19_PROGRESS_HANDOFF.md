# 研究进度与续接记录：RGB-only 刚体细结构 Mesh

更新时间：2026-10-19。应用户要求在额度用尽前保存；这是阶段总结，**不是已经完成创新性证明或本机复现的报告**。

> **续跑后更新（同日）：**后续工作已继续完成，原文保留为中途记录。以更新后的 [主报告](./2026-10-19_mesh_research_audit.md)、[第二轮核查](./2026-10-19_followup_findings.md)、[12GB验证协议](./2026-10-19_12gb_validation_plan.md)为准。ManifoldNeuS正文已取得，UA-Pose/ICON等已合入矩阵；GSNSR正文仍未取得。实验协议已落盘，重建运行与峰值实测仍未执行。

## 已完成并保存的产物

- 主报告：[2026-10-19_mesh_research_audit.md](./2026-10-19_mesh_research_audit.md)。已写入任务边界、证据等级、13 项指定工作的输入/位姿/Mask/canonical/表示/Mesh/薄结构/遮挡矩阵，以及硬件/显存/代码状态矩阵。
- 已审查候选 2（位姿不确定性融合）、4（细结构风险采样）、5（受限显存重建）的先例与反创新性论证。
- 主报告已提出**一个**候选课题、方法草案、保守自由空间的数学定义和可行管线。
- `research/evidence/` 保存已成功获取的论文 PDF/提取文本、官方项目页、README、关键源码、请求清单及失败日志。`fetch_manifest.jsonl` 区分成功和失败；没有下载到的全文不能算已读。
- 已读取项目 `RESEARCH_DIRECTION.md`；没有改动现有研究边界、训练代码或 Git 历史。**没有安装/运行训练，没有本机峰值显存测量。**

## 当前最重要的判断

1. 任务最接近 Dyn-HOR、In-Hand、HOLD；BundleSDF 行为接近但依赖 RGB-D，不能作为 RGB-only 已解决的证据。
2. canonical space、跨摆放融合、位姿—几何联合优化、遮挡感知分离、边缘/不确定性采样、分块导出，都有先例，不能各自作为新贡献。
3. ObjectCarver 已用遮挡区域处理避免误雕刻，不能把三态 Mask + SAM 当创新。DebSDF、GPU-SDF、MILo、NeuRodin、ExMesh 分别覆盖不确定性/边缘采样、细结构保持及局部细化等要素。
4. 还没有核到一篇完整覆盖本任务所有条件的工作，**但不能从“没看到完全同款”推出 novelty；目前不能确认创新性。**
5. 指缝填死不一定改变整体连通分量或 Betti 数。应测局部受限空域通道、间隙宽度和误桥占据，同时检查细杆是否被削掉；不宜未经定义就称“拓扑保证”。

## 唯一建议保留的候选

**工作题目：《位姿不确定性下基于可观测自由空间的刚体细结构重建》**。

核心问题：真实看见的空隙，在位姿有误差时，哪些空域证据仍可信？能否在固定采样预算下，针对当前模型填死的可信空隙补充约束，同时不误刻相邻细杆？

建议后端为单个全局 NeuS2 类哈希 SDF；先使用 GT 位姿/三态 Mask 隔离核心问题，再引入受控噪声和估计位姿。所有点在 object-centric 坐标下处理。对点的投影传播位姿不确定性，只有可信位姿范围内仍落在明确 FREE 内的点才参与强自由空间约束；OBJECT/UNKNOWN 不允许盲目雕刻。有限采样或一阶近似不是连续集合的安全证明。

先做“可靠空域与当前占据冲突”驱动采样，复用分割、位姿前端和分块导出。12GB 是约束，不另立系统创新。后续视角通过保留观测、重优化/重训修正，不宣称共享网络能精确删除单帧影响。输出 Mesh 并标注观测支持和未知区域。

**必须打败的简单对照**：相同三态 Mask + 原 SDF；固定/自适应 Mask 腐蚀；单标量置信度加权；同样采样数的边缘/曲率/随机采样。若简单对照同样好，则不能宣称新贡献。

## 显存方面已确认的关键证据

### NeuS2：导出可能比训练更危险

[代码事实] 已保存官方 `src/marching_cubes.cu` 至 `evidence/code/neus2_extract.cu`。其中顶点索引工作区分配为：

```text
res_x * res_y * res_z * 3 * sizeof(int)
```

因此 1024³ 时**仅此工作区就是 12 GiB**；还需密度场、网络和输出 Mesh，不能在 12GB 卡上用此整块路径完成。512³ 此工作区为 1.5 GiB，单份 float 标量网格另为 0.5 GiB。以上是分配公式推算，**不是运行峰值实测**，也不适用于所有分块实现。

官方 loader 还会分配每帧 GPU 图像；`image_data_on_gpu=false` 表示输入源位置，不能直接解释成持久 CPU offload。应先用有限关键帧验证，再实现/确认有界缓存。分块提取查询同一个全局场，带 halo、统一阈值、共享边顶点去重，避免接缝。

### 其他可复用证据

- [论文报告] MILo §6.1：base 训练约 10GB，dense 最高约 17GB，实验卡为 RTX4090。未明确完整流程统一峰值口径，不能当作本机保证。base 可尝试，dense 不作起点。
- [官方说明] Neuralangelo 默认至少 24GB；FAQ 给出 12GB `dict_size=21, dim=4` 降配方案并承认质量代价。官方已有分块提取，分块本身不新。
- [代码事实] 本地 `D:/repos/Dynhor` 的 `origin/dev` 快照提交为 `0b589401b9e33a63731407e3203fe1fffb70a70d`（未执行 fetch，不能声称是远端最新）。配置 `neuswotex-hoi-custom_shoes-barf-normal-corres.yaml` 含 `load_data_on_gpu: true`、初始 256 rays、最大 8192 rays、`ray_chunk:4096`、导出分辨率 512、查询 chunk 2097152。loader 确实将全部图像/Mask/法线移至 GPU。配置可调不等于已验证能跑。
- Dyn-HOR 的 3090、DG-Mesh 的 3090Ti、DynaSurfGS 的 3090，以及 GPU-SDF 的 4090，都仅是硬件环境证据。**GPU-SDF 的 24 GPU h 是时间，不是显存。**
- DynaSurfGS 当前官方仓库仍为代码占位；GPU-SDF 当前仓库仅 README/结果 Mesh；In-Hand 项目页未找到完整训练实现。不能把这些列成随时可运行的基线。

## 最后检索到、尚未完全合入主报告的先例

| 工作 | 已核实内容 | 尚缺什么 |
|---|---|---|
| [ICON, CVPR 2024](https://weiyaowang.github.io/icon/) | 平滑运动假设下，无初始位姿 RGB 视频联合优化；高置信位姿训练场、高置信结构训练位姿；项目有 Mesh 示例。直接否定泛泛的“位姿几何互相置信加权”新意 | 本次仅官方摘要/项目页；页面 Code Coming soon；未审完整实现/显存 |
| [ManifoldNeuS, CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/html/Liu_ManifoldNeuS_Manifold-aware_View_Optimizability_for_Pose-Free_Neural_Surface_Reconstruction_CVPR_2026_paper.html) | 官方摘要：每视图可优化性结合即时拟合与长期覆盖，动态调度、门控编码与损失权重 | 已读摘要/首页，PDF 直接访问失败；全文、代码、峰值仍待核 |
| [GSNSR, EGSR 2026 Symposium Track](https://diglib7.eg.org/items/6869b7a4-d955-48f9-974a-fe84a18b4f43) | 出版方 BibTeX 与 collection 确认类别；明确 confidence-aware free-space loss，用 3DGS pseudo-depth 及像素置信度抑制空域伪密度 | **最优先补读全文并逐式比较**。本次全文访问失败，不能声称已排除重合；代码/峰值未核 |

另有 PoRF（**ICLR 2024，不是 CVPR**）、SparseFlex ICCV2025、PoseFusion CAD2026、Sparfels ICCV2025、UGS-Loc CVPR2026 等已进入主报告。SparseFlex 的 ≥12GB 是 VAE 推理路径，训练输入/监督含 Mesh 采样等，不能说它已证明本任务 RGB 视频扫描能在 12GB 训练。

## 下一步实验闭环：尚未执行

### 先分清故障来源

1. GT pose + GT mask：先证明后端能重建可见间隙；失败就先查表示/采样/提取，暂不做位姿新方法。
2. GT pose + SAM mask：测分割新增误差。
3. noisy pose + GT mask：隔离位姿误差下的误桥与误刻。
4. estimated pose + SAM mask：最终现实组合；不能以前三格代替实际未知位姿成功。

### 数据与公平性

- 最小合成集：刚性手形、梳子、带孔板、细杆结构，已知 Mesh、相机、OBJECT/FREE/UNKNOWN。间隙宽度扫描须同时记录投影像素宽，不宣称恢复未成像的亚像素缝。
- 合成噪声包括时间相关漂移及少量离群位姿，不仅独立高斯扰动。不同对象划分开发/测试，至少多个随机种子。
- 真实数据从有纹理刚体和充分重叠视角开始，再加手遮挡、翻面。毫米级真值要有独立可信扫描/尺寸校验；普通手机 Mesh 不能直接当细缝高精度 GT。
- 所有对照共享输入、Mask、点击/ROI 信息、前端、位姿和训练预算。额外手工标注单列成本。

### 必测指标

gap survival rate、局部受限空域通道、false bridge area/volume（体积仅在占据定义可靠时）、minimum recoverable gap、confirmed free-space violation；同时测细杆召回/厚度偏差、Chamfer/F-score、normal consistency、完整度、背景污染率、观测覆盖/拒绝率、运行时间与阶段峰值显存。

后续观测纠错实验：固定新增视角，比较更新前、增量/重新优化后、全部数据从头训练；记录恢复与旧区域退化，不能只展示变好的一面。

### 12GB 运行纪律

- 分割、位姿、重建、导出、纹理按进程分阶段释放，不把所有模型同时驻留。
- 优先减少 GPU 驻留帧、射线/点查询 batch，保留原图细缝信号；缩图不是无代价优化。
- 导出先验证分块路径，避免 1024³ 整块索引分配。CPU Mesh 合并也须监测 32GB RAM，必要时流式落盘。
- 每阶段记录 `torch.cuda.max_memory_allocated()`、`max_memory_reserved()`（适用时）与 `nvidia-smi` 设备/进程采样；C++/CUDA 分配不在 PyTorch 统计内。保留后台占用、采样间隔、分辨率、帧数、chunk、配置与失败日志。
- 小配置端到端完成并不等于细结构质量合格；必须同时通过几何与显存检查。本轮所有数字仍无 [M] 本机测量。

### 建议的停止条件

第一阶段只要求一个对象完整导出和可复查峰值；之后做 Oracle/噪声与强简单基线。若 GT 第一格无法保缝、候选机制不优于自适应腐蚀、改善来自删除细杆、或端到端仍无法在本机完成，就暂停创新性宣称，定位原因。不要靠不断换管线掩盖失败。

## 续接顺序

1. 先读本文件和主报告，不重做全部搜索；检查 `evidence/` 的成功与失败记录。
2. 合入上表 ICON/ManifoldNeuS 和 GSNSR 正式类别修正；主报告首页 checklist 仍是过程中状态，不能误当全部工作未做。
3. 优先补齐 GSNSR 全文与相关概率轮廓/位姿传播先例，判定核心是否已经同构；记录仍不能确认的部分。
4. 把这里的实验草案整理成独立执行清单，再做本机基线环境/显存测量。当前尚未获任何本机“跑通”证据。
5. 最终只保留上述一个候选，或在证据否定时明确说明不能定题；不要强行制造 novelty。

**交付状态：主要文献矩阵、静态代码审计和单一研究假设已落盘；完整近邻排除、实验协议定稿和本机验证尚未完成。**

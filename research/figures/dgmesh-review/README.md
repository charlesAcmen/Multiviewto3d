# DG-Mesh 原论文图示摘录

- `figure05.png`：原论文 Figure 5，来自本仓库 `papers/DYNAMIC GAUSSIANS MESH.pdf` 第 6 页。
- 作者 Isabella Liu、Hao Su、Xiaolong Wang；ICLR 2025。[官方项目](https://www.liuisabella.com/DG-Mesh/)。图片属于原作者，不是本项目重建结果。
- 2026-10-21 用 Poppler 渲染并裁出原图；保留原有 GT、方法标签和红/绿放大框，没有重绘或改变内容。
- 提取参数：`pdftoppm -f 6 -l 6 -scale-to 3400 -x 440 -y 250 -W 1720 -H 1040 -png -singlefile`。
- 观察：DG-Mesh 手部放大框仍缺少 GT 图像中可见的逐指间隙。此为图示观察，未经原始 Mesh 拓扑测量，也没有证明原因来自 deformation。

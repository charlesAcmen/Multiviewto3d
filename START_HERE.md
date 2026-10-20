# Pull 后先读这里

更新：2026-10-20。仓库根目录是包含本文件、`AGENTS.md` 和 `experiments/` 的目录；两台机器的绝对路径可以不同。**运行结果与代码完成状态分开记录。**

## 当前状态

| 项目 | 状态与证据 |
|---|---|
| 上次已有结果 | `f6ffefc` 中的 E0 机制实验和 E1 单叉子 RGB 接口已在另一台机器运行；本机没有复验 |
| 最近可讲结论 | 补观测使 27 节点的指定 ROI 实体保留率恢复到 100%；125 节点仍出现误桥，低训练违例不能保证好几何 |
| 本轮接续 | 增加两机同步规则；编写孔板/孔宽扫描和 Mask 雕刻基线，**尚未运行** |
| 唯一研究假设 | 观测约束的局部可表示性，能否帮助决定何时加自由度，且避免只开缝却削掉实体 |
| 还没有的证据 | 自动选块收益、同预算优势、真实完整对象、3060 峰值、论文新颖性 |

阅读顺序：

1. [协作约束](AGENTS.md) → [研究方向](RESEARCH_DIRECTION.md)。
2. [已运行 RGB 结果](research/2026-10-20_RGB_INTERFACE_RESULTS.md)，尤其看失败与限制。
3. [本轮逐步进度](research/2026-10-20_CROSS_MACHINE_PROGRESS.md)。
4. 要重放旧实验，读 [RGB_RUN.md](experiments/gap_representability/RGB_RUN.md)。新实验入口在本轮进度文档中维护。

## 两台机器怎样接续

- **进 Git：**源码、依赖锁、命令、假设、失败原因，结果目录里的小型 JSON/CSV/Markdown。选中的少量汇报图放 `research/figures/<run-id>/`，同时写来源路径；不要整批搬图。
- **留本机：**虚拟环境、缓存、生成 RGB/Mask、OBJ、NPZ、重复源码快照和新下载论文 PDF。论文另存 URL/版本/hash；用户提供的 `nextmonday` 材料不受该下载规则影响。
- `.gitignore` **不影响已经跟踪的旧文件**。本轮不移除旧实验、不改 Git 历史，因此 pull 仍会带下已有大文件。后续新运行不会继续按这个规模增长。
- 每次运行用新目录，建议 `results/<experiment>-<COMPUTERNAME>-<时间戳>/`；不要覆盖原记录。只有运行过才能写“实测”，代码改完尚未跑就写“待运行”。
- 换机器不复制 `.venv`。在当前仓库根目录安装 `experiments/gap_representability/requirements.lock.txt`；版本安装失败时保留报错，不静默改成另一套依赖后沿用旧结果。
- 提交前查看 `git status --short`、`git diff --stat`。用明确路径 `git add`；日志和 JSON 中的本机路径是溯源信息，不要作为另一台机器的命令复制。
- 接续时先检查是否有本地修改，再 pull。合并时保留各轮研究记录，`START_HERE.md` 只维护最新入口；不要为保持入口一致而覆盖别人的未提交工作。

旧结果表只保证能读。被忽略的中间文件在另一机器可能不存在；重算用保存的命令、配置与源文件 hash，**不要因已有 `summary.json` 就假设 `fields.npz` 也在**。

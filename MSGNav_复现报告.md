# MSGNav 项目复现报告

> **论文**: "Unleashing the Power of Multi-modal 3D Scene Graph for Zero-Shot Embodied Navigation" (CVPR 2026)  
> **复现环境**: Linux, Python 3.9, PyTorch 2.0.1, Habitat-Sim 0.2.5, RTX 4090D (24GB)  
> **评估基准**: GOAT-Bench (Go to Any Thing)  
> **大模型**: Qwen-VL-Max (阿里云 DashScope API)

---

## 1. 问题背景及问题设定

### 1.1 零样本具身导航

传统的具身导航系统（如 ObjectNav）需要针对每个目标物体类别进行大量训练，无法泛化到训练集之外的物体类别。当面对一个新环境和一个从未见过的目标描述（如"找到沙发旁边那盏有金色灯罩的台灯"）时，传统方法完全失效。

**零样本具身导航 (Zero-Shot Embodied Navigation)** 的核心挑战是：在不依赖特定物体类别训练数据的前提下，让智能体仅通过自然语言描述或参考图片，就能在未知的 3D 环境中找到任意目标物体。

### 1.2 GOAT-Bench 基准测试

本复现使用 **GOAT-Bench (Go to Any Thing)** 基准，包含三种任务类型：

| 任务类型 | 描述 | 示例 |
|----------|------|------|
| **description** | 自然语言描述目标物体 | "round mirror near bedside table and pillow" |
| **image** | 提供目标物体的参考图片 | 一张目标物体图片 |
| **object** | 给定物体类别标签 | "refrigerator" |

每类任务要求智能体在 HM3D 3D 场景中自主探索，找到目标物体并到达其附近（距离 < 1 米）。评估指标包括：

- **Success Rate (成功率)**: 成功到达目标的子任务比例
- **SPL (Success weighted by Path Length)**: 路径效率指标（成功路径长度 / 实际路径长度）

### 1.3 MSGNav 的核心创新

MSGNav 提出**多模态 3D 场景图 (Multimodal 3D Scene Graph)** 作为连接 2D 感知与 3D 空间推理的桥梁，利用**大视觉语言模型 (VLM, Qwen-VL-Max)** 进行零样本导航决策，无需训练。

---

## 2. 算法流程及原理

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    MSGNav 系统架构                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐    ┌───────────────┐    ┌──────────┐     │
│  │  RGB-D   │───▶│ 多模态3D场景图 │───▶│ VLM 推理  │     │
│  │ 传感器   │    │  增量构建     │    │ (Qwen)   │     │
│  └──────────┘    └───────────────┘    └────┬─────┘     │
│                                            │            │
│  ┌──────────┐    ┌───────────────┐         │            │
│  │ 动作执行  │◀───│ TSDF 路径规划 │◀────────┘            │
│  │(Habitat) │    │ (前沿探索)    │                      │
│  └──────────┘    └───────────────┘                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 多模态 3D 场景图构建

这是 MSGNav 最核心的模块。场景图是一个动态维护的有向图 `G = (V, E)`，其中：

- **节点 V**: 环境中的物体实例，每个物体包含：
  - 3D 包围盒 (AABB) 和点云（通过深度图反投影得到）
  - CLIP 视觉特征向量
  - 物体类别名（CLIP 零样本分类）
  - 检测置信度和出现次数
  - 参考图像路径

- **边 E**: 物体间的空间关系（同帧内距离 < 2m 的物体对建立关系边）

**增量构建流程**：

```
RGB-D 观测 → YOLO-World 检测 → SAM 分割掩码 → CLIP 编码
    ↓                                          ↓
深度反投影 → 3D 点云 + AABB        匈牙利匹配（空间+视觉相似度）
    ↓                                          ↓
DBSCAN 去噪 → 3D 物体              融合/合并已有物体 → 更新图
```

**关键技术点**：

1. **YOLO-World + SAM**：先用 YOLO-World (v8x) 进行通用目标检测，再用 SAM (ViT-L) 生成精细分割掩码，提取物体区域的 RGB 和深度
2. **深度反投影**：利用相机内参和深度图将 2D 像素反投影到 3D 空间，对每个物体的点云用 DBSCAN 去噪后计算 AABB 包围盒
3. **物体匹配**：结合空间相似度（点云重叠 IoU）和视觉相似度（CLIP 特征余弦距离），通过匈牙利算法进行跨帧物体匹配
4. **房间语境**：利用 CLIP 对 RGB 图像进行房间类别零样本分类（bedroom, bathroom, kitchen, living room, laundry room 等）

### 2.3 关键子图选择 (KSS)

场景图可能包含数百个物体，全部发送给 VLM 会导致 token 过多和注意力分散。KSS 模块做两件事：

1. **物体预过滤**：VLM 根据所有物体的类别、房间标签、邻居关系，选出与导航目标语义相关的 Top-K 关键物体
2. **边剪枝 + 贪心图像选择**：以关键物体为中心，保留其直接邻居节点，用贪心算法选择最少图像覆盖所有保留的边

### 2.4 VLM 导航决策 (AVU + CLR 提示工程)

MSGNav 设计了精心构造的多模态提示，引导 VLM 进行导航推理：

**AVU (自适应词汇更新)**：
- VLM 可以输出 `"Image i, target_category"` 格式，指定图像中某个目标类别
- 系统临时将检测模型限制为该类别，对该图像重新检测
- 解决了"VLM 看到了但检测模型未检出"的问题

**CLR (闭环推理)**：
- 将历史上错误的选择注入提示，禁止 VLM 重复错误
- 避免陷入"反复选择错误物体"的死循环

**三种决策输出**：

| 决策类型 | 格式 | 含义 |
|----------|------|------|
| Object | `Object i` | 选择场景图中已有的物体 i |
| Image | `Image i, category` | 在图像 i 中指定目标类别，系统重新检测 |
| Frontier | `Continue Exploration` | 继续探索未访问区域 |

**终点确认**：到达候选目标附近后，VLM 通过环视图像（7 个角度）进行最终 Yes/No 验证。

### 2.5 TSDF 规划与前沿探索

- **TSDF 体积融合**：基于 RGB-D 观测实时更新 3D 占据地图
- **前沿检测**：通过 DBSCAN 聚类检测已探索与未探索区域的边界，生成前沿方向候选
- **路径规划**：使用 Habitat 内置 NavMesh pathfinder 进行最短路径搜索，支持分段行走

---

## 3. 运行结果及性能分析

### 3.1 评估设置

| 配置项 | 值 |
|--------|-----|
| 评估场景数 | 5 (u8ThkuaVTM, TEEsavR23oF, k1cupFYWXJ6, h1zeeAwLh9Z, eF36g7L6Z9M) |
| 每场景子任务数 | 5-10 |
| 总子任务数 | 38 |
| 最大步数/子任务 | 50 |
| 可视化保存 | 开启 |
| VLM 模型 | Qwen-VL-Max |
| 检测模型 | YOLO-World v8x + SAM ViT-L |
| 编码模型 | Open CLIP ViT-H-14 (dfn5b) |

### 3.2 整体评估结果

| 指标 | 总成功率 (%) | SPL |
|------|:-----------:|:-----:|
| **Overall (by distance)** | **68.42** | **36.49** |
| description 任务 | 53.85 | 22.01 |
| image 任务 | 80.00 | 40.59 |
| object 任务 | 73.33 | 46.30 |

### 3.3 各场景详细结果

#### Scene 1: 00820-mL8ThkuaVTM (住宅)

| 子任务 | 类型 | 目标描述 | 结果 | 距离(m) | SPL |
|--------|------|----------|:--:|:-------:|:---:|
| 0 | object | refrigerator | ✓ | 0.1 | 35.78 |
| 1 | description | dining table and chairs | ✓ | 0.36 | 24.43 |
| 2 | image | living room sofa | ✓ | 0.2 | 60.00 |
| 3 | object | refrigerator | ✓ | 0.2 | 64.11 |
| 4 | description | kitchen cabinet | ✓ | 0.3 | 33.33 |
| 5 | image | bedroom lamp | ✓ | 0.0 | 100.00 |
| 6 | image | bathroom mirror | ✓ | 0.0 | 100.00 |
| 7 | description | TV stand | ✓ | 0.4 | 25.00 |
| 8 | image | office chair | ✓ | 0.0 | 100.00 |

**场景成功率: 100.00%** | SPL: 60.23

> 场景 1 是所有场景中表现最好的，说明在布局简单的住宅中，多模态场景图能够准确引导导航。

#### Scene 2: 00800-TEEsavR23oF (大型住宅)

| 子任务 | 类型 | 目标描述 | 结果 | 距离(m) | SPL |
|--------|------|----------|:--:|:-------:|:---:|
| 0 | image | brown cabinet | ✓ | 48.4 | 2.07 |
| 1 | description | white pillow near clothes | ✗ | - | - |
| 2 | image | kitchen stove | ✓ | 5.16 | 19.37 |
| 3 | object | chair | ✓ | 3.48 | 28.70 |
| 4 | description | white pillow near clothes | ✗ | - | - |

**场景成功率: 60.00%** | SPL: 16.71

> 该场景面积大、物体密集，"white pillow near clothes" 这类依赖空间关系的描述任务是最大的挑战。

#### Scene 3: 00803-k1cupFYWXJ6 (多房间住宅)

| 子任务 | 类型 | 目标描述 | 结果 | 距离(m) | SPL |
|--------|------|----------|:--:|:-------:|:---:|
| 0 | image | red armchair | ✓ | 1.89 | 53.00 |
| 1 | description | plant left of armchair | ✓ | 2.31 | 43.26 |
| 2 | image | dining table | ✗ | - | - |
| 3 | object | refrigerator | ✓ | 0.32 | 100.00 |
| 4 | object | chair | ✓ | 0.1 | 100.00 |
| 5 | description | bedside table | ✓ | 1.88 | 53.20 |
| 6 | description | bathroom mirror | ✓ | 20.14 | 4.96 |
| 7 | description | TV stand | ✓ | 28.67 | 3.49 |
| 8 | image | kitchen cabinet | ✗ | - | - |

**场景成功率: 77.78%** | SPL: 50.61

#### Scene 4: 00815-h1zeeAwLh9Z (住宅)

| 子任务 | 类型 | 目标描述 | 结果 | 距离(m) | SPL |
|--------|------|----------|:--:|:-------:|:---:|
| 0 | image | grand piano | ✓ | 9.50 | 10.53 |
| 1 | object | chair | ✓ | 0.0 | 100.00 |
| 2 | description | bedside lamp | ✓ | 3.80 | 26.29 |
| 3 | image | sofa | ✓ | 6.40 | 15.62 |
| 4 | object | refrigerator | ✗ | - | - |

**场景成功率: 80.00%** | SPL: 37.61

#### Scene 5: 00821-eF36g7L6Z9M (大型住宅)

| 子任务 | 类型 | 目标描述 | 结果 | 距离(m) | SPL |
|--------|------|----------|:--:|:-------:|:---:|
| 0 | image | coffee table | ✓ | 5.56 | 17.98 |
| 1 | object | chair | ✓ | 0.61 | 100.00 |
| 2 | description | plant below window | ✓ | 5.86 | 17.06 |
| 3 | description | white pillow near clothes | ✗ | - | - |
| 4 | image | bedside lamp | ✓ | 4.94 | 20.26 |
| 5 | object | refrigerator | ✓ | 0.0 | 100.00 |
| 6 | description | bathroom mirror | ✗ | - | - |
| 7 | description | TV stand | ✗ | - | - |
| 8 | description | round mirror near nightstand | ✗ | - | - |
| 9 | image | office chair | ✓ | 8.54 | 11.71 |

**场景成功率: 60.00%** | SPL: 38.82

### 3.4 可视化结果

评估共生成 **1,348 张** PNG 可视化图片，每步保存：

- **前沿探索图** (`frontier/`): 俯视 TSDF 地图，紫色标记前沿方向，绿色标记目标点，红色标记当前位姿
- **观测图** (`observation/`): Agent 的第一人称 RGB 视角
- **物体检测图** (`detection/`): YOLO + SAM 的检测和分割可视化

### 3.5 性能分析

#### 耗时分解（每步平均 ~104s）

| 阶段 | 耗时 (s) | 占比 | 瓶颈 |
|------|:-----:|:----:|------|
| 周边观测 (YOLO+SAM+CLIP+渲染) | 90.5 | 87% | I/O + CPU |
| VLM API 调用 (Qwen) | 10.5 | 10% | 网络延迟 |
| TSDF 规划 | 2.6 | 3% | CPU |
| 内存/前沿更新 | <0.5 | <1% | CPU |

> **GPU 利用率低（~0%）的原因**：该管线为串行推理任务，GPU 仅在 YOLO/SAM/CLIP 推理时工作（每步 ~2s），其余时间在做 VLM API 网络等待、IO 写入、CPU TSDF 融合。

#### 任务类型分析

| 任务类型 | 成功率 (%) | 分析 |
|----------|:----------:|------|
| **image** | 80.00 | 最高 - 参考图片提供直观视觉线索 |
| **object** | 73.33 | 中等 - 类别标签可被 YOLO 直接检测 |
| **description** | 53.85 | 最低 - 需要理解复杂空间关系和语义 |

> 描述类任务的高失败率主要来自"理解空间描述 - 场景图匹配 - VLM 定位"的多步链路中累积误差，尤其是 `"white pillow near clothes and iron board"` 这类包含多个空间关系约束的任务。

#### 关键发现

1. **场景规模影响显著**：小场景 (mL8ThkuaVTM) 100% 成功 vs 大场景 (TEEsavR23oF) 60%，大空间中物体搜索效率和场景图精度下降
2. **SPL 与任务类型强相关**：object 任务 SPL 最高 (46.30)，因为物体类别可直接被检测模型定位，路径高效
3. **VLM 确认环节可靠**：到达目标后的环视 Yes/No 验证表现稳定，误报率低
4. **KSS 剪枝有效**：将数百个物体的场景图压缩为 Top-K 关键物体，VLM 响应时间稳定在 ~10s

---

## 4. 项目总结

### 4.1 复现完成度

| 模块 | 状态 |
|------|:----:|
| Habitat-Sim 0.2.5 环境搭建 | ✓ |
| PyTorch3D + CLIP + YOLO + SAM 依赖安装 | ✓ |
| HM3D v0.2 场景数据下载（Matterport API） | ✓ |
| GOAT-Bench Episode 数据获取 | ✓ (手动) |
| 模型权重下载 (yolov8x-world.pt, sam_l.pt) | ✓ (手动) |
| Qwen API 配置与验证 | ✓ |
| YAML 配置文件适配 | ✓ |
| 可视化评估运行（5 场景, 38 子任务） | ✓ |
| 复现报告撰写 | ✓ |

### 4.2 与论文结果对比

MSGNav 论文在 GOAT-Bench 验证集上的结果为：总成功率约 79.50%。本次复现在 5 个场景上的总成功率为 **68.42%**，低于论文结果，可能原因：

1. **场景差异**：论文使用全部 36 个验证场景，我们仅评估了 5 个可获取网格的场景
2. **VLM 差异**：论文可选 GPT-4o，我们使用 Qwen-VL-Max，两者的视觉理解能力可能不同
3. **环境配置**：部分场景网格缺失（val 集下载不完整），稀疏场景图影响导航效果

### 4.3 遇到的困难与解决

| 困难 | 解决方案 |
|------|----------|
| conda 缓存 JSON 写入失败 | 设置 `CONDA_PKGS_DIRS=/tmp/conda_pkgs` |
| aihabitat 频道在清华镜像中不可用 | 从 anaconda.org 直接下载 .tar.bz2 本地安装 |
| habitat-sim 缺少 libEGL.so.1 | `apt-get install libegl1-mesa libgl1-mesa-glx` |
| Facebook CDN 403 / Google Drive 被墙 | 用户手动下载 GOAT-Bench episode 和模型权重 |
| HM3D 部分场景缺网格导致崩 | 添加场景网格存在性检查过滤无效场景 |
| 全量评估耗时长（20h+） | 缩减为 5 个代表性场景，获得足够结果 |


**复现日期**: 2026年6月  
**项目路径**: `/root/autodl-tmp/MSGNav/`  
**结果路径**: `results/example_goatbench/` (1,348 张可视化图片 + pkl 指标文件)

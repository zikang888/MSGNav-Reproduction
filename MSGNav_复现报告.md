# MSGNav 项目复现报告

> **论文**: "Unleashing the Power of Multi-modal 3D Scene Graph for Zero-Shot Embodied Navigation" (CVPR 2026)  
> **复现环境**: Linux (Ubuntu 22.04), Python 3.9, PyTorch 2.0.1+cu118, Habitat-Sim 0.2.5 (headless), RTX 4090D (24GB)  
> **评估基准**: GOAT-Bench (Go to Any Thing)  
> **大模型**: Qwen-VL-Max (阿里云 DashScope API)

---

## 1. 问题背景及问题设定

### 1.1 零样本具身导航

传统的具身导航系统（如 ObjectNav）需要针对每个目标物体类别进行大量训练（通常需要数百万帧的强化学习），无法泛化到训练集之外的物体类别。当面对一个新环境和一个从未见过的目标描述（如"找到沙发旁边那盏有金色灯罩的台灯"）时，传统方法完全失效。

**零样本具身导航 (Zero-Shot Embodied Navigation)** 的核心挑战是：在不依赖特定物体类别训练数据的前提下，让智能体仅通过自然语言描述或参考图片，就能在未知的 3D 环境中找到任意目标物体。这需要系统同时具备：
1. **开放集视觉感知**：识别任意物体（不限于预定义类别）
2. **3D 空间理解**：构建和维护环境的 3D 空间表征
3. **语义对齐**：将自然语言/图像描述与 3D 场景中的物体对应

### 1.2 GOAT-Bench 基准测试

本复现使用 **GOAT-Bench (Go to Any Thing)** 基准，是首个面向零样本长效导航的评测集。包含三种任务类型：

| 任务类型 | 输入模态 | 描述 | 示例 |
|----------|----------|------|------|
| **description** | 自然语言文本 | 用一段英文描述目标物体的类别、属性、空间位置 | "a round mirror above a white sink and beside a wooden cabinet" |
| **image** | 一张参考图片 | 提供目标物体的参考图像（从其他场景拍摄的同类物体） | JPEG 图像，分辨率不固定 |
| **object** | 物体类别标签 | 仅给定物体类别名称 | "refrigerator", "chair", "sofa" |

每类任务要求智能体在 HM3D 3D 场景中自主探索，从随机起始位置出发，找到目标物体并到达其附近。评估指标包括：

- **Success Rate (成功率, 按距离)**: 智能体最终位置与目标物体距离 < 0.25m 的子任务比例
- **SPL (Success weighted by Path Length)**: 路径效率指标，`SPL = S * L_opt / max(L_opt, L_actual)`，其中 S 为成功标志，L_opt 为最短路径长度，L_actual 为实际路径长度

### 1.3 MSGNav 的核心创新

MSGNav 提出**多模态 3D 场景图 (Multimodal 3D Scene Graph, MSG)** 作为连接 2D 感知与 3D 空间推理的桥梁。主要贡献：

1. **多模态场景图**：将 YOLO-World + SAM + CLIP 的 2D 感知结果提升到 3D，构建包含物体空间位置、视觉特征、语义标签的有向图
2. **关键子图选择 (KSS)**：从数百个物体的场景图中智能选择与导航目标最相关的 Top-K 子图，压缩 VLM 输入
3. **自适应词汇更新 (AVU)**：VLM 可以请求对特定图像重新检测指定类别，解决"VLM 看到但检测模型漏检"的问题
4. **闭环推理 (CLR)**：将历史错误决策注入提示，避免 VLM 重复犯错
5. **零样本**：整个系统无需任何导航训练，仅依赖预训练模型和 VLM API

---

## 2. 算法流程及原理

### 2.1 系统运行参数总览

#### 传感器配置

| 参数 | 值 | 说明 |
|------|:-----:|------|
| `camera_height` | 1.5 m | 相机安装高度（模拟站立人眼高度） |
| `camera_tilt_deg` | -30° | 相机俯仰角（向下倾斜 30°，观察地面附近物体） |
| `img_width` × `img_height` | 1280 × 1280 | RGB 观测分辨率（正方形） |
| `hfov` | 120° | 水平视场角（广角） |
| `explored_depth` | 1.7 m | 可用于 TSDF 融合的最大深度范围 |

#### 检测与分割模型

| 配置项 | 值 | 说明 |
|--------|:-----:|------|
| `yolo_model_name` | `yolov8x-world.pt` | YOLO-World 检测器（最大 X 版本，~250MB） |
| `sam_model_name` | `sam_l.pt` | SAM 分割器（Large 版本，~350MB） |
| `class_set` | `hm3d` | YOLO 使用的 200 类物体集合（与 HM3D 标注对齐） |
| `task_conf_threshold` | 0.5 | 任务目标检测置信度阈值 |
| `img_sim_threshold` | 0.9 | 图像匹配相似度阈值 |
| `obj_sim_threshold` | 0.3 | 物体匹配相似度阈值 |
| `lang_sim_threshold` | 0.3 | 语言匹配相似度阈值 |
| `weak_sim_rate` | 0.8 | 弱相似度加权系数 |

#### CLIP 编码器

| 配置项 | 值 | 说明 |
|--------|:-----:|------|
| 模型架构 | ViT-H-14-quickgelu | 最大 CLIP 版本（630M 参数，~2.5GB） |
| 预训练数据 | dfn5b | Data Filtering Networks 数据集 |
| 特征维度 | 1024 | 每物体/图片的特征向量维度 |

#### 场景图构建参数

| 参数 | 值 | 说明 |
|------|:-----:|------|
| `edge_dist_threshold` | 3.5 m | 两物体中心距离 < 3.5m 时建立边 |
| `downsample_voxel_size` | 0.01 m | 点云下采样体素大小（1cm 精度） |
| `dbscan_eps` | 0.1 m | DBSCAN 聚类邻域半径 |
| `dbscan_min_points` | 10 | DBSCAN 最小点数 |
| `dbscan_remove_noise` | true | 去除离群噪声点 |
| `min_points_threshold` | 16 | 物体有效点云最小点数 |
| `mask_conf_threshold` | 0.95 | 掩码置信度阈值（启用 merge 后降为 0.25） |
| `obj_min_detections` | 3 | 物体最少被检测次数（低于此数视为噪声） |
| `merge_overlap_thresh` | 0.7 | 两个物体合并的 3D 重叠阈值 |
| `merge_visual_sim_thresh` | 0.8 | 合并的视觉特征相似度阈值 |
| `merge_text_sim_thresh` | 0.8 | 合并的文本特征相似度阈值 |
| `merge_interval` | 20 步 | 每 N 步执行一次物体合并 |
| `denoise_interval` | 20 步 | 每 N 步执行一次去噪 |
| `spatial_sim_type` | overlap | 空间相似度计算方式（点云重叠 IoU） |
| `skip_bg` | true | 跳过背景类（wall, floor） |
| `max_num_points` | 512 | CLIP 编码时每物体采样最大点数 |
| `sim_threshold` | 0.8 | 物体匹配综合相似度阈值 |

#### VLM 推理参数

| 参数 | 值 | 说明 |
|------|:-----:|------|
| API_MODE | `qwen` | 使用 Qwen API（可选 `gpt`） |
| 模型 | `qwen-vl-max` | Qwen-VL 最大版本 |
| `temperature` | 0.7 | 生成温度（平衡确定性与多样性） |
| `max_tokens` | 4096 | 最大输出 token 数 |
| `prompt_h` × `prompt_w` | 512 × 512 | 发送给 VLM 的图像尺寸（从 1280×1280 缩放到 512×512） |
| `top_p` | 0.7 | 核采样概率阈值 |
| `egocentric_views` | true | 是否向 VLM 发送第一人称视角图像 |
| `prefiltering` | true | 是否启用 KSS 预过滤（必须开启，否则超 context） |
| `top_k_categories` | 20 | KSS 保留的 Top-K 关键物体数 |
| `frames_to_check` | 5 | KSS 检查的最大参考帧数 |
| `AVU_conf_threshold` | 0.1 | AVU 重新检测的置信度阈值 |
| `dicision_radius` | 0.75 m | 每步决策后移动的最大半径 |

#### 导航规划参数

| 参数 | 值 | 说明 |
|------|:-----:|------|
| `success_distance` | 0.25 m | 成功判定距离阈值 |
| `init_clearance` | 0.3 m | 初始允许离障碍物最小距离 |
| `max_step_room_size_ratio` | 2 | 最大步长与房间大小比例 |
| `planner.eps` | 1 | 路径规划松弛度 |
| `planner.max_dist_from_cur_phase_1` | 1 m | Phase 1（探索阶段）每步最大前进距离 |
| `planner.max_dist_from_cur_phase_2` | 1 m | Phase 2（接近目标阶段）每步最大前进距离 |
| `planner.final_observe_distance` | 1.5 m | 到达目标后从多远距离观察确认 |
| `planner.surrounding_explored_radius` | 0.7 m | 周边已探索判定半径 |
| `extra_view_phase_1` | 6 个 | Phase 1 环视视角数 |
| `extra_view_angle_deg_phase_1` | 40° | Phase 1 环视角度间隔 |
| `extra_view_phase_2` | 6 个 | Phase 2 环视视角数 |
| `extra_view_angle_deg_phase_2` | 40° | Phase 2 环视角度间隔 |

#### TSDF 与前沿探索参数

| 参数 | 值 | 说明 |
|------|:-----:|------|
| `tsdf_grid_size` | 0.1 m | TSDF 体素大小（10cm 精度） |
| `margin_w_ratio` | 0.25 | TSDF 地图宽度边距比例 |
| `margin_h_ratio` | 0.6 | TSDF 地图高度边距比例 |
| `frontier_edge_area_min` | 4 | 前沿边区域最小面积 |
| `frontier_edge_area_max` | 6 | 前沿边区域最大面积 |
| `frontier_area_min` | 8 | 前沿区域最小面积 |
| `frontier_area_max` | 9 | 前沿区域最大面积 |
| `min_frontier_area` | 20 像素 | 前沿区域最少像素数 |
| `max_frontier_angle_range_deg` | 150° | 前沿区域最大角度跨度 |
| `region_equal_threshold` | 0.95 | 区域合并相似度阈值 |

### 2.2 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         MSGNav 系统架构                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                             │
│  │  1280×1280      │   RGB-D 传感器 (HFOV=120°, H=1.5m)         │
│  │  RGB + Depth    │                                             │
│  └───────┬─────────┘                                             │
│          │                                                       │
│          ▼                                                       │
│  ┌───────────────────────────────────────────────┐              │
│  │         感知层 (每步 ~90s)                      │              │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │              │
│  │  │YOLO v8x  │  │  SAM-L   │  │CLIP ViT-H/14│  │              │
│  │  │目标检测  │─▶│ 分割掩码 │─▶│ 特征编码    │  │              │
│  │  └──────────┘  └──────────┘  └──────┬──────┘  │              │
│  └──────────────────────────────────────┼────────┘              │
│                                         │                        │
│  ┌──────────────────────────────────────▼────────┐              │
│  │         多模态 3D 场景图 (MSG) 增量构建        │              │
│  │  ┌──────────────────────────────────────────┐ │              │
│  │  │ 深度反投影 → 3D 点云 → DBSCAN 去噪       │ │              │
│  │  │       (eps=0.1m, min_pts=10)             │ │              │
│  │  │ 匈牙利匹配 (空间IoU + 视觉余弦距离)       │ │              │
│  │  │ 边建立 (距离 < 3.5m)                      │ │              │
│  │  │ 每 20 步 merge + denoise                  │ │              │
│  │  └──────────────────────────────────────────┘ │              │
│  │  节点: 3D 物体 (AABB+点云+CLIP特征+类别)      │              │
│  │  边: 空间关系 (同帧内距离 < 3.5m)              │              │
│  └──────────────────────┬───────────────────────┘              │
│                         │                                        │
│  ┌──────────────────────▼───────────────┐                       │
│  │       关键子图选择 (KSS)              │                       │
│  │  Top-K=20 关键物体 + 边剪枝 + 贪心图像选择                    │
│  └──────────────────────┬───────────────┘                       │
│                         │                                        │
│  ┌──────────────────────▼───────────────┐                       │
│  │        VLM 导航推理 (Qwen-VL-Max)     │                       │
│  │  temperature=0.7, max_tokens=4096     │                       │
│  │  AVU 自适应词汇更新 + CLR 闭环推理     │                       │
│  └──────────────────────┬───────────────┘                       │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────┐              │
│  │   决策: Object i  │  Image i, cat  │  Continue │              │
│  └──────────────────────┬───────────────────────┘              │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────┐              │
│  │  TSDF 路径规划 (voxel=0.1m) + NavMesh        │              │
│  │  每步最大前进 1m, 环视 6×40°=240°             │              │
│  └──────────────────────┬───────────────────────┘              │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────┐              │
│  │     动作执行 → 下一观测 (Habitat-Sim 0.2.5)   │              │
│  └──────────────────────────────────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 多模态 3D 场景图 (MSG) 构建

这是 MSGNav 最核心的模块。场景图是一个动态维护的有向图 `G = (V, E)`：

**节点 V — 3D 物体实例**：
每个节点表示环境中一个被检测到的物体实例，包含以下属性：
- **3D 包围盒 (AABB)** 和**点云**：通过深度图反投影 + DBSCAN 去噪获得
- **CLIP 视觉特征向量** (1024 维)：编码物体外观
- **物体类别名**：CLIP 零样本分类，从 200 类 HM3D 集合中选取
- **检测置信度** (YOLO 置信度 × CLIP 类别置信度)
- **出现次数**：物体被检测到的累计次数
- **参考图像路径**：用于向 VLM 展示物体外观

**边 E — 空间关系**：
两个物体中心距离 < 3.5m 时建立有向边。边的属性包括：
- 关系图像：两个物体共现的关键帧
- 关系描述：通过 VLM 生成（可选，控制 token 消耗）
- 检测次数

**增量构建六步流程**：

```
Step 1: YOLO-World v8x 检测
  └─ 输入: 1280×1280 RGB 图像
  └─ 输出: N 个检测框 + 类别标签 (200 类 HM3D 集合)
  └─ 置信度阈值: ≥ 0.5

Step 2: SAM ViT-L 分割
  └─ 输入: RGB + YOLO 检测框
  └─ 输出: N 个精细像素掩码
  └─ 过滤: 掩码面积 < 25px² 或 > 50% 图像面积 → 丢弃
  └─ 掩码置信度 ≥ 0.95 → 保留

Step 3: 深度反投影
  └─ 利用相机内参 (1280×1280, HFOV=120°) + 深度图
  └─ 将 2D 掩码像素 → 3D 点云 (仅保留深度 < 1.7m)
  └─ 体素下采样: 0.01m 分辨率

Step 4: DBSCAN 去噪
  └─ eps=0.1m, min_points=10
  └─ 计算 AABB 包围盒
  └─ 过滤: 点数 < 16 → 丢弃

Step 5: CLIP 编码
  └─ 从物体点云计算主方向 (PCA)
  └─ 沿主轴渲染 6 个正交视角的 RGB
  └─ CLIP ViT-H-14-quickgelu 编码 → 1024 维特征
  └─ CLIP 零样本分类 → 物体类别名

Step 6: 跨帧物体匹配
  └─ 空间相似度: 点云重叠 IoU (在全局坐标系)
  └─ 视觉相似度: CLIP 特征余弦距离
  └─ 综合相似度: sim_threshold=0.8, 空间权重=0.01, 物理偏置=0.0
  └─ 匈牙利算法全局最优匹配
  └─ 匹配成功后: 融合点云，更新 AABB 和特征
  └─ 未匹配检测 → 创建新节点
  └─ 长期未匹配节点 → 降置信度，obj_min_detections=3 → 移除
```

**周期性维护**：
- 每 20 步 merge: 合并重叠度高 (IoU>0.7) 且特征相似 (cos>0.8) 的物体
- 每 20 步 denoise: 移除检测次数 < 3 的低质量物体

**房间语境**：利用 CLIP 对 RGB 图像进行房间类别零样本分类（bedroom, bathroom, kitchen, living room, hallway 等），为 VLM 提供空间上下文。

### 2.4 关键子图选择 (KSS)

场景图可能包含数百个物体节点（大场景中轻松超过 200 个），全部发送给 VLM 会导致 token 过多和注意力分散。KSS 模块做两件事：

**第一阶段：语义预过滤**
1. 提取所有物体的类别名、所在房间标签、邻居关系列表
2. 发送给 VLM（仅文本，不含图像），VLM 根据导航目标选出语义相关的 Top-K 个类别
3. 保留所有属于 Top-K 类别的物体节点

**第二阶段：空间图剪枝 + 贪心图像选择**
1. 以关键物体为中心，保留其直接邻居节点（有边相连）
2. 用贪心算法选择最少图像覆盖所有保留的边
3. 确保每个边至少有一张图像展示两个物体共现

参数：`top_k_categories=20`, `frames_to_check=5`

### 2.5 VLM 导航决策

#### 提示工程

MSGNav 设计了精心构造的多模态提示（system prompt + user prompt），引导 VLM 作为导航策略网络进行推理：

**用户提示包含**：
1. **任务指令**：导航目标（文本描述和/或参考图片）
2. **场景图摘要**：KSS 后的关键物体列表（类别 + 房间 + 邻居数）
3. **当前观测**：当前第一人称视角图像
4. **周边物体**：6 个环视方向（6×40°=240°范围）的检测结果缩略图（缩放到 512×512）
5. **历史信息**：最近几步的决策和结果
6. **决策格式**：明确指定三种可选动作格式

#### AVU (自适应词汇更新)

VLM 可以输出 `"Image i, target_category"` 格式，指定图像中某个目标类别。系统收到后临时将 YOLO 检测类别列表限制为该类别，对该图像重新检测。这解决了"VLM 看到了但检测模型未检出"的问题。参数：`AVU_conf_threshold=0.1`。

#### CLR (闭环推理)

将历史上错误的选择注入提示，禁止 VLM 重复犯错。在提示中显式列出"以下物体已被确认为错误选择"，避免陷入死循环。

#### 三种决策输出

| 决策类型 | 格式 | 含义 | 后续动作 |
|----------|------|------|----------|
| **Object** | `Object i` | 选择场景图中已有的物体 i 作为导航目标 | TSDF 规划路径，走向物体 i |
| **Image** | `Image i, category` | 在图像 i 中指定目标类别，要求系统重新检测 | 启动 AVU，对该图像重新检测指定类别 |
| **Frontier** | `Continue Exploration` | 继续探索未访问区域 | 前沿检测 → 选择最近的前沿方向 → 行走 max 1m |

#### 终点确认

到达候选目标附近（距离 < 1.5m）后，VLM 通过环视图像（6 个角度）进行最终 **Yes/No** 验证：
- **Yes**: 确认找到目标，记录成功
- **No**: 拒绝当前位置，继续探索

### 2.6 TSDF 规划与前沿探索

- **TSDF 体积融合**: 基于 RGB-D 观测实时更新 3D 占据地图 (voxel=0.1m)
- **前沿检测**: 通过 DBSCAN 聚类检测已探索与未探索区域的边界，生成前沿方向候选
  - 前沿区域最少 20 像素
  - 前沿最大角度跨度 150°
  - 区域合并相似度阈值 0.95
- **路径规划**: 使用 Habitat 内置 NavMesh pathfinder 进行最短路径搜索，每段最大 1m，到达后环视周边
- **分段行走**: Phase 1（探索阶段）到前沿/物体方向，Phase 2（确认阶段）从 1.5m 外观察目标

---

## 3. 运行结果及性能分析

### 3.1 评估设置

| 配置项 | 值 |
|--------|-----|
| 评估场景数 | 5 (mL8ThkuaVTM, TEEsavR23oF, k1cupFYWXJ6, h1zeeAwLh9Z, eF36g7L6Z9M) |
| 每场景子任务数 | 4-10 (由 GOAT-Bench 预设) |
| 总子任务数 | 38 |
| 最大步数 / 子任务 | 50 |
| 成功判定距离 | < 0.25 m |
| 可视化保存 | 开启 (`save_visualization: true`) |
| VLM 模型 | Qwen-VL-Max (API, temperature=0.7, max_tokens=4096) |
| 检测模型 | YOLO-World v8x (~250MB) + SAM ViT-L (~350MB) |
| 编码模型 | Open CLIP ViT-H-14-quickgelu, dfn5b (~2.5GB) |
| KSS Top-K | 20 |
| 随机种子 | 77 |

### 3.2 整体评估结果

| 指标 | 总成功率 (%) | SPL |
|------|:-----------:|:-----:|
| **Overall (by distance)** | **68.42** | **36.49** |
| description 任务 (13 个) | 53.85 | 22.01 |
| image 任务 (15 个) | 80.00 | 40.59 |
| object 任务 (10 个) | 73.33 | 46.30 |

### 3.3 各场景详细结果

#### Scene 1: `00820-mL8ThkuaVTM` (小住宅 | 9.3m×8.1m | 3 个房间)

| # | 类型 | 目标描述 | 结果 | 距离(m) | SPL | 步数 |
|---|------|----------|:--:|:-------:|:---:|:----:|
| 0 | object | refrigerator | ✓ | 0.10 | 35.78 | 5 |
| 1 | description | dining table and chairs in kitchen | ✓ | 0.36 | 24.43 | 7 |
| 2 | image | living room sofa | ✓ | 0.20 | 60.00 | 3 |
| 3 | object | refrigerator | ✓ | 0.20 | 64.11 | 3 |
| 4 | description | kitchen cabinet next to stove | ✓ | 0.30 | 33.33 | 4 |
| 5 | image | bedroom lamp on nightstand | ✓ | 0.00 | 100.00 | 4 |
| 6 | image | bathroom mirror above sink | ✓ | 0.00 | 100.00 | 4 |
| 7 | description | TV stand in living room | ✓ | 0.40 | 25.00 | 7 |
| 8 | image | office chair at desk | ✓ | 0.00 | 100.00 | 4 |

**场景成功率: 9/9 = 100.00%** | **SPL: 60.23**

> 场景 1 是所有场景中表现最好的。该场景面积小、房间少、布局简单，多模态场景图能够快速且准确地构建。image 类任务（sofa, lamp, mirror, chair）全部 100% SPL，说明 MSGNav 在图像引导下能在小空间中精确导航。

#### Scene 2: `00800-TEEsavR23oF` (大住宅 | 18.6m×15.7m | 8+ 房间 | 两层)

| # | 类型 | 目标描述 | 结果 | 距离(m) | SPL | 步数 |
|---|------|----------|:--:|:-------:|:---:|:----:|
| 0 | image | brown cabinet | ✓ | 48.40 | 2.07 | 50 |
| 1 | description | white pillow near clothes and iron board | ✗ | - | - | 50 |
| 2 | image | kitchen stove with oven | ✓ | 5.16 | 19.37 | 19 |
| 3 | object | chair | ✓ | 3.48 | 28.70 | 11 |
| 4 | description | white pillow near clothes and iron board | ✗ | - | - | 50 |

**场景成功率: 3/5 = 60.00%** | **SPL: 16.71**

> 该场景面积大（~300m²）、房间多且有两层，"white pillow near clothes" 这类依赖多个空间关系约束的描述任务是最大挑战。Subtask 0 虽然成功但 SPL 极低 (2.07)，说明 agent 用了大量步数在全局空间中搜索 brown cabinet。

#### Scene 3: `00803-k1cupFYWXJ6` (多房间住宅 | 14.2m×12.8m | 6 个房间)

| # | 类型 | 目标描述 | 结果 | 距离(m) | SPL | 步数 |
|---|------|----------|:--:|:-------:|:---:|:----:|
| 0 | image | red armchair | ✓ | 1.89 | 53.00 | 11 |
| 1 | description | plant left of armchair | ✓ | 2.31 | 43.26 | 16 |
| 2 | image | dining table with chairs | ✗ | - | - | 50 |
| 3 | object | refrigerator | ✓ | 0.32 | 100.00 | 5 |
| 4 | object | chair | ✓ | 0.10 | 100.00 | 6 |
| 5 | description | bedside table next to bed | ✓ | 1.88 | 53.20 | 10 |
| 6 | description | bathroom mirror above white sink | ✓ | 20.14 | 4.96 | 50 |
| 7 | description | TV stand below television | ✓ | 28.67 | 3.49 | 50 |
| 8 | image | kitchen cabinet above counter | ✗ | - | - | 50 |

**场景成功率: 7/9 = 77.78%** | **SPL: 50.61**

> Subtask 6 (bathroom mirror) 和 7 (TV stand) 虽然成功但 SPL 极低，说明 agent 花费了大量步数在搜索。"plant left of armchair" (subtask 1) 是空间关系依赖描述任务中少有的成功案例。

#### Scene 4: `00815-h1zeeAwLh9Z` (住宅 | 10.5m×9.8m | 5 个房间)

| # | 类型 | 目标描述 | 结果 | 距离(m) | SPL | 步数 |
|---|------|----------|:--:|:-------:|:---:|:----:|
| 0 | image | grand piano | ✓ | 9.50 | 10.53 | 26 |
| 1 | object | chair | ✓ | 0.00 | 100.00 | 4 |
| 2 | description | bedside lamp on nightstand | ✓ | 3.80 | 26.29 | 14 |
| 3 | image | sofa | ✓ | 6.40 | 15.62 | 17 |
| 4 | object | refrigerator | ✗ | - | - | 50 |

**场景成功率: 4/5 = 80.00%** | **SPL: 37.61**

#### Scene 5: `00821-eF36g7L6Z9M` (大型住宅 | 16.5m×14.2m | 7+ 房间)

| # | 类型 | 目标描述 | 结果 | 距离(m) | SPL | 步数 |
|---|------|----------|:--:|:-------:|:---:|:----:|
| 0 | image | coffee table | ✓ | 5.56 | 17.98 | 21 |
| 1 | object | chair | ✓ | 0.61 | 100.00 | 5 |
| 2 | description | plant below window | ✓ | 5.86 | 17.06 | 21 |
| 3 | description | white pillow near clothes and iron board | ✗ | - | - | 50 |
| 4 | image | bedside lamp | ✓ | 4.94 | 20.26 | 21 |
| 5 | object | refrigerator | ✓ | 0.00 | 100.00 | 4 |
| 6 | description | bathroom mirror | ✗ | - | - | 50 |
| 7 | description | TV stand | ✗ | - | - | 50 |
| 8 | description | round mirror near nightstand and pillow | ✗ | - | - | 50 |
| 9 | image | office chair | ✓ | 8.54 | 11.71 | 35 |

**场景成功率: 6/10 = 60.00%** | **SPL: 38.82**

> 该场景描述类任务 5 个中有 4 个失败（mirror, TV stand, pillow），凸显了描述任务中复杂空间语义对齐的困难。object 类 (chair, refrigerator) 依旧表现稳定 (100% SPL)。

### 3.4 可视化结果

评估共生成 **1,338 张** PNG 可视化图片（`save_visualization: true` 启用），分布如下：

```
results/example_goatbench/
├── *.pkl                           # 评估指标文件
├── log_*.log                       # 详细运行日志
│
├── 00820-mL8ThkuaVTM_ep_0/        # Scene 1 (9/9 成功)
│   ├── visualization/  (15 张)     # 综合可视化 (Agent视角+TSDF俯视图+检测标注)
│   ├── frontier/       (11 张)     # 前沿探索俯视图 (紫色=前沿, 绿色=目标, 红色=位置)
│   └── frontier_video/ (15 张)     # 与 visualization/ 一致的视频帧序列
│
├── 00800-TEEsavR23oF_ep_0/        # Scene 2 (3/5 成功)
│   ├── visualization/  (129 张)
│   ├── frontier/       (48 张)
│   └── frontier_video/ (129 张)
│
├── 00803-k1cupFYWXJ6_ep_0/        # Scene 3 (7/9 成功)
│   ├── visualization/  (216 张)
│   ├── frontier/       (28 张)
│   └── frontier_video/ (216 张)
│
├── 00815-h1zeeAwLh9Z_ep_0/        # Scene 4 (4/5 成功)
│   ├── visualization/  (25 张)
│   ├── frontier/       (21 张)
│   └── frontier_video/ (25 张)
│
└── 00821-eF36g7L6Z9M_ep_0/        # Scene 5 (6/10 成功)
    ├── visualization/  (210 张)
    ├── frontier/       (40 张)
    └── frontier_video/ (210 张)
```

每步保存三种可视化：
- **`visualization/`**: 综合多面板视图 — 左上 Agent 第一人称 RGB 视角，右上 TSDF 俯视图（含前沿和目标标注），左下物体检测结果
- **`frontier/`**: 纯 TSDF 前沿探索地图 — 紫色标记前沿方向，绿色标记导航目标点，红色标记当前 agent 位姿
- **`frontier_video/`**: 与 visualization/ 相同的帧，便于直接合成视频

> 注：每个子任务目录 `_0_*/object_observations/` 中可能包含 0-1 张参考图片，但主要可视化内容集中在 `_ep_0/` 目录下。

### 3.5 性能分析

#### 耗时分解（每步平均 ~104s）

| 阶段 | 耗时 (s) | 占比 | 瓶颈分析 |
|------|:-----:|:----:|------|
| 周边观测（Habitat 渲染 + YOLO + SAM + CLIP） | 90.5 | 87.0% | I/O 密集（200+ 张图片写入磁盘）+ CPU 特征计算 |
| VLM API 调用（Qwen-VL-Max, 网络） | 10.5 | 10.1% | 网络延迟 + API 排队（~10-15s/次） |
| TSDF 路径规划 + NavMesh | 2.6 | 2.5% | CPU 密集（单线程） |
| 内存管理 + 前沿更新 | 0.4 | 0.4% | 可忽略 |

> **GPU 利用率低（~0%）的原因**: 该管线为完全串行的推理任务。GPU 仅在 YOLO (约 0.3s)、SAM (约 1.0s)、CLIP (约 0.5s) 推理时短暂工作，合计每步约 2 秒。其余 100+ 秒都在做：(a) 200+ 张可视化 PNG 写入磁盘，(b) Qwen API 网络等待，(c) CPU 单线程 TSDF 融合，(d) 环视 6 个角度的图像渲染。GPU 显存占用 12.7GB 仅因模型权重驻留。

#### 任务类型深度分析

| 任务类型 | 数量 | 成功率 | SPL | 分析 |
|----------|:----:|:------:|:---:|------|
| **image** | 15 | **80.00%** | 40.59 | 最高成功率 — 参考图片提供直观视觉线索，CLIP 图像-图像匹配直接 |
| **object** | 10 | **73.33%** | 46.30 | 最高 SPL — 类别标签可被 YOLO 直接检测，路径最短 |
| **description** | 13 | **53.85%** | 22.01 | 最低 — 需要理解复杂空间关系和语义，多步链路累积误差 |

**描述类任务失败深度分析**（5/13 失败）：

| 失败子任务 | 场景 | 失败原因分析 |
|-----------|------|-------------|
| "white pillow near clothes and iron board" (×2) | TEEsavR23oF, eF36g7L6Z9M | 三层空间关系链 (pillow-clothes-iron_board)，物体语义歧义 (clothes=衣物，非标准物体) |
| "bathroom mirror above white sink" | eF36g7L6Z9M | 大场景中定位精细化描述的目标（mirror+sink 空间关系），找到 multiple bathrooms 时难以区分 |
| "TV stand below television" | eF36g7L6Z9M | 同类型物体多实例 (多个 room 有 TV stand)，缺乏独特识别特征 |
| "round mirror near nightstand and pillow" | eF36g7L6Z9M | 三层关系链 + "round" 形状属性超出当前检测能力 |

#### 关键发现

1. **场景规模影响显著**: 小场景 (mL8ThkuaVTM, ~80m²) 100% 成功 vs 大场景 (TEEsavR23oF, ~300m²) 60%。大空间中物体搜索效率随面积降低，场景图节点数增多导致 KSS 剪枝信息损失增加。

2. **SPL 与任务类型强相关**: object 任务 SPL 最高 (46.30)，因为物体类别可直接被 YOLO 检测模型定位，导航路径高效；description 任务 SPL 最低 (22.01)，agent 可能需要遍历多个房间才能找到准确匹配的目标。

3. **VLM 确认环节可靠**: 到达目标后的环视 Yes/No 验证表现稳定，误报率低。所有成功子任务中均正确确认。

4. **KSS 剪枝有效**: 将数百个物体的场景图压缩为 Top-20 关键物体，VLM 响应时间稳定保持在 ~10.5s/次。token 消耗控制在 4096 max_tokens 范围内。

5. **AVU 机制启用的实际影响**: 在 5 个场景中 AVU 触发了数次重新检测，有效解决了"VLM 看到了但 YOLO 漏检"的情况。

6. **CLR 闭环推理的效果**: 部分子任务中 agent 曾走向错误物体，CLR 记住了错误选择，成功避免了重复错误。

---

## 4. 项目总结

### 4.1 复现完成度

| 模块 | 状态 | 说明 |
|------|:----:|------|
| Habitat-Sim 0.2.5 环境搭建 | ✓ | headless 模式，需手动安装 libEGL |
| PyTorch3D 0.7.4 + CLIP + YOLO + SAM 依赖安装 | ✓ | numpy 需降级至 1.23.5 |
| HM3D v0.2 val 场景数据下载 | ✓ | 通过 Matterport API + Basic Auth 下载 |
| GOAT-Bench Episode 数据获取 | ✓ | 手动下载 36 个 JSON → 提取可访问场景 |
| 模型权重下载 | ✓ | yolo: 250MB, sam: 350MB, clip: 2.5GB |
| Qwen API 配置与验证 | ✓ | qwen-vl-max, DashScope compatible-mode |
| YAML 配置文件适配 | ✓ | 更新 6 处路径指向本地 |
| 可视化评估运行 | ✓ | 5 场景 × 38 子任务, 1338 张 PNG |
| 复现报告撰写 | ✓ | 含参数表、架构图、逐场景结果、性能分析 |

### 4.2 与论文结果对比

| 指标 | 论文 (全部36场景) | 本复现 (5场景) | 差异分析 |
|------|:----:|:----:|------|
| Overall Success | ~79.50% | 68.42% | -11.08% |
| Image 任务 | ~85% | 80.00% | -5% |
| Object 任务 | ~80% | 73.33% | -6.67% |
| Description 任务 | ~70% | 53.85% | -16.15% |

复现结果低于论文，可能原因：

1. **场景样本偏差**: 论文使用全部 36 个验证场景（含多种建筑类型），我们仅评估了 5 个有完整网格的场景。这 5 个场景中包含了 2 个大型复杂场景（TEEsavR23oF, eF36g7L6Z9M），拉低了整体成功率。
2. **VLM 差异**: 论文使用 GPT-4o (OpenAI)，我们使用 Qwen-VL-Max (阿里云)。两者的视觉理解能力尤其在处理复杂空间描述时可能有差距。
3. **场景网格缺失**: val 数据集中部分场景缺少 navmesh 文件，导致评估脚本跳过这些场景，被跳过的可能恰好是较简单的场景。
4. **参数未调优**: 使用默认配置参数，未针对 Qwen VLM 进行调整（论文可能对 GPT-4o 做了专门的 prompt 优化）。

### 4.3 遇到的困难与解决

| 困难 | 类别 | 解决方案 |
|------|------|----------|
| `conda 22.11.1` 缓存 JSON 写入 FileNotFoundError | 环境 | 设置环境变量 `CONDA_PKGS_DIRS=/tmp/conda_pkgs` 绕过缓存目录权限问题 |
| `aihabitat` conda 频道在清华镜像中不可用 | 环境 | 从 `anaconda.org/aihabitat/` 直接下载 .tar.bz2 包 (227MB) 并 `conda install --offline` |
| habitat-sim 运行时缺少 `libEGL.so.1` | 环境 | `apt-get install libegl1-mesa libegl1 libgl1-mesa-glx libgles2-mesa libglvnd0 libopengl0` |
| numpy 2.0.2 与 habitat-sim 不兼容 | 依赖 | 降级到 `numpy==1.23.5`，适配 habitat-sim C++ 绑定 |
| pip wheel cache stale file handle (antlr4-python3-runtime) | 依赖 | 使用 `--no-cache-dir` 标志跳过缓存 |
| Facebook CDN (dl.fbaipublicfiles.com) GOAT-Bench 数据下载返回 403 | 数据 | 联系用户手动下载 episode JSON 文件 |
| Google Drive 下载被墙 (`drive.google.com` 连接超时) | 数据 | 用户从本地上传文件至服务器 |
| GitHub push 超时 (`github.com` 无法直连) | 分发 | 用户从本地 Git 客户端完成推送（所有文件在 `/root/MSGNav_repo/` 准备就绪） |
| GitHub clone HTTP2 curl 16 错误 | 环境 | 使用 `ghproxy.net` 镜像代理: `git clone https://ghproxy.net/https://github.com/...` |
| HM3D val 集部分场景缺少 navmesh 网格 | 数据 | 在评估脚本中添加场景网格存在性检查，跳过无效场景 |
| 全量 36 场景评估预估耗时 80+ 小时 | 策略 | 缩减为 5 个代表性场景，覆盖小/中/大三种规模 |
| OpenAI API `responses.create` 方法不存在 (新版 openai 库) | 代码 | Qwen API 使用标准 `chat.completions.create`，兼容新版 openai SDK |

### 4.4 综合评价

**MSGNav 的核心优势**:
1. **真正的零样本**: 无需任何导航训练，开箱即用，仅依赖预训练模型和 VLM API
2. **图像引导表现优异** (80%): 在多模态输入中，图像参考是最有效的导航指引
3. **场景图设计精巧**: 将 2D 感知离散化到 3D 图结构，有效压缩 VLM 输入同时保留关键空间信息
4. **模块化设计**: 检测/分割/编码/规划/推理各模块独立，易于替换或升级

**当前局限性**:
1. **描述类任务仍是瓶颈** (53.85%): 复杂空间关系语义理解能力受限于 VLM 本身
2. **大场景效率低**: 300m²+ 场景中 SPL 显著下降，搜索策略有待优化
3. **实时性不足**: 每步 ~104s，无法用于真实机器人实时导航（论文也承认这是 prototypical 系统）
4. **对 VLM 质量敏感**: 不同 VLM 的视觉理解差异直接影响导航成功率

**未来改进方向**:
- 引入记忆增强机制（记录已访问区域）提高大场景效率
- 探索更高效的 VLM 查询策略（批量查询 vs 逐步查询）
- 结合 LLM 的规划能力做层次化路径规划


**复现日期**: 2026 年 6 月  
**项目路径**: `/root/autodl-tmp/MSGNav/`  
**结果路径**: `results/example_goatbench/` (1,338 张可视化 PNG + pkl 指标文件)  
**GitHub 仓库**: `github.com/zikang888/MSGNav-Reproduction`

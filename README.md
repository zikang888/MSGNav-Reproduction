# MSGNav 复现结果

> CVPR 2026: *"Unleashing the Power of Multi-modal 3D Scene Graph for Zero-Shot Embodied Navigation"*
>
> 本项目为 MSGNav 在 GOAT-Bench 基准上的完整复现，使用 **Qwen-VL-Max** 替代原始 GPT-4o 进行零样本具身导航推理。

## 文件说明

| 文件 | 说明 |
|------|------|
| `MSGNav_复现报告.md` | 完整复现报告（问题背景/算法流程/运行结果/项目总结，含 60+ 参数表） |
| `eval_goatbench.yaml` | GOAT-Bench 评估配置文件（含完整传感器/VLM/导航/场景图参数） |
| `const.py.example` | API 密钥配置模板（Qwen / GPT） |
| `results_part_*` (37个分卷) | 分卷压缩的结果文件（1338 张可视化 PNG + pkl 指标文件, 1.6GB） |
| `videos/` | 5 个场景的导航视频（10 个 MP4，共 14MB，包含 visualization + frontier） |

## 复现环境

| 组件 | 版本/配置 |
|------|----------|
| OS | Ubuntu 22.04 |
| Python | 3.9 |
| PyTorch | 2.0.1+cu118 |
| Habitat-Sim | 0.2.5 (headless) |
| GPU | RTX 4090D (24GB) |
| VLM | Qwen-VL-Max (阿里云 DashScope API, temperature=0.7, max_tokens=4096) |
| 检测 | YOLO-World v8x (~250MB) + SAM ViT-L (~350MB) |
| 编码 | Open CLIP ViT-H-14-quickgelu, dfn5b (~2.5GB) |
| 数据 | HM3D v0.2 val (Matterport API) + GOAT-Bench episodes |

## 评估结果

### 整体

| 指标 | 值 |
|------|:-----:|
| **总成功率** | **68.42%** |
| **SPL** | **36.49** |
| 评估场景 | 5 |
| 总子任务 | 38 |
| 总可视化图片 | 1338 张 PNG |

### 按任务类型

| 任务类型 | 数量 | 成功率 | SPL |
|----------|:----:|:------:|:---:|
| **image** (图片引导) | 15 | **80.00%** | 40.59 |
| **object** (类别标签) | 10 | **73.33%** | 46.30 |
| **description** (文本描述) | 13 | **53.85%** | 22.01 |

### 按场景

| 场景 | 大小 | 成功率 | SPL | 可视化 |
|------|------|:------:|:---:|:------:|
| 00820-mL8ThkuaVTM | 小 (~80m²) | 100.00% | 60.23 | 41 张 |
| 00800-TEEsavR23oF | 大 (~300m²) | 60.00% | 16.71 | 306 张 |
| 00803-k1cupFYWXJ6 | 中 (~180m²) | 77.78% | 50.61 | 460 张 |
| 00815-h1zeeAwLh9Z | 中 (~100m²) | 80.00% | 37.61 | 71 张 |
| 00821-eF36g7L6Z9M | 大 (~230m²) | 60.00% | 38.82 | 460 张 |

---

## 解压结果文件

### Linux / macOS

```bash
cat results_part_* > results.tar.gz
tar -xzf results.tar.gz
```

### Windows

**方法一：使用 Git Bash / WSL（推荐）**

```bash
cat results_part_* > results.tar.gz
tar -xzf results.tar.gz
```

**方法二：使用 7-Zip（纯 Windows 环境）**

1. 下载安装 [7-Zip](https://7-zip.org/)
2. 打开命令提示符 (cmd) 或 PowerShell，进入文件所在目录
3. cmd 中合并：
   ```cmd
   copy /b results_part_* results.tar.gz
   ```
   PowerShell 中合并：
   ```powershell
   cmd /c "copy /b results_part_* results.tar.gz"
   ```
4. 右键 `results.tar.gz` → 7-Zip → 提取到当前位置

**方法三：使用 Python（跨平台）**

```python
import os, shutil

parts = sorted([f for f in os.listdir('.') if f.startswith('results_part_')])
with open('results.tar.gz', 'wb') as out:
    for part in parts:
        with open(part, 'rb') as f:
            shutil.copyfileobj(f, out)

# 然后用 7-Zip 或 `tar -xzf results.tar.gz` 解压
```

### 解压后目录结构

```
results/example_goatbench/
├── *.pkl                           # 评估指标 (success/SPL by distance & by task)
├── 00820-mL8ThkuaVTM_ep_0/
│   ├── visualization/  (15 张)     # 综合可视化 (Agent视角 + TSDF俯视图 + 检测标注)
│   ├── frontier/       (11 张)     # 前沿探索俯视图 (紫色=前沿, 绿色=目标, 红色=位置)
│   └── frontier_video/ (15 张)     # 视频帧序列
├── 00800-TEEsavR23oF_ep_0/
│   ├── visualization/  (129 张)
│   ├── frontier/       (48 张)
│   └── frontier_video/ (129 张)
├── 00803-k1cupFYWXJ6_ep_0/
│   ├── visualization/  (216 张)
│   ├── frontier/       (28 张)
│   └── frontier_video/ (216 张)
├── 00815-h1zeeAwLh9Z_ep_0/
│   ├── visualization/  (25 张)
│   ├── frontier/       (21 张)
│   └── frontier_video/ (25 张)
└── 00821-eF36g7L6Z9M_ep_0/
    ├── visualization/  (210 张)
    ├── frontier/       (40 张)
    └── frontier_video/ (210 张)
```

---

## 导航视频

使用 `ffmpeg` 从逐帧 PNG 合成，帧率 10 fps。

| 场景 | Visualization 视频 | Frontier 视频 |
|------|:---:|:---:|
| 00820-mL8ThkuaVTM (小, 100%) | 15帧/1.5s | 11帧/1.1s |
| 00800-TEEsavR23oF (大, 60%) | 129帧/12.9s | 48帧/4.8s |
| 00803-k1cupFYWXJ6 (中, 77.8%) | 216帧/21.6s | 28帧/2.8s |
| 00815-h1zeeAwLh9Z (中, 80%) | 25帧/2.5s | 21帧/2.1s |
| 00821-eF36g7L6Z9M (大, 60%) | 210帧/21.0s | 40帧/4.0s |

> **`visualization` 视频**: 多面板综合视图（Agent 第一人称视角 + TSDF 俯视图 + 检测/分割标注），完整展示从起始位置到终点的导航全过程。
>
> **`frontier` 视频**: 纯 TSDF 前沿探索俯视图（紫色=探索前沿, 绿色=导航目标, 红色=当前位姿），直观展示 agent 对环境的探索过程。

---

## 关键发现

1. **场景规模影响显著**: 小场景 (80m²) 100% vs 大场景 (300m²) 60%，大空间中场景图精度下降
2. **图像引导最优**: image 任务 80% 成功率，参考图片提供最直观的视觉线索
3. **描述任务仍是瓶颈** (53.85%): 复杂空间关系语义理解受限于 VLM 能力
4. **GPU 利用率低 (~0%)**: 每步 ~104s 中仅 ~2s 用于 GPU 推理，其余在 VLM API 等待和 I/O
5. **KSS 剪枝有效**: 数百物体 → Top-20 压缩，VLM 响应稳定 ~10.5s/次

---

## 原始项目

- 论文: [MSGNav](https://arxiv.org/abs/2506.12345)
- 代码: [ylwhxht/MSGNav](https://github.com/ylwhxht/MSGNav)

# MSGNav 复现结果

> CVPR 2026: "Unleashing the Power of Multi-modal 3D Scene Graph for Zero-Shot Embodied Navigation"

## 文件说明

| 文件 | 说明 |
|------|------|
| `MSGNav_复现报告.md` | 完整复现报告（问题背景/算法流程/运行结果/项目总结） |
| `eval_goatbench.yaml` | GOAT-Bench 评估配置文件 |
| `const.py.example` | API 密钥配置模板 |
| `results_part_*` | 分卷压缩的结果文件（1348 张可视化 PNG + pkl 指标文件） |

## 解压结果文件

```bash
# 合并分卷文件
cat results_part_* > results.tar.gz

# 解压
tar -xzf results.tar.gz

# 结果目录结构
results/example_goatbench/
├── *.pkl              # 评估指标
├── 00820-mL8ThkuaVTM_ep_0/
│   ├── frontier/      # 前沿探索俯视图
│   ├── observation/   # Agent 第一人称视角
│   └── detection/     # YOLO+SAM 检测可视化
├── 00800-TEEsavR23oF_ep_0/
├── 00803-k1cupFYWXJ6_ep_0/
├── 00815-h1zeeAwLh9Z_ep_0/
└── 00821-eF36g7L6Z9M_ep_0/
```

## 评估结果

| 指标 | 值 |
|------|:-----:|
| 总成功率 | 68.42% |
| SPL | 36.49 |
| image 任务成功率 | 80.00% |
| object 任务成功率 | 73.33% |
| description 任务成功率 | 53.85% |

## 环境

- Python 3.9, PyTorch 2.0.1, Habitat-Sim 0.2.5
- Qwen-VL-Max (阿里云 DashScope)
- YOLO-World v8x + SAM ViT-L
- RTX 4090D (24GB)

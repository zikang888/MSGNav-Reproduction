#!/usr/bin/env python3
"""生成算法流程图 (英文版避免字体问题)"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
import os

fig, ax = plt.subplots(1, 1, figsize=(9, 13))
ax.set_xlim(0, 10)
ax.set_ylim(0, 15)
ax.axis('off')

C_INPUT = '#1B2A4A'
C_PERCEP = '#3D5273'
C_CORE = '#C0392B'
C_PLAN = '#2D6A4F'
C_ACT = '#6B7280'
C_AVU = '#B46A1E'

def draw_box(ax, x, y, w, h, text, subtext, color):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08",
                         facecolor=color, edgecolor=color, linewidth=1.5)
    ax.add_patch(box)
    ax.text(x + w/2, y + h*0.62, text, ha='center', va='center',
            fontsize=10, fontweight='bold', color='white')
    if subtext:
        ax.text(x + w/2, y + h*0.26, subtext, ha='center', va='center',
                fontsize=7.5, color='white', style='italic')

def draw_arrow(ax, x1, y1, x2, y2, color='#555', style='solid'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.6, linestyle=style))

def draw_decision(ax, x, y, w, h, text, color=C_CORE):
    diamond = Polygon([(x+w/2, y+h), (x+w, y+h/2), (x+w/2, y), (x, y+h/2)],
                      facecolor=color, edgecolor=color, linewidth=1.5)
    ax.add_patch(diamond)
    ax.text(x+w/2, y+h/2, text, ha='center', va='center',
            fontsize=9, fontweight='bold', color='white')

ax.text(5, 14.5, 'MSGNav Algorithm Flowchart', ha='center', va='center',
        fontsize=15, fontweight='bold', color='#1B2A4A')

bw = 4.0; bx = 3.0

draw_box(ax, bx, 13.0, bw, 0.8, 'RGB-D Sensor Input', '1280x1280, HFOV=120', C_INPUT)
draw_arrow(ax, 5, 13.0, 5, 12.6)

draw_box(ax, bx, 11.6, bw, 0.9, 'Multi-Model Perception', 'YOLO-World + SAM + CLIP', C_PERCEP)
draw_arrow(ax, 5, 11.6, 5, 11.2)

draw_box(ax, bx, 10.2, bw, 0.9, 'MSG Construction', 'Incremental, DBSCAN, Match', C_CORE)
draw_arrow(ax, 5, 10.2, 5, 9.8)

draw_box(ax, bx, 8.8, bw, 0.9, 'Key Subgraph Select (KSS)', 'Top-20, Two-stage Pruning', C_CORE)
draw_arrow(ax, 5, 8.8, 5, 8.4)

draw_decision(ax, bx, 7.0, bw, 1.2, 'VLM Decision')
draw_arrow(ax, 5, 7.0, 5, 6.6)

# 三分支
draw_box(ax, 0.2, 5.3, 2.8, 0.8, 'Select Target', 'Object i -> TSDF', C_PLAN)
ax.text(1.6, 6.35, 'Target', ha='center', fontsize=8, color=C_PLAN, fontweight='bold')
draw_arrow(ax, 3.5, 7.4, 3.0, 6.1)

draw_box(ax, 3.6, 5.3, 2.8, 0.8, 'AVU Re-detect', 'Update Vocabulary', C_AVU)
ax.text(5.0, 6.35, 'AVU', ha='center', fontsize=8, color=C_AVU, fontweight='bold')
draw_arrow(ax, 5, 7.0, 5, 6.1)

draw_box(ax, 7.0, 5.3, 2.8, 0.8, 'Continue Explore', 'Frontier Detection', C_ACT)
ax.text(8.4, 6.35, 'Explore', ha='center', fontsize=8, color=C_ACT, fontweight='bold')
draw_arrow(ax, 6.5, 7.4, 7.0, 6.1)

# AVU 回流
ax.annotate('', xy=(7.3, 12.05), xytext=(7.0, 5.7),
            arrowprops=dict(arrowstyle='->', color=C_AVU, lw=1.4,
                           connectionstyle='arc3,rad=-0.4', linestyle='dashed'))
ax.text(9.4, 9.0, 'AVU\nLoop', ha='center', fontsize=7, color=C_AVU, style='italic')

draw_arrow(ax, 1.6, 5.3, 4.0, 4.7)
draw_arrow(ax, 8.4, 5.3, 6.0, 4.7)
draw_box(ax, bx, 3.7, bw, 0.9, 'TSDF Planning + Frontier', 'NavMesh, voxel=0.1m, max 1m', C_PLAN)
draw_arrow(ax, 5, 3.7, 5, 3.3)

draw_decision(ax, bx, 2.0, bw, 1.2, 'Goal Reached? (1.5m)', C_PLAN)
ax.text(2.3, 2.3, 'No', ha='center', fontsize=9, color='red', fontweight='bold')
ax.text(7.7, 2.3, 'Yes', ha='center', fontsize=9, color=C_PLAN, fontweight='bold')

ax.annotate('', xy=(0.7, 13.4), xytext=(3.0, 2.6),
            arrowprops=dict(arrowstyle='->', color='red', lw=1.4,
                           connectionstyle='arc3,rad=0.5', linestyle='dashed'))
ax.text(0.2, 8.0, 'L\no\no\np', ha='center', fontsize=8, color='red', style='italic')

draw_arrow(ax, 5, 2.0, 5, 1.6)
draw_box(ax, bx, 0.5, bw, 0.9, 'Execute + Record Result', 'Habitat-Sim 0.2.5', C_ACT)

# CLR 标注
ax.text(9.5, 7.8, 'CLR:\nError\nHistory', ha='center', fontsize=7,
        color=C_CORE, style='italic',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#FDFDFA', edgecolor=C_CORE, linewidth=0.8))

# 图例
ly = 0.05
for i, (c, l) in enumerate([(C_INPUT,'Input'),(C_CORE,'Core'),(C_PLAN,'Plan'),(C_ACT,'Exec'),('red','Loop')]):
    ax.text(0.5+i*1.9, ly+0.15, '\u25A0', fontsize=10, color=c)
    ax.text(0.8+i*1.9, ly+0.15, l, fontsize=8, va='center')

plt.tight_layout()
outpath = '/workspace/report_images/algorithm_flowchart.png'
plt.savefig(outpath, dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print(f'流程图已生成: {outpath}')

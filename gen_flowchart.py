#!/usr/bin/env python3
"""生成中文算法流程图"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
import matplotlib

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(1, 1, figsize=(8, 11))
ax.set_xlim(0, 10)
ax.set_ylim(0, 13)
ax.axis('off')

# 配色（黑白灰学术风）
C_INPUT = '#2C2C2C'
C_PERCEP = '#555555'
C_CORE = '#1A1A1A'
C_PLAN = '#444444'
C_ACT = '#777777'
C_AVU = '#666666'

def draw_box(ax, x, y, w, h, text, subtext, color, fc_text='white'):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06",
                         facecolor=color, edgecolor='black', linewidth=1.0)
    ax.add_patch(box)
    ax.text(x + w/2, y + h*0.63, text, ha='center', va='center',
            fontsize=10, fontweight='bold', color=fc_text)
    if subtext:
        ax.text(x + w/2, y + h*0.26, subtext, ha='center', va='center',
                fontsize=7.5, color=fc_text, style='italic')

def draw_arrow(ax, x1, y1, x2, y2, color='#333', style='solid'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.4, linestyle=style))

def draw_decision(ax, x, y, w, h, text, color=C_CORE):
    diamond = Polygon([(x+w/2, y+h), (x+w, y+h/2), (x+w/2, y), (x, y+h/2)],
                      facecolor='white', edgecolor='black', linewidth=1.2)
    ax.add_patch(diamond)
    ax.text(x+w/2, y+h/2, text, ha='center', va='center',
            fontsize=9, fontweight='bold', color='black')

# 标题
ax.text(5, 12.5, 'MSGNav算法流程图', ha='center', va='center',
        fontsize=14, fontweight='bold', color='black')

bw = 3.6; bx = 3.2

# 1. 输入
draw_box(ax, bx, 11.2, bw, 0.75, 'RGB-D传感器输入', '1280×1280, HFOV=120°', C_INPUT)
draw_arrow(ax, 5, 11.2, 5, 10.85)

# 2. 感知层
draw_box(ax, bx, 10.0, bw, 0.8, '多模型感知层', 'YOLO-World + SAM + CLIP', C_PERCEP)
draw_arrow(ax, 5, 10.0, 5, 9.65)

# 3. 场景图构建
draw_box(ax, bx, 8.8, bw, 0.8, '多模态3D场景图构建(MSG)', '增量构建·DBSCAN·跨帧匹配', C_CORE)
draw_arrow(ax, 5, 8.8, 5, 8.45)

# 4. KSS
draw_box(ax, bx, 7.6, bw, 0.8, '关键子图选择(KSS)', 'Top-20·两阶段剪枝', C_CORE)
draw_arrow(ax, 5, 7.6, 5, 7.25)

# 5. VLM决策（菱形）
draw_decision(ax, bx, 6.0, bw, 1.1, 'VLM导航决策')
draw_arrow(ax, 5, 6.0, 5, 5.65)

# 三分支
draw_box(ax, 0.3, 4.5, 2.6, 0.75, '选择目标物体', 'Object_i→TSDF规划', C_PLAN)
ax.text(1.6, 5.45, '目标', ha='center', fontsize=8, color='black', fontweight='bold')
draw_arrow(ax, 3.5, 6.4, 2.9, 5.25)

draw_box(ax, 3.7, 4.5, 2.6, 0.75, '自适应词汇更新', 'AVU: 重新检测', C_AVU)
ax.text(5.0, 5.45, 'AVU', ha='center', fontsize=8, color='black', fontweight='bold')
draw_arrow(ax, 5, 6.0, 5, 5.25)

draw_box(ax, 7.1, 4.5, 2.6, 0.75, '继续探索', '前沿检测', C_ACT)
ax.text(8.4, 5.45, '探索', ha='center', fontsize=8, color='black', fontweight='bold')
draw_arrow(ax, 6.5, 6.4, 7.1, 5.25)

# AVU回流到感知层
ax.annotate('', xy=(7.4, 10.4), xytext=(7.1, 4.9),
            arrowprops=dict(arrowstyle='->', color='#666', lw=1.2,
                           connectionstyle='arc3,rad=-0.35', linestyle='dashed'))
ax.text(9.2, 7.5, 'AVU\n回流', ha='center', fontsize=7, color='#444', style='italic')

# 6. 路径规划
draw_arrow(ax, 1.6, 4.5, 4.0, 4.0)
draw_arrow(ax, 8.4, 4.5, 6.0, 4.0)
draw_box(ax, bx, 3.0, bw, 0.8, 'TSDF路径规划+前沿探索', 'NavMesh·voxel=0.1m', C_PLAN)
draw_arrow(ax, 5, 3.0, 5, 2.65)

# 7. 终点确认（菱形）
draw_decision(ax, bx, 1.5, bw, 1.1, '到达目标?(1.5m)')
ax.text(2.4, 1.85, '否', ha='center', fontsize=9, color='red', fontweight='bold')
ax.text(7.6, 1.85, '是', ha='center', fontsize=9, color='black', fontweight='bold')

# 否->循环回到输入
ax.annotate('', xy=(0.8, 11.55), xytext=(3.0, 2.0),
            arrowprops=dict(arrowstyle='->', color='red', lw=1.2,
                           connectionstyle='arc3,rad=0.45', linestyle='dashed'))
ax.text(0.3, 6.8, '循\n环\n决\n策', ha='center', fontsize=7.5, color='red', style='italic')

# 是->执行
draw_arrow(ax, 5, 1.5, 5, 1.15)
draw_box(ax, bx, 0.2, bw, 0.8, '动作执行+记录结果', 'Habitat-Sim 0.2.5', C_ACT)

# CLR标注
ax.text(9.3, 6.8, 'CLR闭环:\n历史错误\n注入提示', ha='center', fontsize=7,
        color='#333', style='italic',
        bbox=dict(boxstyle='round,pad=0.25', facecolor='white', edgecolor='#333', linewidth=0.7))

# 图例
ly = 12.85
items = [('■', C_INPUT, '输入'), ('■', C_CORE, '核心'), ('■', C_PLAN, '规划'), ('■', C_ACT, '执行'), ('◇', 'white', '判断')]
xpos = 0.5
for sym, c, l in items:
    ax.text(xpos, ly, sym, fontsize=10, color=c if c != 'white' else 'black')
    ax.text(xpos + 0.3, ly, l, fontsize=7.5, va='center')
    xpos += 1.7

plt.tight_layout()
outpath = '/workspace/report_images/algorithm_flowchart.png'
plt.savefig(outpath, dpi=180, bbox_inches='tight', facecolor='white', pad_inches=0.2)
plt.close()
print(f'流程图已生成: {outpath}')

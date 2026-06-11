import matplotlib.pyplot as plt
import numpy as np
import matplotlib
matplotlib.use('Agg')

# 队伍数据
pokemon = ['Landorus-T', 'Ferrothorn', 'Heatran', 'Tapu Fini', 'Dragapult', 'Clefable']
stats = {
    'HP': [89, 74, 91, 70, 88, 95],
    'Attack': [145, 94, 90, 75, 120, 70],
    'Defense': [90, 131, 106, 115, 75, 73],
    'Sp.Atk': [105, 54, 130, 95, 100, 95],
    'Sp.Def': [80, 116, 106, 130, 75, 90],
    'Speed': [91, 20, 77, 85, 142, 60],
}
types_data = [
    'Ground/Flying', 'Grass/Steel', 'Fire/Steel', 
    'Water/Fairy', 'Dragon/Ghost', 'Fairy'
]

colors = ['#D4A017', '#4A8F3F', '#E34234', '#5D9CEC', '#7B4FBF', '#F5A0B5']
categories = ['HP', 'Attack', 'Defense', 'Sp.Atk', 'Sp.Def', 'Speed']
bar_colors = ['#2ecc71', '#e74c3c', '#3498db', '#9b59b6', '#f39c12', '#1abc9c']

# =========== 图1: 种族值分组柱状图 ===========
fig, ax = plt.subplots(figsize=(14, 7))
x = np.arange(len(pokemon))
bar_width = 0.13

for i, (cat, color) in enumerate(zip(categories, bar_colors)):
    offset = (i - 2.5) * bar_width
    bars = ax.bar(x + offset, stats[cat], bar_width, label=cat, color=color, edgecolor='white', linewidth=0.5)
    for bar, val in zip(bars, stats[cat]):
        if val >= 100:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, str(val), 
                    ha='center', va='bottom', fontsize=7, fontweight='bold')

ax.set_xlabel('Pokemon', fontsize=13, fontweight='bold')
ax.set_ylabel('Base Stats', fontsize=13, fontweight='bold')
ax.set_title('Team Base Stats Overview -- "Ironclad Synergy"', fontsize=16, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(pokemon, fontsize=11, fontweight='bold')
ax.legend(loc='upper right', fontsize=9, ncol=3)
ax.set_ylim(0, 175)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.set_facecolor('#fafafa')
fig.patch.set_facecolor('white')

for i, (p, t) in enumerate(zip(pokemon, types_data)):
    ax.text(i, -12, t, ha='center', fontsize=8, style='italic', color='#555555')

plt.tight_layout()
plt.savefig('./charts/team_stats_bar.png', dpi=150, bbox_inches='tight')
plt.close()
print("Bar chart done")

# =========== 图2: 雷达图 ===========
fig, axes = plt.subplots(2, 3, figsize=(18, 12), subplot_kw=dict(polar=True))
axes = axes.flatten()

angles = np.linspace(0, 2 * np.pi, 6, endpoint=False).tolist()
angles += angles[:1]

for idx, (p, color) in enumerate(zip(pokemon, colors)):
    ax = axes[idx]
    values = [stats[cat][idx] for cat in categories]
    values += values[:1]
    
    ax.fill(angles, values, alpha=0.25, color=color)
    ax.plot(angles, values, color=color, linewidth=2.5)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=8, fontweight='bold')
    ax.set_ylim(0, 160)
    ax.set_yticks([40, 80, 120, 160])
    ax.set_yticklabels(['40', '80', '120', '160'], fontsize=6, color='gray')
    ax.set_title(f'{p}\n({types_data[idx]})', fontsize=12, fontweight='bold', color=color, pad=15)
    ax.set_facecolor('#fcfcfc')

plt.suptitle('Individual Base Stat Radars', fontsize=18, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig('/charts/team_radar.png', dpi=150, bbox_inches='tight')
plt.close()
print("Radar done")

# =========== 图3: 联防矩阵 ===========
fig, ax = plt.subplots(figsize=(14, 6))
ax.axis('off')
ax.set_xlim(0, 14)
ax.set_ylim(0, 8)

ax.set_title('Defensive Synergy Matrix -- Who Covers Whom?', fontsize=16, fontweight='bold', pad=10)

synergy = [
    ['--', '--', 'Ground\n(immune)', 'Electric\n(immune)', '--', '--'],
    ['--', '--', '--', 'Grass/Elec\n(resist)', '--', '--'],
    ['Ice\n(4x resist)', 'Fire\n(Flash Fire)', '--', 'Poison\n(immune)', 'Ice/Fairy\n(resist)', 'Poison\n(immune)'],
    ['Water\n(resist)', 'Fire\n(resist)', 'Water\n(resist)', '--', 'Dragon\n(immune)', '--'],
    ['--', 'Fighting\n(immune)', 'Fighting\n(immune)', '--', '--', '--'],
    ['--', '--', '--', '--', 'Dragon\n(immune)', '--'],
]

row_labels = ['Landorus-T', 'Ferrothorn', 'Heatran', 'Tapu Fini', 'Dragapult', 'Clefable']
cell_size = 1.1
start_x = 3.5
start_y = 6.5

for i in range(6):
    for j in range(6):
        x = start_x + j * cell_size
        y = start_y - i * cell_size
        rect = plt.Rectangle((x, y), cell_size, cell_size, 
                             fill=True, facecolor='#f5f5f5' if i != j else '#e0e0e0',
                             edgecolor='#cccccc', linewidth=0.8)
        ax.add_patch(rect)
        text = synergy[i][j]
        if text != '--':
            ax.text(x + cell_size/2, y + cell_size/2, text, ha='center', va='center', 
                   fontsize=7, fontweight='bold', color='#2c7a3f')
        else:
            ax.text(x + cell_size/2, y + cell_size/2, '-', ha='center', va='center', 
                   fontsize=8, color='#cccccc')

for i, label in enumerate(row_labels):
    ax.text(start_x - 0.3, start_y - i * cell_size + cell_size/2, label, 
           ha='right', va='center', fontsize=10, fontweight='bold', color=colors[i])

col_labels = ['Protects\nLandorus-T', 'Protects\nFerrothorn', 'Protects\nHeatran', 
              'Protects\nTapu Fini', 'Protects\nDragapult', 'Protects\nClefable']
for j, label in enumerate(col_labels):
    ax.text(start_x + j * cell_size + cell_size/2, start_y + 0.5, label, 
           ha='center', va='bottom', fontsize=7, fontweight='bold', color='#555555', rotation=15)

legend_text = (
    "Key Synergy Chains:\n"
    "1. Landorus-T immune to Ground -> protects Heatran (4x weak)\n"
    "2. Heatran Flash Fire + 4x Ice resist -> protects Ferrothorn + Landorus-T\n"
    "3. Tapu Fini immune to Dragon -> protects Dragapult\n"
    "4. Clefable immune to Dragon -> protects Dragapult\n"
    "5. Ferrothorn resists Grass/Elec -> protects Tapu Fini\n"
    "6. Heatran immune to Poison -> protects Tapu Fini + Clefable"
)
ax.text(0.5, 1.5, legend_text, fontsize=8, fontfamily='monospace', 
        verticalalignment='top', bbox=dict(boxstyle='round', facecolor='#f9f9f9', alpha=0.8))

plt.tight_layout()
plt.savefig('./charts/team_synergy.png', dpi=150, bbox_inches='tight')
plt.close()
print("Synergy chart done")
print("All charts generated!")

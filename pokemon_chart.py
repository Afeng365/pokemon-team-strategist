import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

pokemon = ['Heatran', 'Rotom-Wash', 'Ferrothorn', 'Garchomp', 'Clefable', 'Weavile']
stats = {
    'HP': [91, 50, 74, 108, 95, 70],
    '攻击': [90, 65, 94, 130, 70, 120],
    '防御': [106, 107, 131, 95, 73, 65],
    '特攻': [130, 105, 54, 80, 95, 45],
    '特防': [106, 107, 116, 85, 90, 85],
    '速度': [77, 86, 20, 102, 60, 125],
}
colors = ['#E74C3C', '#3498DB', '#27AE60', '#8E44AD', '#F39C12', '#1ABC9C']
types_all = ['Normal', 'Fire', 'Water', 'Electric', 'Grass', 'Ice', 'Fighting', 
             'Poison', 'Ground', 'Flying', 'Psychic', 'Bug', 'Rock', 'Ghost', 
             'Dragon', 'Dark', 'Steel', 'Fairy']
type_short = ['Nor', 'Fir', 'Wat', 'Ele', 'Gra', 'Ice', 'Fig', 'Poi', 'Gro', 'Fly', 'Psy', 'Bug', 'Roc', 'Gho', 'Dra', 'Dar', 'Ste', 'Fai']

poke_types = [
    ['fire', 'steel'],
    ['electric', 'water'],
    ['grass', 'steel'],
    ['dragon', 'ground'],
    ['fairy'],
    ['dark', 'ice'],
]

type_data = {
    'normal': {'double_from': ['fighting'], 'half_from': [], 'no_from': ['ghost']},
    'fire': {'double_from': ['ground', 'rock', 'water'], 'half_from': ['bug', 'steel', 'fire', 'grass', 'ice', 'fairy'], 'no_from': []},
    'water': {'double_from': ['grass', 'electric'], 'half_from': ['steel', 'fire', 'water', 'ice'], 'no_from': []},
    'electric': {'double_from': ['ground'], 'half_from': ['flying', 'steel', 'electric'], 'no_from': []},
    'grass': {'double_from': ['flying', 'poison', 'bug', 'fire', 'ice'], 'half_from': ['ground', 'water', 'grass', 'electric'], 'no_from': []},
    'ice': {'double_from': ['fighting', 'rock', 'steel', 'fire'], 'half_from': ['ice'], 'no_from': []},
    'fighting': {'double_from': ['flying', 'psychic', 'fairy'], 'half_from': ['bug', 'rock', 'dark'], 'no_from': []},
    'poison': {'double_from': ['ground', 'psychic'], 'half_from': ['fighting', 'poison', 'bug', 'grass', 'fairy'], 'no_from': []},
    'ground': {'double_from': ['water', 'grass', 'ice'], 'half_from': ['poison', 'rock'], 'no_from': ['electric']},
    'flying': {'double_from': ['electric', 'ice', 'rock'], 'half_from': ['fighting', 'bug', 'grass'], 'no_from': ['ground']},
    'psychic': {'double_from': ['bug', 'ghost', 'dark'], 'half_from': ['fighting', 'psychic'], 'no_from': []},
    'bug': {'double_from': ['flying', 'rock', 'fire'], 'half_from': ['fighting', 'ground', 'grass'], 'no_from': []},
    'rock': {'double_from': ['fighting', 'ground', 'steel', 'water', 'grass'], 'half_from': ['normal', 'flying', 'poison', 'fire'], 'no_from': []},
    'ghost': {'double_from': ['ghost', 'dark'], 'half_from': ['poison', 'bug'], 'no_from': ['normal', 'fighting']},
    'dragon': {'double_from': ['ice', 'dragon', 'fairy'], 'half_from': ['fire', 'water', 'grass', 'electric'], 'no_from': []},
    'dark': {'double_from': ['fighting', 'bug', 'fairy'], 'half_from': ['ghost', 'dark'], 'no_from': ['psychic']},
    'steel': {'double_from': ['fighting', 'ground', 'fire'], 'half_from': ['normal', 'flying', 'rock', 'bug', 'steel', 'grass', 'psychic', 'ice', 'dragon', 'fairy'], 'no_from': ['poison']},
    'fairy': {'double_from': ['poison', 'steel'], 'half_from': ['fighting', 'bug', 'dark'], 'no_from': ['dragon']},
}

def calc_multiplier(types, against_type, has_levitate=False):
    mult = 1.0
    for t in types:
        td = type_data[t]
        if against_type in td['no_from']:
            return 0.0
        elif against_type in td['double_from']:
            mult *= 2.0
        elif against_type in td['half_from']:
            mult *= 0.5
    if has_levitate and against_type == 'ground':
        return 0.0
    return mult

# ===== 图1: 柱状图 =====
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
axes = axes.flatten()

for i, (pkm, color) in enumerate(zip(pokemon, colors)):
    vals = [stats['HP'][i], stats['攻击'][i], stats['防御'][i], 
            stats['特攻'][i], stats['特防'][i], stats['速度'][i]]
    bars = axes[i].bar(['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe'], vals, color=color, edgecolor='white', linewidth=0.8, alpha=0.85)
    axes[i].set_title(f'{pkm}', fontsize=13, fontweight='bold')
    axes[i].set_ylim(0, 150)
    axes[i].axhline(y=100, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
    axes[i].grid(axis='y', alpha=0.3)
    for bar, val in zip(bars, vals):
        axes[i].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 2, str(val),
                     ha='center', va='bottom', fontsize=8, fontweight='bold')
    bst = sum(vals)
    axes[i].text(0.5, 0.95, f'BST: {bst}', transform=axes[i].transAxes, ha='center', 
                 fontsize=10, fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

fig.suptitle('Team Stats Distribution', fontsize=16, fontweight='bold', y=1.01)
plt.tight_layout()
plt.savefig('team_stats_bar.png', dpi=150, bbox_inches='tight')
plt.close()
print("Bar chart saved.")

# ===== 图2: 雷达图 =====
labels = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe']
num_vars = len(labels)
angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
angles += angles[:1]

fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))

for i, (pkm, color) in enumerate(zip(pokemon, colors)):
    values = [stats['HP'][i], stats['攻击'][i], stats['防御'][i], 
              stats['特攻'][i], stats['特防'][i], stats['速度'][i]]
    values += values[:1]
    ax.fill(angles, values, alpha=0.08, color=color)
    ax.plot(angles, values, 'o-', linewidth=2, color=color, label=pkm, markersize=5)

ax.set_xticks(angles[:-1])
ax.set_xticklabels(labels, fontsize=12, fontweight='bold')
ax.set_ylim(0, 150)
ax.set_yticks([30, 60, 90, 120, 150])
ax.set_yticklabels(['30', '60', '90', '120', '150'], fontsize=8)
ax.set_title('Team Radar Chart — Base Stats Overview', fontsize=15, fontweight='bold', pad=25)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10, framealpha=0.9)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('team_radar.png', dpi=150, bbox_inches='tight')
plt.close()
print("Radar chart saved.")

# ===== 图3: 联防热力图 =====
heatmap_data = []
for i, pkm in enumerate(pokemon):
    row = []
    has_lev = (pkm == 'Rotom-Wash')
    for atk_type in types_all:
        m = calc_multiplier(poke_types[i], atk_type.lower(), has_lev)
        row.append(m)
    heatmap_data.append(row)

best_per_type = []
for j in range(len(types_all)):
    min_val = min(heatmap_data[i][j] for i in range(len(pokemon)))
    best_per_type.append(min_val)

fig, ax = plt.subplots(figsize=(20, 7))
data_array = np.array(heatmap_data)
cmap = plt.cm.RdYlGn_r
im = ax.imshow(data_array, cmap=cmap, aspect='auto', vmin=0, vmax=4)

ax.set_xticks(range(len(types_all)))
ax.set_xticklabels(type_short, fontsize=10, fontweight='bold')
ax.set_yticks(range(len(pokemon)))
ax.set_yticklabels(pokemon, fontsize=11, fontweight='bold')

for i in range(len(pokemon)):
    for j in range(len(types_all)):
        val = heatmap_data[i][j]
        if val == 0:
            text = 'IMMUNE'
            tc = 'darkgreen'
        elif val == 0.25:
            text = 'x0.25'
            tc = 'green'
        elif val == 0.5:
            text = 'x0.5'
            tc = 'darkgreen'
        elif val == 1:
            text = 'x1'
            tc = 'black'
        elif val == 2:
            text = 'x2'
            tc = 'darkred'
        elif val == 4:
            text = 'x4'
            tc = 'red'
        else:
            text = str(val)
            tc = 'black'
        ax.text(j, i, text, ha='center', va='center', fontsize=7.5, fontweight='bold', color=tc,
                bbox=dict(boxstyle='round,pad=0.15', facecolor='white', alpha=0.75))

for j in range(len(types_all)):
    min_val = best_per_type[j]
    for i in range(len(pokemon)):
        if heatmap_data[i][j] == min_val and min_val <= 0.5:
            ax.add_patch(plt.Rectangle((j-0.5, i-0.5), 1, 1, fill=False, edgecolor='blue', linewidth=2.5))

ax.set_title('Defensive Synergy Heatmap — Blue box = best switch-in | Green = resist | Red = weakness', fontsize=14, fontweight='bold', pad=15)
plt.colorbar(im, ax=ax, label='Damage Multiplier', shrink=0.85)
plt.tight_layout()
plt.savefig('team_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print("Heatmap saved.")

print("ALL DONE")

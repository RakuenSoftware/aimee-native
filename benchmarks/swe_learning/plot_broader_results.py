"""Plot all frozen follow-up tasks, explicitly distinguishing pending outcomes.

Run with python3 -P so the neighboring benchmark select.py does not shadow
the standard-library select module imported by matplotlib.
"""
import argparse
import json
import pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

p = argparse.ArgumentParser()
p.add_argument('report')
p.add_argument('output')
a = p.parse_args()
x = json.loads(pathlib.Path(a.report).read_text())
if len(x['tasks']) != 32 or x['scheduled_attempts'] != 64:
    raise ValueError('expected the frozen 32-task follow-up')
arms = ['source-control', 'source-learn-1']
states = ['failed', 'passed', 'pending', 'ungraded']
values = [[states.index(t['outcomes'][arm]['status']) for arm in arms] for t in x['tasks']]
fig, ax = plt.subplots(figsize=(10, 13))
ax.imshow(values, cmap=ListedColormap(['#ead8d6', '#207a58', '#f0f1f3', '#e7ba68']), vmin=0, vmax=3, aspect='auto')
labels = []
for name, arm in zip(['Control', 'Native reuse'], arms):
    counts = x['arms'][arm]
    labels.append(f'{name}\n{counts["passed"]} pass / {counts["failed"]} fail\n{counts["pending"]} pending / {counts["ungraded"]} ungraded')
ax.set_xticks(range(2), labels, fontsize=12)
ax.xaxis.tick_top()
ax.tick_params(length=0, pad=10)
ax.set_yticks(range(32), [t['instance_id'].replace('__', ' / ') for t in x['tasks']], fontsize=10)
for i, row in enumerate(values):
    for j, value in enumerate(row):
        ax.text(j, i, ['fail', 'pass', 'pending', 'ungraded'][value], ha='center', va='center',
                color='white' if value == 1 else '#303840', fontsize=10)
ax.set_xticks([-.5, .5, 1.5], minor=True)
ax.set_yticks([i-.5 for i in range(33)], minor=True)
ax.grid(which='minor', color='white', linewidth=2)
ax.tick_params(which='minor', length=0)
for spine in ax.spines.values():
    spine.set_visible(False)
complete = x['status'] == 'complete'
fig.suptitle(('Completed follow-up' if complete else 'Interim follow-up') + f': {x["graded_attempts"]}/64 scored attempts', fontsize=17, y=.995)
pairs = x['paired_tasks']
fig.text(.5, .035, f'Complete pairs: {32-pairs["incomplete"]}/32 · Native-only passes: {pairs["native_only"]} · Control-only passes: {pairs["control_only"]}\n'
         'One control followed by one native attempt; no prior calibration memory supplied.\n'
         'No second no-memory attempt: this does not isolate a memory effect from retrying.', ha='center', fontsize=10)
fig.subplots_adjust(left=.42, right=.98, top=.89, bottom=.09)
out = pathlib.Path(a.output)
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out.with_suffix('.png'), dpi=160)
fig.savefig(out.with_suffix('.pdf'))
plt.close(fig)

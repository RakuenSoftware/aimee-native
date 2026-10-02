"""Render the completed primary outcome matrix from its audited report."""
import argparse,json,pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

p=argparse.ArgumentParser();p.add_argument('report');p.add_argument('output');a=p.parse_args()
x=json.loads(pathlib.Path(a.report).read_text())
if x['status']!='complete' or x['graded_attempts']!=64:raise ValueError('completed 64-outcome report required')
arms=['source-control','source-learn-1','source-learn-2','source-learn-3']
values=[[int(t['outcomes'][arm]['status']=='passed') for arm in arms] for t in x['tasks']]
fig,ax=plt.subplots(figsize=(11,9))
ax.imshow(values,cmap=ListedColormap(['#e4e7eb','#207a58']),vmin=0,vmax=1,aspect='auto')
ax.set_xticks(range(4),[f'{name}\n{x["arms"][arm]["passed"]}/16 tasks passed' for name,arm in zip(['Control','Native round 1','Native round 2','Native round 3'],arms)],fontsize=12)
ax.xaxis.tick_top();ax.tick_params(length=0,pad=9)
ax.set_yticks(range(16),[t['instance_id'].replace('__',' / ') for t in x['tasks']],fontsize=11)
for i,row in enumerate(values):
 for j,value in enumerate(row):ax.text(j,i,'pass' if value else 'fail',ha='center',va='center',color='white' if value else '#303840',fontsize=11)
ax.set_xticks([-.5,.5,1.5,2.5,3.5],minor=True)
ax.set_yticks([i-.5 for i in range(17)],minor=True)
ax.grid(which='minor',color='white',linewidth=2);ax.tick_params(which='minor',length=0)
for spine in ax.spines.values():spine.set_visible(False)
fig.suptitle('Primary study: complete paired task outcomes',fontsize=18,y=.99)
fig.text(.5,.025,'Same-task reuse; repeated rounds are not independent tasks.\nSuccessful calibration procedures were replay-validated before the native rounds.',ha='center',fontsize=11)
fig.subplots_adjust(left=.37,right=.99,top=.87,bottom=.085)
out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(out.with_suffix('.png'),dpi=180);fig.savefig(out.with_suffix('.pdf'));plt.close(fig)

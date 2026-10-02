"""Summarize saved exact-image evidence without resampling or filtering failures."""
import argparse,json,math,pathlib,statistics
p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--output',required=True);a=p.parse_args()
root=pathlib.Path(a.directory);report=json.loads((root/'report.json').read_text());summary={'image':report['image_inspect'],'status':report['status'],'profiles':{}}
for profile,v in report['profiles'].items():
 matrix=json.loads((root/profile/'matrix.json').read_text());m=v['metrics']['after_streaming'];workers=m['workers']['workers']
 row={'status':v['status'],'matrix_answers':len(matrix['rows']),'matrix_correct':sum(r['correct'] for r in matrix['rows']),
      'concurrency_answers':len(v['concurrency']),'concurrency_correct':sum(r['correct'] for r in v['concurrency']),
      'streaming_answers':len(v['streaming']),'streaming_correct':sum(r['correct'] for r in v['streaming']),
      'backpressure_responses':sum(r['retries'] for r in v['concurrency']),
      'cgroup_peak_bytes':int(m['cgroup'][1]),'cgroup_limit_bytes':int(m['cgroup'][2]),
      'native_peak_bytes_per_rank':[r['peak_bytes'] for r in workers],
      'torch_peak_reserved_bytes_per_rank':[r['device']['torch_peak_reserved_bytes'] for r in workers],
      'driver_used_bytes_per_rank':[r['device']['driver_used_bytes'] for r in workers],'streaming':{}}
 for mode,turns in sorted(set((r['mode'],r['turns']) for r in v['streaming'])):
  rows=[r for r in v['streaming'] if (r['mode'],r['turns'])==(mode,turns)];x=sorted(r['ttft_ms'] for r in rows)
  row['streaming'][f'{mode}-{turns}']={'n':len(x),'ttft_median_ms':statistics.median(x),'ttft_p95_nearest_rank_ms':x[math.ceil(.95*len(x))-1],
      'prompt_tokens':sorted(set(r['usage']['prompt_tokens'] for r in rows)),
      'completion_tokens':sorted(set(r['usage']['completion_tokens'] for r in rows))}
 summary['profiles'][profile]=row
pathlib.Path(a.output).write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

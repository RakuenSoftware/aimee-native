"""Conservative acceptance gate for this experiment's affine procedure grammar."""
import re
PATTERN=re.compile(r'multiply (?:the input |input )?by ([+-]?\d+) (?:and|then) (add|subtract) ([+-]?\d+)\.?',re.I)
def validate(rule, examples):
 match=PATTERN.fullmatch(' '.join(rule.split()))
 if not match:return dict(accepted=False,reason='unsupported procedure syntax',checks=[])
 multiplier=int(match[1]);offset=int(match[3])*(1 if match[2].lower()=='add' else -1)
 checks=[dict(input=e['input'],expected=e['output'],actual=multiplier*e['input']+offset) for e in examples]
 passed=bool(checks) and all(c['expected']==c['actual'] for c in checks)
 return dict(accepted=passed,reason='all original training examples pass' if passed else 'original training example mismatch',checks=checks)
def choose(candidate, previous, examples):
 verdict=validate(candidate,examples)
 return dict(candidate=candidate,previous=previous,selected=candidate if verdict['accepted'] else previous,**verdict)

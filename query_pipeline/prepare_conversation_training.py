"""Merge identifier-only examples into your own existing intent dataset."""
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--input',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
data=json.loads(Path(a.input).read_text())
sample=json.loads((Path(__file__).parent/'data/intent_classification/demo_train.json').read_text())
added=next(x for x in sample['intents'] if x['context']=='identifiers')
existing=next((x for x in data['intents'] if x['context']=='identifiers'),None)
if existing:
 existing['query_patterns']=list(dict.fromkeys(existing['query_patterns']+added['query_patterns']))
else: data['intents'].append(added)
Path(a.output).write_text(json.dumps(data,indent=2))

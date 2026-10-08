import pytest
from app.graph import build_graph, evaluate, ExtraTask

class Classifier:
 def __init__(self,label): self.label=label; self.calls=0
 def predict(self,q): self.calls+=1; return self.label
class Extractor:
 def __init__(self): self.calls=0
 def predict(self,q): self.calls+=1; return {'employee_id':'00222'}
@pytest.mark.parametrize('query,numeric', [('120003',True),('The employee ID is 00222',False)])
def test_existing_context_always_classifies(query,numeric):
 c=Classifier('identifiers'); e=Extractor()
 r=evaluate(build_graph(c,e),{'query':query,'context':'case_details'})
 assert c.calls==1
 assert e.calls==(0 if numeric else 1)
 assert r['context']=='case_details'
 assert r['identifiers']['case_id' if numeric else 'employee_id']==('120003' if numeric else '00222')
def test_switch_clears_old_ids():
 c=Classifier('letter_generation'); e=Extractor()
 r=evaluate(build_graph(c,e),{'query':'get recent letter for employee 00222','context':'case_details','identifiers':{'case_id':'999'}})
 assert r['context']=='letter_generation'
 assert r['identifiers']['case_id']==''
 assert r['identifiers']['employee_id']=='00222'
def test_no_previous_business_context_stops():
 c=Classifier('identifiers'); e=Extractor()
 r=evaluate(build_graph(c,e),{'query':'120003','context':''})
 assert r['status']=='awaiting_intent'
 assert not e.calls

def test_unknown_with_previous_context_stops():
 c=Classifier(''); e=Extractor()
 r=evaluate(build_graph(c,e),{'query':'unrelated','context':'case_details'})
 assert r['context']==''
 assert r['status']=='awaiting_intent'
 assert not e.calls

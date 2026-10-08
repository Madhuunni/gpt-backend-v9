import pytest
from context_tasks import case_details
from context_tasks.router import context_dispatcher
from workflow_outcomes import IdentifierRequired
from workflow_errors import TaskExecutionError
from app.graph import build_graph, evaluate, ExtraTask


def test_postprocess_unwraps_typed_response(monkeypatch):
    monkeypatch.setattr(case_details, 'call_http_api', lambda state: {'status_code':200,'data':{'type':'json','details':{'balance':12}}})
    result=case_details.process_case_details({})
    assert result == {'type':'json','details':{'balance':12}}

def test_missing_id_outcome_preserved(monkeypatch):
    outcome=IdentifierRequired()
    monkeypatch.setattr(case_details,'call_http_api',lambda state:outcome)
    assert case_details.process_case_details({}) is outcome

def test_only_selected_context_runs():
    calls=[]
    dispatch=context_dispatcher({'case_details':lambda s:calls.append('case') or {'ok':True},
                                 'letter_generation':lambda s:calls.append('letter') or {}})
    assert dispatch({'context':'case_details'})=={'ok':True}
    assert calls==['case']
    with pytest.raises(TaskExecutionError): dispatch({'context':'unsupported'})

def test_unexpected_processor_error_names_function():
    def process_case_details(state): raise ValueError('invalid payload')
    with pytest.raises(TaskExecutionError) as exc:
        context_dispatcher({'case_details':process_case_details})({'context':'case_details'})
    assert exc.value.task=='process_case_details'

def test_graph_preserves_result_key_and_stops_on_clarification():
    class C:
        def predict(self,q): return 'case_details'
    class E:
        def predict(self,q): return {'case_id':'123'}
    def later(s): raise AssertionError('must not run')
    task=context_dispatcher({'case_details':lambda s:IdentifierRequired()})
    graph=build_graph(C(),E(),[ExtraTask('call_http_api',task),ExtraTask('later',later)])
    assert evaluate(graph,'show case 123')['status']=='awaiting_identifier'
    task=context_dispatcher({'case_details':lambda s:{'type':'text','content':'done'}})
    graph=build_graph(C(),E(),[ExtraTask('call_http_api',task)])
    assert evaluate(graph,'show case 123')['results']['call_http_api']['content']=='done'

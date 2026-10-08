import pytest
from app.graph import build_graph, evaluate, ExtraTask
from app.schemas import QueryRequest, QueryResponse
from workflow_errors import TaskExecutionError

class Classifier:
    def __init__(self, value): self.value = value
    def predict(self, query): return self.value
class Extractor:
    def predict(self, query): raise AssertionError('Extraction must not run')

@pytest.mark.parametrize('context', [None, '', '  '])
def test_unknown_intent_stops(context):
    def downstream(state): raise AssertionError('HTTP must not run')
    graph = build_graph(Classifier(context), Extractor(), [ExtraTask('call_http_api', downstream)])
    result = evaluate(graph, 'unknown query')
    assert result['context'] == ''
    assert result['status'] == 'awaiting_intent'
    assert result['pending_field'] == 'intent'
    assert result['action_required']
    assert not any(result['identifiers'].values())
    assert 'results' not in result
    QueryResponse(**result)
    QueryRequest(**result)

def test_recognized_intent_continues():
    class ValidExtractor:
        def predict(self, query): return {'case_id': '00123'}
    graph = build_graph(Classifier('case_details'), ValidExtractor(),
                        [ExtraTask('call_http_api', lambda state: {'ok': True})])
    result = evaluate(graph, 'show case 00123')
    assert result['status'] == 'completed'
    assert result['action_required'] == ''

def test_model_failure_remains_error():
    class BrokenClassifier:
        def predict(self, query): raise RuntimeError('model failure')
    with pytest.raises(TaskExecutionError):
        evaluate(build_graph(BrokenClassifier(), Extractor()), 'query')

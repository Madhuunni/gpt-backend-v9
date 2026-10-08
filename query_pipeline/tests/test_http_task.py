import json

import httpx
import pytest

from app.graph import ExtraTask, build_graph, evaluate
from workflow_outcomes import IdentifierRequired
from workflow_errors import IntentNotFoundError, TaskExecutionError, MissingIdentifiersError
from app.extensions import EXTRA_TASKS
from http_task.task import HTTPTaskError, call_http_api


class Classifier:
    def __init__(self, context):
        self.context = context
    def predict(self, query):
        return self.context


class Extractor:
    def predict(self, query):
        return {"employee_id": "00123"}


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setenv("DOWNSTREAM_API_URL", "https://example.test/details")
    monkeypatch.setenv("DOWNSTREAM_API_TOKEN", "test-token")


def test_http_response_in_graph(configure, monkeypatch):
    def post(url, **kwargs):
        assert url == "https://example.test/details"
        assert kwargs["json"] == {"query": "original query", "context": "case_details", "identifiers": {"case_id":"", "employee_id": "00123", "sr_no":""}}
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert kwargs["timeout"] == 15
        assert kwargs["follow_redirects"] is False
        return httpx.Response(200, json=[{"amount": 100}])
    monkeypatch.setattr(httpx, "post", post)
    result = evaluate(build_graph(Classifier("case_details"), Extractor(), EXTRA_TASKS), "original query")
    assert result["action_required"] == ""
    assert result["results"]["call_http_api"] == {"status_code": 200, "data": [{"amount": 100}]}


def test_unknown_skips_http(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("HTTP must not run for unknown context")
    monkeypatch.setattr(httpx, "post", forbidden)
    with pytest.raises(IntentNotFoundError):
        evaluate(build_graph(Classifier(""), Extractor(), EXTRA_TASKS), "unknown")


@pytest.mark.parametrize("response,expected", [(httpx.Response(503),502)])
def test_invalid_response(configure, monkeypatch, response, expected):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response)
    with pytest.raises(HTTPTaskError) as exc:
        call_http_api({"query":"q","context":"c","identifiers":{}})
    assert exc.value.status_code == expected


def test_timeout(configure, monkeypatch):
    def post(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(HTTPTaskError) as exc:
        call_http_api({"query":"q","context":"c","identifiers":{}})
    assert exc.value.status_code == 504


def test_http_204_response(configure, monkeypatch):
    def post(*args, **kwargs):
        assert kwargs["json"]["identifiers"] == {"case_id":"123"}
        return httpx.Response(204)
    monkeypatch.setattr(httpx, "post", post)
    assert call_http_api({"query":"q","context":"c","identifiers":{"case_id":"123"}}) == IdentifierRequired()


def test_missing_configuration(monkeypatch):
    monkeypatch.delenv("DOWNSTREAM_API_URL", raising=False)
    with pytest.raises(HTTPTaskError, match="not configured"):
        call_http_api({})


@pytest.mark.parametrize("identifiers", [{}, {"employee_id":"", "case_id":"", "sr_no":""},
                                        {"employee_id":"  ", "case_id":None}])
def test_no_ids_stops_graph_before_http(monkeypatch, identifiers):
    class EmptyExtractor:
        def predict(self, query):
            return identifiers
    def forbidden(*args, **kwargs):
        pytest.fail("HTTP must not run after extraction fails")
    monkeypatch.setattr(httpx, "post", forbidden)
    result = evaluate(build_graph(Classifier("case_details"), EmptyExtractor(), EXTRA_TASKS), "q")
    assert result["context"] == "case_details"
    assert result["identifiers"] == {"employee_id":"", "case_id":"", "sr_no":""}
    assert result["action_required"]
    assert result["status"] == "awaiting_identifier"
    assert "results" not in result


def test_unexpected_task_exception_keeps_task_name():
    class BrokenExtractor:
        def predict(self, query):
            raise RuntimeError("private internal details")
    with pytest.raises(TaskExecutionError) as caught:
        evaluate(build_graph(Classifier("known"), BrokenExtractor()), "q")
    assert caught.value.detail() == {"task":"extract_identifiers", "code":"TASK_EXECUTION_FAILED", "message":"Task execution failed."}


def test_new_tasks_use_shared_error_contract():
    from app.graph import ExtraTask
    def fail(state):
        raise TaskExecutionError(task="employee_lookup", code="EMPLOYEE_NOT_FOUND",
                                 message="Employee not found.", status_code=404)
    with pytest.raises(TaskExecutionError) as caught:
        evaluate(build_graph(Classifier("known"), Extractor(), [ExtraTask("employee_lookup", fail)]), "q")
    assert caught.value.code == "EMPLOYEE_NOT_FOUND"
    assert caught.value.status_code == 404


@pytest.mark.parametrize("error", [IntentNotFoundError(), MissingIdentifiersError(),
                                  HTTPTaskError("Downstream API timed out", 504, "DOWNSTREAM_TIMEOUT")])
def test_central_api_error_handler(error):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.error_handlers import register_error_handlers
    app = FastAPI()
    register_error_handlers(app)
    @app.get("/test")
    def run():
        raise error
    with TestClient(app) as client:
        response = client.get("/test")
    assert response.status_code == error.status_code
    assert response.json() == {"detail": error.detail()}


def test_action_required_without_extensions_and_reset_between_queries():
    class MaybeExtractor:
        def predict(self, query):
            return {} if query == "missing" else {"employee_id": "00123"}
    graph = build_graph(Classifier("case_details"), MaybeExtractor())
    assert evaluate(graph, "missing")["action_required"]
    assert evaluate(graph, "present")["action_required"] == ""


@pytest.mark.parametrize("response", [
    httpx.Response(200, content=b""), httpx.Response(200, text="  "),
    httpx.Response(204), httpx.Response(200, text="not JSON"),
    httpx.Response(200, text="<html>no records</html>"),
    httpx.Response(200, text="null"), httpx.Response(200, json={}),
    httpx.Response(200, json=[]), httpx.Response(200, json=""),
    httpx.Response(200, json="  "), httpx.Response(200, text="NaN"),
    httpx.Response(200, text='{"value":1e999}'),
])
def test_empty_or_invalid_http_requests_identifier(configure, monkeypatch, response):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response)
    def forbidden(state):
        pytest.fail("Later tasks must not run")
    graph = build_graph(Classifier("case_details"), Extractor(), [
        ExtraTask("before",lambda s: {"ok":True}),
        *EXTRA_TASKS, ExtraTask("later", forbidden),
    ])
    result = evaluate(graph, "query")
    assert result["context"] == "case_details"
    assert result["action_required"] == "Enter a valid Case ID or Employee ID or SR Number"
    assert result["pending_field"] == "identifier"
    assert result["status"] == "awaiting_identifier"
    assert not any(result["identifiers"].values())
    assert "call_http_api" not in result["results"]


@pytest.mark.parametrize("value", [0, False, {"amount":0}, [1], "found"])
def test_valid_nonempty_json_proceeds(configure, monkeypatch, value):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200,json=value))
    graph = build_graph(Classifier("case_details"), Extractor(), [*EXTRA_TASKS, ExtraTask("later", lambda s:{"ok":True})])
    result = evaluate(graph, "query")
    assert result["status"] == "completed"
    assert result["action_required"] == ""
    assert result["results"]["call_http_api"]["data"] == value
    assert result["results"]["later"] == {"ok":True}


def test_invalid_json_returns_http_200_and_valid_retry(configure, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.schemas import QueryRequest, QueryResponse
    from app.error_handlers import register_error_handlers
    responses = iter([httpx.Response(200,text="invalid"), httpx.Response(200,json={"found":True})])
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return next(responses)
    monkeypatch.setattr(httpx, "post", post)
    graph = build_graph(Classifier("case_details"), Extractor(), EXTRA_TASKS)
    app = FastAPI()
    register_error_handlers(app)
    @app.post("/evaluate",response_model=QueryResponse,response_model_exclude_none=True)
    def run(body:QueryRequest):
        return evaluate(graph,body.model_dump())
    with TestClient(app) as client:
        response = client.post("/evaluate",json={"query":"first query"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "awaiting_identifier"
        assert body["action_required"] == "Enter a valid Case ID or Employee ID or SR Number"
        assert "detail" not in body
        body["query"] = "001111"
        response = client.post("/evaluate",json=body)
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["action_required"] == ""
        assert sent[1]["identifiers"] == {"case_id":"001111","employee_id":"","sr_no":""}

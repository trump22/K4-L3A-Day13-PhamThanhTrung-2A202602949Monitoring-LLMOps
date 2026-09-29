from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class RecordingObservation:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.observations: list[RecordingObservation] = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        observation = RecordingObservation()
        self.calls.append(kwargs)
        self.observations.append(observation)
        yield observation

    def update_current_span(self, **kwargs) -> None:
        return None


def test_agent_creates_safe_retrieval_and_generation_observations(monkeypatch) -> None:
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: False)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Contact student@vinuni.edu.vn at 090 123 4567",
        correlation_id="req-12345678",
    )

    retrieval, generation = client.calls
    assert retrieval["as_type"] == "retriever"
    assert retrieval["metadata"]["correlation_id"] == "req-12345678"
    assert "student@" not in retrieval["input"]["query_preview"]

    assert generation["as_type"] == "generation"
    assert generation["model"] == "claude-sonnet-4-5"
    assert generation["metadata"]["correlation_id"] == "req-12345678"
    assert "student@" not in generation["input"]["message_preview"]
    assert client.observations[0].updates == [{"output": {"document_count": 1}}]
    assert set(client.observations[1].updates[0]) == {
        "output",
        "usage_details",
        "cost_details",
    }

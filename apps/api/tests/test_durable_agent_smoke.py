"""DurableAgent smoke test helpers."""

from unittest.mock import MagicMock, patch

import pytest

from workflows.durable_agent_smoke import SMOKE_AGENT_NAME, build_smoke_durable_agent


@patch("workflows.durable_agent_smoke.DurableAgent")
@patch("workflows.durable_agent_smoke.StateStoreService")
@patch("workflows.durable_agent_smoke.ConversationDaprStateMemory")
@patch("workflows.durable_agent_smoke.DaprChatClient")
def test_build_smoke_durable_agent_configures_name_and_role(
    _mock_llm: MagicMock,
    _mock_memory: MagicMock,
    _mock_state: MagicMock,
    mock_agent_cls: MagicMock,
) -> None:
    mock_agent_cls.return_value = MagicMock(name=SMOKE_AGENT_NAME, role="SmokeAssistant")
    build_smoke_durable_agent()
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["name"] == SMOKE_AGENT_NAME
    assert kwargs["role"] == "SmokeAssistant"
    assert kwargs["llm"] is _mock_llm.return_value


@patch("workflows.durable_agent_smoke.DurableAgent")
@patch("workflows.durable_agent_smoke.StateStoreService")
@patch("workflows.durable_agent_smoke.ConversationDaprStateMemory")
@patch("workflows.durable_agent_smoke.DaprChatClient")
def test_build_smoke_durable_agent_accepts_runtime(
    _mock_llm: MagicMock,
    _mock_memory: MagicMock,
    _mock_state: MagicMock,
    mock_agent_cls: MagicMock,
) -> None:
    runtime = MagicMock()
    build_smoke_durable_agent(runtime)
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["runtime"] is runtime


@pytest.mark.integration
def test_durable_agent_smoke_requires_dapr_runtime() -> None:
    """Documented integration hook; skipped unless Dapr sidecar is reachable."""
    pytest.skip("run manually with Dapr sidecar and @pytest.mark.smoke")

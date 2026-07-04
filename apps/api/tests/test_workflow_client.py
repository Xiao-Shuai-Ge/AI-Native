"""WorkflowScheduler client tests."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from workflows.client import WorkflowScheduler
from workflows.models import TASK_WORKFLOW_NAME, TaskWorkflowInput


@pytest.fixture
def wf_input() -> TaskWorkflowInput:
    task_id = uuid4()
    session_id = uuid4()
    workflow_id = f"wf-{task_id}"
    return TaskWorkflowInput(
        task_id=task_id,
        session_id=session_id,
        user_id="test-user",
        user_query="workflow client test",
        engine_requested="auto",
        workflow_id=workflow_id,
        thread_id=str(task_id),
    )


@pytest.mark.asyncio
async def test_schedule_task_uses_stable_instance_id(wf_input: TaskWorkflowInput) -> None:
    mock_client = MagicMock()
    mock_client.schedule_new_workflow.return_value = wf_input.workflow_id

    with patch("workflows.client.DaprWorkflowClient", return_value=mock_client):
        scheduler = WorkflowScheduler(grpc_port=50001)
        instance_id = await scheduler.schedule_task(wf_input)

    assert instance_id == wf_input.workflow_id
    mock_client.schedule_new_workflow.assert_called_once()
    args, kwargs = mock_client.schedule_new_workflow.call_args
    assert args[0] == TASK_WORKFLOW_NAME
    assert kwargs["instance_id"] == wf_input.workflow_id
    scheduler.close()


@pytest.mark.asyncio
async def test_pause_and_resume_task(wf_input: TaskWorkflowInput) -> None:
    mock_client = MagicMock()

    with patch("workflows.client.DaprWorkflowClient", return_value=mock_client):
        scheduler = WorkflowScheduler(grpc_port=50001)
        await scheduler.pause_task(wf_input.workflow_id)
        await scheduler.resume_task(wf_input.workflow_id)

    mock_client.pause_workflow.assert_called_once_with(wf_input.workflow_id)
    mock_client.resume_workflow.assert_called_once_with(wf_input.workflow_id)
    scheduler.close()


@pytest.mark.asyncio
async def test_get_runtime_status(wf_input: TaskWorkflowInput) -> None:
    mock_state = MagicMock()
    mock_state.runtime_status.name = "RUNNING"
    mock_client = MagicMock()
    mock_client.get_workflow_state.return_value = mock_state

    with patch("workflows.client.DaprWorkflowClient", return_value=mock_client):
        scheduler = WorkflowScheduler(grpc_port=50001)
        status = await scheduler.get_runtime_status(wf_input.workflow_id)

    assert status == "RUNNING"
    scheduler.close()

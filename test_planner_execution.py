from types import SimpleNamespace
from unittest.mock import patch

from app.orchestrator.verification_orchestrator import (
    _gather_planned_evidence,
)
from app.schemas.verification import (
    PlannerInput,
    PlannerTask,
    PlannerTaskType,
    ResearchSource,
)


proposal = PlannerInput(
    proposal_id="proposal_plan_test",
    article_title="Helsinki",
    language_code="en",
    proposed_text="Helsinki is the capital of Finland.",
)

claim = SimpleNamespace(
    claim_id="claim_plan_test",
    claim_text="Helsinki is the capital of Finland.",
)

source = ResearchSource(
    source_id="source_plan_test",
    title="Test source",
    url="https://example.com/helsinki",
    content="Helsinki is the capital of Finland.",
    retrieved_at="2026-11-14T12:00:00+00:00",
)


def task(task_type, required=True):
    return PlannerTask(
        task_id=f"task_{task_type.value}",
        task_type=task_type,
        rationale="Test task selection.",
        priority=5,
        required=required,
    )


def run(tasks, embed_text=None):
    return _gather_planned_evidence(
        connection=object(),
        claim=claim,
        proposal=proposal,
        embed_text=embed_text or (lambda text: [0.0] * 1024),
        tasks=tasks,
        oxylabs_client=object(),
        top_k=5,
    )


# ---------------------------------------------------------
# 1. Internal retrieval only
# ---------------------------------------------------------

internal_result = SimpleNamespace(matches=[])

with patch(
    "app.orchestrator.verification_orchestrator.retrieve_knowledge",
    return_value=internal_result,
) as internal_mock, patch(
    "app.orchestrator.verification_orchestrator.research_claim",
) as external_mock:

    sources, internal, external, warnings = run([
        task(PlannerTaskType.INTERNAL_RETRIEVAL)
    ])

    assert internal is internal_result
    assert external is None
    assert sources == []
    assert warnings == []
    assert internal_mock.call_count == 1
    external_mock.assert_not_called()

print("INTERNAL-ONLY TASK SELECTION: SUCCESS")


# ---------------------------------------------------------
# 2. External research only
# ---------------------------------------------------------

external_result = SimpleNamespace(sources=[source])

with patch(
    "app.orchestrator.verification_orchestrator.retrieve_knowledge",
) as internal_mock, patch(
    "app.orchestrator.verification_orchestrator.research_claim",
    return_value=external_result,
) as external_mock:

    sources, internal, external, warnings = run([
        task(PlannerTaskType.EXTERNAL_RESEARCH)
    ])

    assert len(sources) == 1
    assert sources[0].source_id == source.source_id
    assert internal is None
    assert external is external_result
    assert warnings == []
    internal_mock.assert_not_called()
    assert external_mock.call_count == 1

print("EXTERNAL-ONLY TASK SELECTION: SUCCESS")


# ---------------------------------------------------------
# 3. Both retrieval systems requested
# ---------------------------------------------------------

with patch(
    "app.orchestrator.verification_orchestrator.retrieve_knowledge",
    return_value=internal_result,
) as internal_mock, patch(
    "app.orchestrator.verification_orchestrator.research_claim",
    return_value=external_result,
) as external_mock:

    sources, internal, external, warnings = run([
        task(PlannerTaskType.INTERNAL_RETRIEVAL),
        task(PlannerTaskType.EXTERNAL_RESEARCH),
    ])

    assert internal is internal_result
    assert external is external_result
    assert len(sources) == 1
    assert warnings == []
    assert internal_mock.call_count == 1
    assert external_mock.call_count == 1

print("DUAL RETRIEVAL TASK SELECTION: SUCCESS")


# ---------------------------------------------------------
# 4. Optional external research failure
# ---------------------------------------------------------

with patch(
    "app.orchestrator.verification_orchestrator.research_claim",
    side_effect=ConnectionError("Simulated Oxylabs outage"),
):

    sources, internal, external, warnings = run([
        task(
            PlannerTaskType.EXTERNAL_RESEARCH,
            required=False,
        )
    ])

    assert sources == []
    assert external is None
    assert len(warnings) == 1
    assert "external_research failed" in warnings[0]
    assert "Optional task skipped" in warnings[0]

print("OPTIONAL TASK FAILURE HANDLING: SUCCESS")


# ---------------------------------------------------------
# 5. Required external research failure
# ---------------------------------------------------------

required_failure_detected = False

with patch(
    "app.orchestrator.verification_orchestrator.research_claim",
    side_effect=ConnectionError("Simulated Oxylabs outage"),
):

    try:
        run([
            task(
                PlannerTaskType.EXTERNAL_RESEARCH,
                required=True,
            )
        ])
    except RuntimeError as exc:
        required_failure_detected = (
            "Required Planner task failed" in str(exc)
        )

assert required_failure_detected

print("REQUIRED TASK FAILURE HANDLING: SUCCESS")


# ---------------------------------------------------------
# 6. Optional historical review
# ---------------------------------------------------------

sources, internal, external, warnings = run([
    task(
        PlannerTaskType.HISTORICAL_REVIEW,
        required=False,
    )
])

assert sources == []
assert any(
    "Historical review" in warning
    and "Optional task skipped" in warning
    for warning in warnings
)

print("OPTIONAL HISTORICAL REVIEW HANDLING: SUCCESS")


# ---------------------------------------------------------
# 7. Required historical review
# ---------------------------------------------------------

required_history_detected = False

try:
    run([
        task(
            PlannerTaskType.HISTORICAL_REVIEW,
            required=True,
        )
    ])
except NotImplementedError as exc:
    required_history_detected = (
        "Historical review" in str(exc)
    )

assert required_history_detected

print("REQUIRED HISTORICAL REVIEW HANDLING: SUCCESS")


# ---------------------------------------------------------
# 8. Empty evidence plan
# ---------------------------------------------------------

sources, internal, external, warnings = run([])

assert sources == []
assert internal is None
assert external is None
assert warnings
assert "no available evidence-gathering tasks" in warnings[0]

print("EMPTY EVIDENCE PLAN HANDLING: SUCCESS")


print("\nPLANNER EXECUTION TESTS: ALL PASSED")

import uuid
from concurrent.futures import ThreadPoolExecutor

from app.agents.planner import (
    build_planner_prompt,
    parse_planner_output,
)
from app.agents.claim_extractor import (
    build_claim_extraction_prompt,
    parse_claim_extraction_output,
)
from app.agents.knowledge_retriever import retrieve_knowledge
from app.agents.internal_evidence import convert_knowledge_matches
from app.agents.research_agent import research_claim
from app.agents.evidence_pipeline import combine_evidence_sources
from app.agents.verification_agent import (
    build_verification_prompt,
    parse_verification_output,
)
from app.agents.critique_agent import (
    build_critique_prompt,
    parse_critique_output,
)
from app.agents.decision_agent import (
    build_decision_prompt,
    parse_decision_output,
)

from app.schemas.persistence import ClaimExecutionRecord


from app.schemas.verification import (
    PlannerInput,
    ClaimExtractionInput,
    KnowledgeRetrievalInput,
    ResearchInput,
    VerificationAgentInput,
    CritiqueAgentInput,
    DecisionAgentInput,
    CritiqueAgentResult,
    VerificationResult,
    ClaimDecision,
    PlannerTask,
    PlannerTaskType,
)


from app.agents import (
    planner as _planner,
    claim_extractor as _claim_extractor,
    verification_agent as _verification_agent,
    critique_agent as _critique_agent,
    decision_agent as _decision_agent,
)


# Each agent's system prompt holds its rules and exact output JSON schema. The
# LLM client only forwards the prompt string (with a generic system message), so
# the orchestrator must prepend the agent's system prompt here - otherwise the
# model never sees the schema and returns a non-conforming shape.
_SYSTEM_PROMPTS = {
    "planner": _planner.PLANNER_SYSTEM_PROMPT,
    "claim_extractor": _claim_extractor.CLAIM_EXTRACTOR_SYSTEM_PROMPT,
    "verification_agent": _verification_agent.VERIFICATION_SYSTEM_PROMPT,
    "critique_agent": _critique_agent.CRITIQUE_SYSTEM_PROMPT,
    "decision_agent": _decision_agent.DECISION_SYSTEM_PROMPT,
}


def _call_agent(model_call, agent_name: str, prompt: str) -> str:
    """Call the injected LLM provider and validate its response type.

    The agent's system prompt (its rules and exact JSON schema) is prepended to
    the prompt so the model actually receives it.
    """

    system_prompt = _SYSTEM_PROMPTS.get(agent_name, "")
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    response = model_call(agent_name, full_prompt)

    if not isinstance(response, str):
        raise TypeError(
            f"{agent_name} must return a JSON string."
        )

    if not response.strip():
        raise ValueError(
            f"{agent_name} returned an empty response."
        )

    return response


def _validate_embedding(embedding: list[float]) -> list[float]:
    """Validate the embedding before sending it to MariaDB."""

    if not isinstance(embedding, list) or len(embedding) != 1024:
        raise ValueError(
            "Embedding function must return exactly 1024 values."
        )

    import math

    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in embedding
    ):
        raise ValueError(
            "Embedding contains invalid numeric values."
        )

    return [float(value) for value in embedding]


def _gather_evidence(
    connection,
    claim,
    proposal,
    embed_text,
    oxylabs_client=None,
    top_k: int = 5,
):
    """Retrieve internal and external evidence concurrently."""

    embedding = _validate_embedding(
        embed_text(claim.claim_text)
    )

    knowledge_request = KnowledgeRetrievalInput(
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        embedding=embedding,
        top_k=top_k,
        language_code=proposal.language_code,
    )

    research_request = ResearchInput(
        proposal_id=proposal.proposal_id,
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        language_code=proposal.language_code,
        search_query=claim.claim_text,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        internal_future = executor.submit(
            retrieve_knowledge,
            connection,
            knowledge_request,
        )

        external_future = executor.submit(
            research_claim,
            research_request,
            oxylabs_client,
        )

        internal_result = internal_future.result()
        external_result = external_future.result()

    internal_sources = convert_knowledge_matches(
        internal_result.matches
    )

    combined_sources = combine_evidence_sources(
        internal_sources,
        external_result.sources,
    )

    return combined_sources, internal_result, external_result


def _gather_planned_evidence(
    connection,
    claim,
    proposal,
    embed_text,
    tasks: list[PlannerTask],
    oxylabs_client=None,
    top_k: int = 5,
):
    """Execute only evidence tasks selected by the Planner."""

    task_by_type = {}

    for task in tasks:
        if task.task_type == PlannerTaskType.EXTRACT_CLAIMS:
            continue

        if task.task_type in task_by_type:
            raise ValueError(
                "Planner produced duplicate task type: "
                f"{task.task_type.value}"
            )

        task_by_type[task.task_type] = task

    warnings = []
    internal_result = None
    external_result = None
    internal_sources = []
    external_sources = []

    historical_task = task_by_type.get(
        PlannerTaskType.HISTORICAL_REVIEW
    )

    if historical_task is not None:
        message = (
            "Historical review was requested, but its execution "
            "module is not implemented yet."
        )

        if historical_task.required:
            raise NotImplementedError(message)

        warnings.append(message + " Optional task skipped.")

    internal_task = task_by_type.get(
        PlannerTaskType.INTERNAL_RETRIEVAL
    )

    external_task = task_by_type.get(
        PlannerTaskType.EXTERNAL_RESEARCH
    )

    if internal_task is None and external_task is None:
        warnings.append(
            "The Planner selected no available evidence-gathering tasks."
        )
        return [], None, None, warnings

    def retrieve_internal():
        embedding = _validate_embedding(
            embed_text(claim.claim_text)
        )

        request = KnowledgeRetrievalInput(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            embedding=embedding,
            top_k=top_k,
            language_code=proposal.language_code,
        )

        result = retrieve_knowledge(connection, request)

        return result, convert_knowledge_matches(result.matches)

    def retrieve_external():
        request = ResearchInput(
            proposal_id=proposal.proposal_id,
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            language_code=proposal.language_code,
            search_query=claim.claim_text,
        )

        return research_claim(request, oxylabs_client)

    jobs = {}

    worker_count = (
        int(internal_task is not None)
        + int(external_task is not None)
    )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        if internal_task is not None:
            jobs[PlannerTaskType.INTERNAL_RETRIEVAL] = (
                internal_task,
                executor.submit(retrieve_internal),
            )

        if external_task is not None:
            jobs[PlannerTaskType.EXTERNAL_RESEARCH] = (
                external_task,
                executor.submit(retrieve_external),
            )

        for task_type, (task, future) in jobs.items():
            try:
                result = future.result()

                if task_type == PlannerTaskType.INTERNAL_RETRIEVAL:
                    internal_result, internal_sources = result
                else:
                    external_result = result
                    external_sources = result.sources

            except Exception as exc:
                message = (
                    f"{task_type.value} failed: "
                    f"{type(exc).__name__}: {exc}"
                )

                if task.required:
                    raise RuntimeError(
                        f"Required Planner task failed: {message}"
                    ) from exc

                warnings.append(
                    message + " Optional task skipped."
                )

    combined_sources = combine_evidence_sources(
        internal_sources,
        external_sources,
    )

    return (
        combined_sources,
        internal_result,
        external_result,
        warnings,
    )


def _run_verification(
    model_call,
    claim,
    sources,
    additional_context: str = "",
):
    """Run the Verification Agent and parse its structured response."""

    request = VerificationAgentInput(
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        sources=sources,
    )

    prompt = build_verification_prompt(request)

    if additional_context:
        prompt += (
            "\n\nADDITIONAL REASSESSMENT INSTRUCTIONS:\n"
            + additional_context
        )

    raw_response = _call_agent(
        model_call,
        "verification_agent",
        prompt,
    )

    result = parse_verification_output(
        raw_response,
        request,
    )

    return request, result


def _run_critique_round(
    model_call,
    claim,
    sources,
    verification,
    round_number: int,
):
    """Run one adversarial critique round."""

    request = CritiqueAgentInput(
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        round_number=round_number,
        verification=verification,
        sources=sources,
    )

    raw_response = _call_agent(
        model_call,
        "critique_agent",
        build_critique_prompt(request),
    )

    return parse_critique_output(
        raw_response,
        request,
    )


def _aggregate_critiques(
    claim_id: str,
    critiques: list[CritiqueAgentResult],
) -> CritiqueAgentResult:
    """Combine critique findings while preserving their original IDs."""

    if not critiques:
        raise ValueError("At least one critique result is required.")

    unique_findings = {}

    for critique in critiques:
        for finding in critique.findings:
            existing = unique_findings.get(finding.objection_id)

            if existing is not None and existing != finding:
                raise ValueError(
                    "Conflicting critique findings share objection ID: "
                    f"{finding.objection_id}"
                )

            unique_findings[finding.objection_id] = finding

    latest = critiques[-1]

    return CritiqueAgentResult(
        claim_id=claim_id,
        round_number=latest.round_number,
        findings=list(unique_findings.values()),
        agrees_with_verdict=latest.agrees_with_verdict,
        alternative_verdict=latest.alternative_verdict,
        summary="\n".join(
            f"Round {item.round_number}: {item.summary}"
            for item in critiques
        ),
        requires_human_review=True,
    )


def _run_decision(
    model_call,
    claim,
    verification,
    critique,
    sources,
    temporal_context: str = "",
):
    """Run Agent 7 and convert its output to the final claim contract."""

    request = DecisionAgentInput(
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        verification=verification,
        critique=critique,
        sources=sources,
    )

    prompt = build_decision_prompt(request)

    if temporal_context:
        prompt += (
            "\n\nTEMPORAL CONTEXT (article revision history, background only):\n"
            + temporal_context
        )

    raw_response = _call_agent(
        model_call,
        "decision_agent",
        prompt,
    )

    result = parse_decision_output(
        raw_response,
        request,
    )

    claim_decision = ClaimDecision(
        claim_id=result.claim_id,
        verdict=result.verdict,
        confidence=result.confidence,
        supporting_evidence=result.supporting_source_ids,
        contradicting_evidence=result.contradicting_source_ids,
        critique_objections=result.considered_objection_ids,
        reasoning=result.reasoning,
        requires_human_review=True,
    )

    # Return both: the raw DecisionAgentResult for persistence (ClaimExecutionRecord
    # expects it) and the ClaimDecision contract for the final result.
    return result, claim_decision


def run_verification(
    proposal: PlannerInput,
    connection,
    model_call,
    embed_text,
    oxylabs_client=None,
    top_k: int = 5,
    on_claim_completed=None,
    temporal_context: str = "",
    on_stage=None,
) -> VerificationResult:
    """
    Execute the complete seven-agent verification workflow.

    model_call:
        Callable with signature model_call(agent_name, prompt) -> JSON string.

    embed_text:
        Callable with signature embed_text(text) -> list[float] of length 1024.

    connection:
        An open MariaDB connection owned by the caller.
    """

    if not callable(model_call):
        raise TypeError("model_call must be callable.")

    if not callable(embed_text):
        raise TypeError("embed_text must be callable.")

    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")

    def _stage(message):
        if on_stage is not None:
            try:
                on_stage(message)
            except Exception:
                # Progress reporting must never break verification.
                pass

    # ---------------------------------------------------------
    # Agent 1: Planner
    # ---------------------------------------------------------

    _stage("Planning the investigation...")

    planner_raw = _call_agent(
        model_call,
        "planner",
        build_planner_prompt(proposal),
    )

    plan = parse_planner_output(
        planner_raw,
        proposal,
    )

    # ---------------------------------------------------------
    # Agent 2: Claim Extractor
    # ---------------------------------------------------------

    extraction_input = ClaimExtractionInput(
        proposal_id=proposal.proposal_id,
        article_title=proposal.article_title,
        language_code=proposal.language_code,
        old_text=proposal.old_text,
        proposed_text=proposal.proposed_text,
    )

    _stage("Extracting factual claims from the edit...")

    extraction_raw = _call_agent(
        model_call,
        "claim_extractor",
        build_claim_extraction_prompt(extraction_input),
    )

    extraction = parse_claim_extraction_output(
        extraction_raw,
        extraction_input,
    )

    decisions = []
    workflow_warnings = []

    # No factual claims means there is nothing to verify.
    if not extraction.claims:
        return VerificationResult(
            verification_id=str(uuid.uuid4()),
            proposal_id=proposal.proposal_id,
            decisions=[],
            overall_summary=(
                "No independently verifiable factual claims "
                "were identified in the proposed edit."
            ),
            requires_human_review=True,
        )

    # ---------------------------------------------------------
    # Process each extracted claim independently.
    # ---------------------------------------------------------

    _stage(f"Found {len(extraction.claims)} claim(s) to verify.")

    for claim in extraction.claims:

        _stage(f"Gathering evidence for: {claim.claim_text[:70]}")

        # Agents 3 and 4: Execute only the evidence tasks selected
        # by the Planner. Both run concurrently when requested.
        (
            sources,
            internal_result,
            external_result,
            task_warnings,
        ) = _gather_planned_evidence(
            connection=connection,
            claim=claim,
            proposal=proposal,
            embed_text=embed_text,
            tasks=plan.tasks,
            oxylabs_client=oxylabs_client,
            top_k=top_k,
        )

        workflow_warnings.extend(
            f"{claim.claim_id}: {warning}"
            for warning in task_warnings
        )

        # Agent 5: Initial verification.
        _stage("Checking the claim against Wikipedia knowledge and web sources...")
        _, verification = _run_verification(
            model_call,
            claim,
            sources,
        )

        verification_rounds = [verification]
        critiques = []
        max_rounds = min(plan.max_critique_rounds, 2)

        # Agents 6 and 5: Critique and possible reassessment.
        for round_number in range(1, max_rounds + 1):

            _stage(f"Adversarial critique, round {round_number}...")

            critique = _run_critique_round(
                model_call=model_call,
                claim=claim,
                sources=sources,
                verification=verification,
                round_number=round_number,
            )

            critiques.append(critique)

            needs_reassessment = any(
                finding.requires_reassessment
                for finding in critique.findings
            )

            if not needs_reassessment:
                break

            if round_number >= max_rounds:
                break

            reassessment_context = (
                "Reconsider your previous assessment in light of "
                "the following critique findings:\n"
                + "\n".join(
                    f"- [{finding.severity.value}] "
                    f"{finding.objection}"
                    for finding in critique.findings
                    if finding.requires_reassessment
                )
                + "\nReassess the evidence independently. "
                "Do not automatically accept the critique."
            )

            _, verification = _run_verification(
                model_call=model_call,
                claim=claim,
                sources=sources,
                additional_context=reassessment_context,
            )
            verification_rounds.append(verification)

        aggregated_critique = _aggregate_critiques(
            claim.claim_id,
            critiques,
        )

        # Agent 7: Final confidence and decision.
        _stage("Reaching a final decision...")
        decision_result, decision = _run_decision(
            model_call=model_call,
            claim=claim,
            verification=verification,
            critique=aggregated_critique,
            sources=sources,
            temporal_context=temporal_context,
        )

        decisions.append(decision)

        # Optional persistence hook. The caller owns persistence
        # and database transaction handling.
        if on_claim_completed is not None:
            if not callable(on_claim_completed):
                raise TypeError(
                    "on_claim_completed must be callable."
                )

            on_claim_completed(
                ClaimExecutionRecord(
                    claim=claim,
                    sources=sources,
                    verification_rounds=verification_rounds,
                    critique_rounds=critiques,
                    decision=decision_result,
                )
            )


    # ---------------------------------------------------------
    # Final structured result. Human review is mandatory.
    # ---------------------------------------------------------

    supported = sum(
        decision.verdict.value == "supported"
        for decision in decisions
    )

    contradicted = sum(
        decision.verdict.value == "contradicted"
        for decision in decisions
    )

    insufficient = sum(
        decision.verdict.value == "insufficient_evidence"
        for decision in decisions
    )

    summary = (
        f"Verification completed for {len(decisions)} claims. "
        f"Supported: {supported}. "
        f"Contradicted: {contradicted}. "
        f"Insufficient evidence: {insufficient}. "
        "All claims require human review before publication."
    )

    if workflow_warnings:
        summary += (
            f" {len(workflow_warnings)} workflow warning(s) were recorded."
        )

    return VerificationResult(
        verification_id=str(uuid.uuid4()),
        proposal_id=proposal.proposal_id,
        decisions=decisions,
        overall_summary=summary,
        requires_human_review=True,
        warnings=workflow_warnings,
    )





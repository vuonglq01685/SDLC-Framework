"""Auto-brainstorm panel orchestration on upstream ambiguity (Story 4.10, FR22/FR26/FR51)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

from sdlc.concurrency.io_primitives import atomic_write
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import PanelObserver, build_pre_write_hook_chain, dispatch_panel
from sdlc.dispatcher.core import PanelResult
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import JournalEntry, append_with_seq_alloc
from sdlc.runtime import AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

log = logging.getLogger(__name__)

_CLARIFICATIONS_DIR_REL: Final[str] = ".claude/state/clarifications"
_OPEN_CLARIFICATION_NAME: Final[str] = "open_clarification.md"
_OPTIONS_NAME: Final[str] = "options.md"
_AMBIGUITY_SIGNALS_REL: Final[str] = ".claude/state/ambiguity_signals"
_ACTOR: Final[str] = "auto_brainstorm"
_EVENT_SENTINEL: Final[str] = "sha256:" + "0" * 64
_PRIMARY: Final[str] = "product-strategist"
_PARALLEL: Final[tuple[str, ...]] = ("technical-researcher", "devil-advocate")
_SYNTHESIZER: Final[str] = "requirement-synthesizer"
# FR26: a valid clarification offers at least two options-with-tradeoffs for the human to pick from.
_MIN_OPTIONS: Final[int] = 2
# A synthesizer that *picks* a winner violates FR22 ("the framework never picks"). Detect
# explicit recommendation/selection statements rather than brittle bare substrings: a
# recommendation/decision heading, a "we recommend/choose/select/pick" clause, "<verb> option N",
# "option N is best/recommended/...", or a "selected/chosen/preferred/recommended option" phrase.
_AUTO_PICK_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?im)^#{1,6}\s*(?:recommendation|final\s+decision|decision|verdict)\b"),
    re.compile(r"(?i)\b(?:we|i)\s+(?:recommend|choose|select|pick)\b"),
    re.compile(r"(?i)\b(?:recommend|choose|select|pick|go\s+with)\s+option\s+\d+\b"),
    re.compile(
        r"(?i)\boption\s+\d+\s+(?:is\s+)?(?:the\s+)?"
        r"(?:best|recommended|winner|chosen|preferred|the\s+way\s+to\s+go)\b"
    ),
    re.compile(r"(?i)\b(?:selected|chosen|preferred|recommended)\s+option\b"),
)


@dataclass(frozen=True)
class AmbiguityContext:
    task_id: str
    summary: str


@dataclass(frozen=True)
class OptionsContract:
    option_count: int
    has_tradeoffs: bool
    preserves_member_concerns: bool
    has_auto_pick: bool


def clarification_id_for(context: AmbiguityContext) -> str:
    digest = hashlib.sha256(f"{context.task_id}\0{context.summary}".encode()).hexdigest()[:16]
    return f"clar-{digest}"


def detect_ambiguity_signal(repo_root: Path, *, task_id: str) -> AmbiguityContext | None:
    """Read the v1 explicit ambiguity marker for ``task_id`` (D1a seam)."""
    path = repo_root / _AMBIGUITY_SIGNALS_REL / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("ambiguity_signal_unreadable path=%s", path)
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    return AmbiguityContext(task_id=task_id, summary=summary.strip())


def parse_options_contract(text: str) -> OptionsContract:
    option_headers = re.findall(r"(?m)^## Option \d+:", text)
    has_pros = bool(re.search(r"(?m)^### Pros\b", text))
    has_cons = bool(re.search(r"(?m)^### Cons\b", text))
    has_risks = bool(re.search(r"(?m)^### Risks\b", text))
    preserves = all(
        marker in text
        for marker in ("product-strategist", "technical-researcher", "devil-advocate")
    )
    has_auto_pick = any(pattern.search(text) for pattern in _AUTO_PICK_PATTERNS)
    return OptionsContract(
        option_count=len(option_headers),
        has_tradeoffs=has_pros and has_cons and has_risks,
        preserves_member_concerns=preserves,
        has_auto_pick=has_auto_pick,
    )


def _valid_options_text(panel: PanelResult) -> str | None:
    """Return the synthesizer's options text iff the panel produced a valid no-pick contract.

    Returns ``None`` when the panel failed, produced no synthesizer output, wrote empty text,
    offered fewer than two options, or picked a winner — the caller halts gracefully (CR4.10-D1)
    and writes no ``options.md`` rather than letting a contract-violating output through (CR4.10-D2,
    FR22 "the framework never picks").
    """
    if panel.synthesizer_result is None or panel.outcome != "success":
        return None
    text = panel.synthesizer_result.agent_result.output_text
    if not text.strip():
        return None
    contract = parse_options_contract(text)
    if contract.has_auto_pick or contract.option_count < _MIN_OPTIONS:
        return None
    return text


def clarification_prompt_builder(
    specialist: Specialist,
    spec: WorkflowSpec,
    *,
    idea_text: str,
    role: Literal["primary", "parallel", "synthesizer"],
    upstream_outputs: Sequence[str] = (),
    extra_context: Mapping[str, object] = MappingProxyType({}),
    nonce: str | None = None,
) -> str:
    _ = spec, extra_context, nonce
    system = (
        f"<SYSTEM>\nYou are {specialist.frontmatter.title}. "
        f"Participate in auto-brainstorm clarification as the {role} specialist.\n</SYSTEM>"
    )
    instructions = f"<INSTRUCTIONS>\n{specialist.body}\n</INSTRUCTIONS>"
    ambiguity = f"<AMBIGUITY>\n{idea_text}\n</AMBIGUITY>"
    parts = [system, instructions, ambiguity]
    if role == "synthesizer":
        parts.append(
            "<SYNTHESIZER_CONTRACT>\n"
            "Produce options-with-tradeoffs markdown for options.md.\n"
            "Include at least 2 distinct options as '## Option N: ...' headings.\n"
            "For each option include ### Pros, ### Cons, ### Risks, and "
            "### Concerns preserved with contributions from product-strategist, "
            "technical-researcher, and devil-advocate.\n"
            "Do NOT pick or recommend a final option.\n"
            "</SYNTHESIZER_CONTRACT>"
        )
        if upstream_outputs:
            upstream = "\n---\n".join(upstream_outputs)
            parts.append(f"<UPSTREAM_OUTPUTS>\n{upstream}\n</UPSTREAM_OUTPUTS>")
    return "\n\n".join(parts)


def _clarification_paths(repo_root: Path, clar_id: str) -> tuple[Path, Path, Path]:
    clar_dir = repo_root / _CLARIFICATIONS_DIR_REL / clar_id
    return (
        clar_dir,
        clar_dir / _OPTIONS_NAME,
        clar_dir / _OPEN_CLARIFICATION_NAME,
    )


def _brainstorm_workflow_spec(options_rel: str) -> WorkflowSpec:
    globs = MappingProxyType(
        {
            _PRIMARY: (options_rel,),
            _PARALLEL[0]: (options_rel,),
            _PARALLEL[1]: (options_rel,),
            _SYNTHESIZER: (options_rel,),
        }
    )
    return WorkflowSpec(
        schema_version=1,
        name="auto-brainstorm",
        slash_command="sdlc-auto",
        primary_agent=_PRIMARY,
        parallel_agents=_PARALLEL,
        synthesizer_agent=_SYNTHESIZER,
        write_globs=globs,
    )


async def _append_auto_brainstorm_dispatched(
    journal_path: Path,
    *,
    clarification_id: str,
    task_id: str,
    correlation_id: str,
    panel_invoked: bool,
    panel_succeeded: bool,
) -> None:
    await append_with_seq_alloc(
        journal_path,
        lambda seq: JournalEntry(
            schema_version=1,
            monotonic_seq=seq,
            ts=now_rfc3339_utc_ms(),
            actor=_ACTOR,
            kind="auto_brainstorm_dispatched",
            target_id=clarification_id,
            before_hash=None,
            after_hash=_EVENT_SENTINEL,
            payload={
                "clarification_id": clarification_id,
                "task_id": task_id,
                "correlation_id": correlation_id,
                "panel_invoked": panel_invoked,
                "panel_succeeded": panel_succeeded,
                "framework_picks": False,
            },
        ),
    )


async def _write_open_clarification(
    path: Path, *, context: AmbiguityContext, clar_id: str, panel_succeeded: bool = True
) -> None:
    note = (
        ""
        if panel_succeeded
        else (
            "\n> NOTE: the auto-brainstorm panel did not produce a valid options-with-tradeoffs "
            "set (it failed or violated the no-pick contract); resolve this clarification "
            "manually.\n"
        )
    )
    body = (
        f"# Open Clarification\n\n"
        f"clarification_id: {clar_id}\n"
        f"task_id: {context.task_id}\n\n"
        f"{context.summary}\n"
        f"{note}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(atomic_write, path.resolve(), body)


async def _dispatch_brainstorm_panel(
    repo_root: Path,
    *,
    options_rel: str,
    context: AmbiguityContext,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    journal_path: Path,
    agent_runs_path: Path,
) -> PanelResult:
    spec = _brainstorm_workflow_spec(options_rel)
    observer = PanelObserver(
        slash_command="sdlc-auto",
        idea_text=context.summary,
        emit_agent_dispatched=True,
    )
    return await dispatch_panel(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=repo_root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=clarification_prompt_builder,
        hooks=build_pre_write_hook_chain(repo_root=repo_root),
        observer=observer,
        max_parallel_agents=4,
    )


async def run_auto_brainstorm(
    repo_root: Path,
    *,
    context: AmbiguityContext,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    journal_path: Path,
    agent_runs_path: Path,
    correlation_id: str,
    auto_brainstorm: bool = True,
) -> str:
    """Run (or bypass) the brainstorm panel and open a clarification directory."""
    clar_id = clarification_id_for(context)
    repo = repo_root.resolve()
    _clar_dir, options_path, open_path = _clarification_paths(repo, clar_id)
    if open_path.is_file():
        log.info("auto_brainstorm_idempotent_skip clarification_id=%s", clar_id)
        return clar_id

    _clar_dir.mkdir(parents=True, exist_ok=True)

    options_rel = str(options_path.relative_to(repo))
    panel_invoked = False
    panel_succeeded = True
    if auto_brainstorm:
        panel = await _dispatch_brainstorm_panel(
            repo,
            options_rel=options_rel,
            context=context,
            runtime=runtime,
            registry=registry,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
        )
        panel_invoked = True
        options_text = _valid_options_text(panel)
        if options_text is None:
            # CR4.10-D1/-D2: a failed or contract-violating panel must NOT crash the auto-loop.
            # Halt gracefully — record the failure and still open the clarification (so STOP fires
            # and resume stays idempotent on the existing open_clarification.md), but write no
            # options.md, because the framework must never pick or surface a degenerate set.
            panel_succeeded = False
            log.warning(
                "auto_brainstorm_panel_failed clarification_id=%s outcome=%s",
                clar_id,
                panel.outcome,
            )
        else:
            await asyncio.to_thread(atomic_write, options_path.resolve(), options_text)

    await _write_open_clarification(
        open_path, context=context, clar_id=clar_id, panel_succeeded=panel_succeeded
    )
    await _append_auto_brainstorm_dispatched(
        journal_path,
        clarification_id=clar_id,
        task_id=context.task_id,
        correlation_id=correlation_id,
        panel_invoked=panel_invoked,
        panel_succeeded=panel_succeeded,
    )
    return clar_id

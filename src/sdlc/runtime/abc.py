"""AIRuntime ABC + AgentResult contract (Decision C1, Architecture §355, §1062).

Async-only dispatch interface; no streaming in v1 (Architecture §327).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class AgentResult(BaseModel):
    """Runtime-neutral dispatch result (Architecture §355).

    frozen=True: results are immutable; callers must re-construct to modify.
    extra="forbid": adding fields is a v2-or-later schema change (Decision F3).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    output_text: str
    tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)
    # strict=True rejects bool → int coercion (True/False are int subclasses in Python).
    tokens_in: int = Field(ge=0, strict=True)
    tokens_out: int = Field(ge=0, strict=True)
    mock: bool = Field(default=False, strict=True)


class AIRuntime(ABC):
    """Runtime-neutral dispatch interface (Decision C1, Architecture §355, FR29, NFR-COMPAT-3).

    Implementations: ClaudeAIRuntime (Story 2B-1), MockAIRuntime (this story).
    Engine and dispatcher MUST import via this ABC only (boundary rule §1106).
    """

    @abstractmethod
    async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult:
        """Dispatch a prompt to the runtime; return AgentResult.

        context carries workflow_step, agent_name, tool_call_budget, and
        similar dispatch metadata. The v1 surface is intentionally open-ended;
        formal context schema is Story 2A-3.

        Raises:
            DispatchError (or subclass like MockMissError) on dispatch failure.
        """

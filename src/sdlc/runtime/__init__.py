"""AIRuntime abstraction (Architecture §826-§829, §1062, Decision C1 + C2).

v1 ships AIRuntime ABC + MockAIRuntime; ClaudeAIRuntime arrives in Story 2B-1.
"""

from __future__ import annotations

from sdlc.errors import MockMissError
from sdlc.runtime.abc import AgentResult, AIRuntime
from sdlc.runtime.mock import MockAIRuntime

# Semantic order: ABC -> return-type -> mock-impl -> mock-error.
# This order is incidentally alphabetical, so the unsorted-dunder-all rule does not fire.
# If a future story adds a name that breaks the alphabetical coincidence (e.g.
# ClaudeAIRuntime before MockAIRuntime), suppress the rule per the project convention.
__all__ = (
    "AIRuntime",
    "AgentResult",
    "MockAIRuntime",
    "MockMissError",
)

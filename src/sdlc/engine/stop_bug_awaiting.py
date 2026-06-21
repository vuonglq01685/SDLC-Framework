"""STOP trigger 7 — bug ticket awaiting-decide detection (Story 4.8)."""

from __future__ import annotations

from pathlib import Path

import yaml

from sdlc.engine.stop_triggers import StopDecision
from sdlc.state.model import State

_BUGS_DIR_REL = ".claude/state/bugs"
_AWAITING_STATE = "awaiting-decide"


class BugAwaitingDecideTrigger:
    """Detect ``.claude/state/bugs/<id>.yaml`` with ``state: awaiting-decide``."""

    trigger_id = "bug_awaiting_decide"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        bugs_dir = repo_root / _BUGS_DIR_REL
        if not bugs_dir.is_dir():
            return StopDecision(fired=False)

        for path in sorted(bugs_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                # UnicodeDecodeError is a ValueError (NOT an OSError): a non-UTF-8
                # bug file must fail soft, never crash the unguarded post-dispatch
                # check_stop sweep (auto_loop.py:286) — mirrors AgentFailedTrigger's
                # fail-open NFR-REL posture (CR4.8-P1).
                continue
            if not isinstance(raw, dict):
                continue
            if raw.get("state") != _AWAITING_STATE:
                continue
            summary = raw.get("summary")
            reason = summary if isinstance(summary, str) and summary.strip() else f"bug {path.stem}"
            return StopDecision(
                fired=True,
                trigger=self.trigger_id,
                target=path.stem,
                reason=reason,
            )

        return StopDecision(fired=False)

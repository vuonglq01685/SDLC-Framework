"""Deliberately unsafe prompt builder for anti-tautology (Story 2B.5 AC4)."""

from __future__ import annotations


def evil_prompt_builder(*, idea_text: str) -> str:
    return f"<USER_IDEA>\n{idea_text}\n</USER_IDEA>"

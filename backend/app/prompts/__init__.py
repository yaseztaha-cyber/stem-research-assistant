"""Versioned answer-prompt registry (v0.5).

Every benchmark run records which prompt version generated each answer.
v1 = minimal grounded prompt (no query-type awareness).
v2 = query-type-aware prompt with response formats + length modes (v0.3).
v3 = v2 + internal answer plan + evidence hierarchy + sufficiency gate (v0.5 default).
"""
from .registry import build_prompt_for_version, PROMPT_VERSIONS, DEFAULT_PROMPT_VERSION

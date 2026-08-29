#!/usr/bin/env python3
"""Source: speedyapply/2027-AI-College-Jobs, international intern table."""
from . import common

NAME = "speedyapply-intern-intl"
URL = "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main/INTERN_INTL.md"
FIXTURE = "speedyapply-intern-intl.md"


def parse(markdown: str, fetched_at: str) -> list[dict]:
    return common.parse_markdown_table(markdown, NAME, fetched_at)

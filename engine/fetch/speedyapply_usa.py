#!/usr/bin/env python3
"""Source: speedyapply/2027-AI-College-Jobs, US intern table (README.md)."""
from . import common

NAME = "speedyapply-intern-usa"
URL = "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main/README.md"
FIXTURE = "speedyapply-intern-usa.md"


def parse(markdown: str, fetched_at: str) -> list[dict]:
    return common.parse_markdown_table(markdown, NAME, fetched_at)

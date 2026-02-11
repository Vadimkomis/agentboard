"""PM Agent — triages tickets using Claude Sonnet with structured JSON output."""

import json
import re

import httpx
import structlog

from src.models.project import Project
from src.models.ticket import Ticket
from src.schemas.ticket import TriageResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert PM Agent for AgentBoard, an AI-powered project management system.
Your job is to triage development tickets and route them to the right AI coding agent.

Given a ticket title and description, plus context about the project, you must produce a JSON classification.

## Agent Types
- backend: API endpoints, database work, server logic
- frontend: UI components, pages, styling, client-side logic
- mobile: Mobile-specific features (React Native, Flutter)
- devops: CI/CD, Docker, infrastructure, deployment
- qa: Test writing, test infrastructure, quality assurance
- fullstack: Changes spanning both frontend and backend
- docs: Documentation, README updates, API docs

## Runtimes
- claude: Best for multi-file changes, architectural work, complex refactoring, vague requirements
- codex: Best for single-file fixes, boilerplate, test generation, well-scoped bugs

## Priority Levels
- critical: Production broken, security vulnerability
- high: Blocks other work, important feature
- medium: Normal feature work, improvements
- low: Nice-to-have, minor fixes

## Complexity
- trivial: One-line change, typo fix
- simple: Single file, straightforward logic
- medium: Multiple files, moderate logic
- complex: Architectural changes, many files, careful design needed

Respond with ONLY a JSON object matching this schema:
{
  "agent_type": "backend|frontend|mobile|devops|qa|fullstack|docs",
  "runtime": "claude|codex",
  "priority": "critical|high|medium|low",
  "complexity": "trivial|simple|medium|complex",
  "branch_name": "feature/short-kebab-case-name",
  "refined_description": "A clearer, more detailed version of what needs to be done",
  "acceptance_criteria": "Bullet-pointed list of what 'done' looks like",
  "context_files": ["list", "of", "relevant/file/paths"],
  "reasoning": "Brief explanation of your classification decisions"
}"""


async def triage_ticket(
    ticket: Ticket,
    project: Project,
    anthropic_key: str,
    repo_files: list[str] | None = None,
) -> TriageResult:
    user_content = f"""## Ticket
Title: {ticket.title}
Description: {ticket.description or "No description provided"}

## Project
Repository: {project.repo_full_name}
Default branch: {project.default_branch}
"""
    if repo_files:
        user_content += f"\n## Repository file tree (top-level)\n{chr(10).join(repo_files[:200])}\n"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            },
        )
        resp.raise_for_status()
        data = resp.json()

    text = data["content"][0]["text"]
    # Extract JSON from the response (handle markdown code blocks)
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        raise ValueError(f"Could not parse triage JSON from response: {text[:200]}")

    parsed = json.loads(json_match.group())
    return TriageResult(**parsed)

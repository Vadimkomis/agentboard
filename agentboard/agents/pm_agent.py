"""PM Agent — story refinement, decomposition, diff analysis, bug triage.

The PM agent is conversational during DRAFTING and acts headlessly during ENGINEERING.
All LLM calls go through the CLI subprocess (claude or codex).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from agentboard.core.models import Story, StoryMessage, Ticket

REFINEMENT_SYSTEM_PROMPT = """\
You are a senior product manager helping a developer refine their story (feature/product idea).

Your responsibilities during refinement:
1. Ask 2-3 sharp clarifying questions to deepen understanding
2. ALWAYS ask about the GTM (Go-To-Market) strategy if the user hasn't addressed it:
   "How will users find this? What's the growth lever — SEO, paid, community, product-led?
    How do you monetize or distribute?"
3. Push for specificity on scope — what's in and what's out?
4. Identify risks and ambiguities early
5. Refuse to suggest finalization until all 5 PRD sections have substance:
   Problem, Solution, Scope, Acceptance Criteria, GTM

IMPORTANT:
- Do NOT decompose into tickets yet — that happens only on explicit finalize
- Keep responses conversational and concise (under 200 words)
- If all 5 sections are covered, tell the user they can press [f] to finalize

PRD Sections required:
- Problem: What pain, for whom
- Solution: What we're building and why this approach
- Scope: In / out of scope (be specific)
- Acceptance Criteria: How we know it works
- GTM: How to scale / promote / sell (mandatory — refuse to finalize without it)
"""


DECOMPOSITION_SYSTEM_PROMPT = """\
You are a senior product manager decomposing a refined PRD into engineering tickets.

Output ONLY valid JSON. No explanation, no markdown, no preamble.

Required output schema:
{
  "engineering_tickets": [
    {
      "index": 0,
      "title": "string",
      "prd_anchor": "string — e.g. checkout.payment-methods",
      "agent_type": "backend|frontend|mobile|devops|qa|fullstack|docs",
      "runtime": "claude|codex",
      "priority": "high|medium|low",
      "complexity": "high|medium|low",
      "branch_name": "feature/...",
      "refined_description": "string — precise, implementation-ready",
      "acceptance_criteria": "string",
      "context_files": [],
      "depends_on": [],
      "reasoning": "string — why this agent type and runtime"
    }
  ],
  "marketing_ticket": {
    "title": "string",
    "prd_anchor": "gtm",
    "gtm_context": "string — summary of GTM strategy",
    "output_file": "LAUNCH.md"
  }
}

Routing heuristic:
- Claude: multi-file changes, architectural reasoning, complex refactoring, vague requirements, CI/CD
- Codex: single-file fixes, boilerplate, test generation, docs, well-scoped bugs

Keep tickets small and independently deployable. Maximum 8 engineering tickets per story.
"""


DIFF_ANALYSIS_SYSTEM_PROMPT = """\
You are analyzing a PRD change to determine which engineering tickets are now stale.

You will receive:
1. The original PRD
2. The updated PRD
3. A list of existing tickets with their prd_anchor values

Output ONLY valid JSON:
{
  "stale_ticket_indices": [0, 2],
  "changed_sections": ["checkout.payment-methods"],
  "summary": "Brief description of what changed and why tickets are stale"
}

Return an empty list if no tickets are affected.
"""


BUG_TRIAGE_SYSTEM_PROMPT = """\
You are triaging a bug report during testing. Create a focused bug-fix ticket.

Output ONLY valid JSON:
{
  "title": "Fix: [specific bug]",
  "prd_anchor": "bug.[area]",
  "agent_type": "backend|frontend|fullstack|qa",
  "runtime": "claude|codex",
  "priority": "high|medium|low",
  "complexity": "high|medium|low",
  "branch_name": "fix/...",
  "refined_description": "Steps to reproduce + expected vs actual + fix approach",
  "acceptance_criteria": "What must be true for this bug to be considered fixed",
  "context_files": [],
  "depends_on": []
}
"""


@dataclass
class DecomposedStory:
    engineering_tickets: list[dict]
    marketing_ticket: dict


@dataclass
class DiffAnalysis:
    stale_ticket_indices: list[int]
    changed_sections: list[str]
    summary: str


class PMAgent:
    """Conversational PM agent for story refinement and decomposition."""

    def __init__(self, llm_client: object) -> None:
        self._client = llm_client

    def _build_prd_summary(self, story: Story) -> str:
        sections = []
        if story.prd_problem:
            sections.append(f"**Problem:** {story.prd_problem}")
        if story.prd_solution:
            sections.append(f"**Solution:** {story.prd_solution}")
        if story.prd_scope:
            sections.append(f"**Scope:** {story.prd_scope}")
        if story.prd_acceptance:
            sections.append(f"**Acceptance Criteria:** {story.prd_acceptance}")
        if story.prd_gtm:
            sections.append(f"**GTM:** {story.prd_gtm}")
        return "\n\n".join(sections) if sections else "(No PRD content yet)"

    async def refine(
        self,
        story: Story,
        user_message: str,
        history: list[StoryMessage],
        on_token: Callable[[str], None],
    ) -> AsyncIterator[str]:
        """Stream a PM response to the user's message during DRAFTING."""
        system = REFINEMENT_SYSTEM_PROMPT

        messages: list[dict[str, str]] = []

        # Include PRD state as context in first message
        if not history:
            prd_context = self._build_prd_summary(story)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Story title: {story.title}\n\nCurrent PRD:\n{prd_context}\n\n"
                        f"User message: {user_message}"
                    ),
                }
            )
        else:
            # Pass full conversation history
            for msg in history:
                messages.append(msg.to_dict())
            messages.append({"role": "user", "content": user_message})

        return self._client.stream(system, messages, on_token)  # type: ignore[return-value]

    async def decompose(self, story: Story) -> DecomposedStory:
        """Decompose a finalized PRD into engineering + marketing tickets."""
        prd_full = self._build_prd_summary(story)
        user_msg = (
            f"Story title: {story.title}\n\n"
            f"Full PRD:\n{prd_full}\n\n"
            "Please decompose this into engineering tickets and a marketing ticket."
        )

        response = await self._client.complete(  # type: ignore[call-arg]
            DECOMPOSITION_SYSTEM_PROMPT,
            [{"role": "user", "content": user_msg}],
        )

        parsed = _parse_json_response(response)
        return DecomposedStory(
            engineering_tickets=parsed.get("engineering_tickets", []),
            marketing_ticket=parsed.get("marketing_ticket", {}),
        )

    async def analyze_diff(
        self,
        story: Story,
        original_prd: str,
        updated_prd: str,
        existing_tickets: list[Ticket],
    ) -> DiffAnalysis:
        """Determine which tickets are stale after a PRD edit."""
        ticket_summary = json.dumps(
            [
                {"index": t.ticket_index, "title": t.title, "prd_anchor": t.prd_anchor}
                for t in existing_tickets
            ],
            indent=2,
        )

        user_msg = (
            f"Original PRD:\n{original_prd}\n\n"
            f"Updated PRD:\n{updated_prd}\n\n"
            f"Existing tickets:\n{ticket_summary}"
        )

        response = await self._client.complete(  # type: ignore[call-arg]
            DIFF_ANALYSIS_SYSTEM_PROMPT,
            [{"role": "user", "content": user_msg}],
        )

        parsed = _parse_json_response(response)
        return DiffAnalysis(
            stale_ticket_indices=parsed.get("stale_ticket_indices", []),
            changed_sections=parsed.get("changed_sections", []),
            summary=parsed.get("summary", ""),
        )

    async def triage_bug(
        self,
        story: Story,
        bug_description: str,
    ) -> dict:
        """Create a bug-fix ticket from a user bug report."""
        prd_summary = self._build_prd_summary(story)
        user_msg = (
            f"Story: {story.title}\n\nPRD context:\n{prd_summary}\n\nBug report:\n{bug_description}"
        )

        response = await self._client.complete(  # type: ignore[call-arg]
            BUG_TRIAGE_SYSTEM_PROMPT,
            [{"role": "user", "content": user_msg}],
        )

        return _parse_json_response(response)


def _parse_json_response(text: str) -> dict:
    """Extract and parse JSON from LLM response (handles markdown code blocks)."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in markdown
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } block
    match2 = re.search(r"\{.*\}", text, re.DOTALL)
    if match2:
        try:
            return json.loads(match2.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:500]}")

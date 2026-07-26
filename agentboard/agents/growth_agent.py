"""Growth Agent — GTM strategy conversation + LAUNCH.md generation.

Runs in parallel with the PM agent from story creation.
Conversational during DRAFTING; produces LAUNCH.md on finalize.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from agentboard.core.models import GrowthMessage, Story
from agentboard.llm.client import LLMClient

GROWTH_REFINEMENT_SYSTEM_PROMPT = """\
You are a growth strategist and product marketer specialized in developer tools and SaaS.

Your role is to help the user think deeply about distribution, positioning, and launch strategy.
You run in PARALLEL with the PM agent — you focus exclusively on growth and GTM.

Your conversation style:
- Ask sharp, specific questions that surface insights the user didn't know they had
- Challenge vague answers: "How exactly will users discover this?"
- Think about the full journey: discover → try → buy → tell others
- Push for specificity on channels, timing, and mechanics

In each response, ask 1-2 focused questions. Don't overwhelm.

Key areas to explore:
1. ICP (Ideal Customer Profile): Who is the buyer? What's their job-to-be-done?
2. Discovery: How will they find this? (SEO, paid, community, product-led, partnerships, word of mouth)
3. Growth lever: What's the mechanism for organic spread?
4. Pricing: Model and rationale. Why this price point?
5. Launch sequence: Soft launch → beta → public. Timeline?
6. Top 3 distribution bets and why

IMPORTANT:
- Keep responses concise (under 150 words)
- Be opinionated — share what works for products like this
- When growth strategy is sufficiently defined, tell user they can press [g] to generate LAUNCH.md
"""


LAUNCH_MD_GENERATION_SYSTEM_PROMPT = """\
You are generating a LAUNCH.md file based on a growth strategy conversation.

Write actionable, specific content. Avoid generic advice.
Output raw Markdown only — no explanation, no preamble.

LAUNCH.md must follow this exact structure:

# LAUNCH.md — {story_title}

## Positioning
"For [ICP], [product] is the [category] that [key differentiator]."

## Target Audience
### Ideal Customer Profile
[Specific description]

### Jobs-to-be-Done
[What they hire this product to do]

### Pain Points
[Top 3 specific pains]

## Distribution Channels
[Top 3-5 channels with specific tactics, owner, and why this channel]

## Launch Copy

### One-Liner
[One sentence]

### Tweet Draft
[Draft tweet — under 280 chars]

### Hacker News Post Title
[Compelling HN title]

### Product Hunt Tagline
[Under 60 chars]

## Pricing
### Model
[Free/freemium/paid tiers]

### Rationale
[Why this pricing]

## 30-Day Launch Sequence
### Week 1: Soft Launch
### Week 2: Community
### Week 3: Content
### Week 4: Public Launch

## Open Questions
[Unresolved decisions that need answers before launch]
"""


class GrowthAgent:
    """Conversational growth agent — GTM refinement and LAUNCH.md generation."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    async def refine(
        self,
        story: Story,
        user_message: str,
        history: list[GrowthMessage],
        on_token: Callable[[str], None],
    ) -> AsyncIterator[str]:
        """Stream a growth strategy response during DRAFTING."""
        messages: list[dict[str, str]] = []

        if not history:
            # First message — seed with story context
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Story title: {story.title}\n\n"
                        f"Problem: {story.prd_problem or '(not defined yet)'}\n\n"
                        f"Solution: {story.prd_solution or '(not defined yet)'}\n\n"
                        f"GTM so far: {story.prd_gtm or '(not defined yet)'}\n\n"
                        f"User message: {user_message}"
                    ),
                }
            )
        else:
            for msg in history:
                messages.append(msg.to_dict())
            messages.append({"role": "user", "content": user_message})

        return self._client.stream(
            GROWTH_REFINEMENT_SYSTEM_PROMPT,
            messages,
            on_token,
        )

    async def generate_launch_md(
        self,
        story: Story,
        conversation_history: list[GrowthMessage],
    ) -> str:
        """Generate LAUNCH.md content from the growth conversation.

        Returns the full markdown content to be committed to the repo.
        """
        # Summarize the conversation into context
        conversation_text = "\n".join(
            f"{msg.role.value.upper()}: {msg.content}" for msg in conversation_history
        )

        system = LAUNCH_MD_GENERATION_SYSTEM_PROMPT.replace("{story_title}", story.title)
        user_msg = (
            f"Story title: {story.title}\n\n"
            f"Full PRD:\n"
            f"Problem: {story.prd_problem or ''}\n"
            f"Solution: {story.prd_solution or ''}\n"
            f"Scope: {story.prd_scope or ''}\n"
            f"Acceptance Criteria: {story.prd_acceptance or ''}\n"
            f"GTM: {story.prd_gtm or ''}\n\n"
            f"Growth Strategy Conversation:\n{conversation_text}"
        )

        return await self._client.complete(
            system,
            [{"role": "user", "content": user_msg}],
        )

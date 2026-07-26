"""Engineering Runner — headless execution of engineering tickets.

Clones the repo, creates a branch, invokes claude or codex CLI,
commits the result, creates a PR, and returns the PR URL.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from agentboard.core.config import Config
from agentboard.core.models import Execution, Runtime, Story, Ticket
from agentboard.llm.claude_cli import ClaudeCLIClient
from agentboard.llm.codex_cli import CodexCLIClient

ENGINEERING_SYSTEM_PROMPT_TEMPLATE = """\
You are a {agent_type} engineer working on a story: "{story_title}".

Your task:
{refined_description}

Acceptance criteria:
{acceptance_criteria}

PRD context:
Problem: {prd_problem}
Solution: {prd_solution}

Standards:
- Follow the existing code conventions in this repository
- Run the project's linter before finishing (check pyproject.toml, package.json, etc.)
- Write tests for all new code
- Make atomic commits with clear messages
- Do NOT modify unrelated files
- If you are unsure about scope, implement the minimal version that satisfies the acceptance criteria

When done:
- Ensure all changes are committed
- Print "TASK_COMPLETE" on the last line
"""


class EngineeringRunner:
    """Executes a ticket by cloning the repo, running an agent, and creating a PR."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def _get_client(self, runtime: Runtime) -> ClaudeCLIClient | CodexCLIClient:
        if runtime == Runtime.claude:
            return ClaudeCLIClient(self._config.claude_cli_path)
        return CodexCLIClient(self._config.codex_cli_path)

    def _workspace_path(self, execution_id: int) -> Path:
        return self._config.workspace_dir / str(execution_id)

    async def run(
        self,
        story: Story,
        ticket: Ticket,
        execution: Execution,
        on_output: Callable[[str], None],
    ) -> str | None:
        """Execute a ticket. Returns PR URL on success, None on failure.

        Raises RuntimeError on fatal errors.
        """
        workspace = self._workspace_path(execution.id)
        workspace.mkdir(parents=True, exist_ok=True)

        try:
            repo_url = story.repo_url
            if not repo_url:
                raise RuntimeError("Story has no repo_url — cannot clone")

            # Clone repo
            on_output(f"[runner] Cloning {repo_url}...\n")
            await _run_cmd(
                ["git", "clone", repo_url, str(workspace)],
                cwd=None,
            )

            # Create and checkout branch
            branch = ticket.branch_name or f"feature/ticket-{ticket.id}"
            on_output(f"[runner] Creating branch {branch}...\n")
            await _run_cmd(["git", "checkout", "-b", branch], cwd=str(workspace))

            # Build task prompt
            system = ENGINEERING_SYSTEM_PROMPT_TEMPLATE.format(
                agent_type=ticket.agent_type.value,
                story_title=story.title,
                refined_description=ticket.description or ticket.title,
                acceptance_criteria=ticket.acceptance_criteria or "Implement as described.",
                prd_problem=story.prd_problem or "",
                prd_solution=story.prd_solution or "",
            )

            task = (
                f"Branch: {branch}\n"
                f"Ticket #{ticket.ticket_index}: {ticket.title}\n\n"
                f"{ticket.description or ''}"
            )

            # Run the agent
            on_output(f"[runner] Starting {ticket.runtime.value} agent...\n")
            client = self._get_client(ticket.runtime)
            await client.run_agent(
                system=system,
                task=task,
                workspace=str(workspace),
                on_output=on_output,
            )

            # Check for uncommitted changes
            status_out = await _run_cmd(["git", "status", "--porcelain"], cwd=str(workspace))
            if status_out.strip():
                on_output("[runner] Committing changes...\n")
                await _run_cmd(["git", "add", "-A"], cwd=str(workspace))
                commit_msg = f"feat: {ticket.title}\n\nTicket #{ticket.id} — {story.title}"
                await _run_cmd(
                    ["git", "commit", "-m", commit_msg],
                    cwd=str(workspace),
                )

            # Push branch
            on_output(f"[runner] Pushing {branch}...\n")
            await _run_cmd(
                ["git", "push", "origin", branch],
                cwd=str(workspace),
            )

            # Create PR (requires GitHub token)
            pr_url: str | None = None
            if self._config.github_token:
                pr_url = await self._create_pr(
                    workspace=str(workspace),
                    story=story,
                    ticket=ticket,
                    branch=branch,
                    on_output=on_output,
                )

            on_output(f"[runner] Done! PR: {pr_url or '(no GitHub token)'}\n")
            return pr_url

        finally:
            # Clean up workspace
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)

    async def _create_pr(
        self,
        workspace: str,
        story: Story,
        ticket: Ticket,
        branch: str,
        on_output: Callable[[str], None],
    ) -> str | None:
        """Create a GitHub PR using the gh CLI."""
        title = f"{ticket.title} (AgentBoard)"
        body = (
            f"## Story: {story.title}\n\n"
            f"### Ticket\n{ticket.description or ticket.title}\n\n"
            f"### Acceptance Criteria\n{ticket.acceptance_criteria or 'See ticket.'}\n\n"
            f"---\n*Auto-generated by AgentBoard*"
        )
        try:
            env = {"GH_TOKEN": self._config.github_token or ""}
            out = await _run_cmd(
                ["gh", "pr", "create", "--title", title, "--body", body, "--head", branch],
                cwd=workspace,
                extra_env=env,
            )
            # gh pr create outputs the PR URL on the last line
            pr_url = out.strip().split("\n")[-1].strip()
            on_output(f"[runner] PR created: {pr_url}\n")
            return pr_url
        except Exception as e:
            on_output(f"[runner] PR creation failed: {e}\n")
            return None


async def _run_cmd(
    cmd: list[str],
    cwd: str | None,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Run a shell command, returning stdout. Raises on non-zero exit."""
    import os

    env = {**os.environ, **(extra_env or {})}
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Command {cmd[0]!r} failed (exit {proc.returncode}): {err}")
    return stdout.decode()

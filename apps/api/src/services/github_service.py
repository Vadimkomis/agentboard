"""GitHub API service — branch creation, pull requests, repo tree."""

import httpx

GITHUB_API = "https://api.github.com"


def _headers(github_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_default_branch_sha(
    repo_full_name: str, branch: str, github_token: str
) -> str:
    url = f"{GITHUB_API}/repos/{repo_full_name}/git/ref/heads/{branch}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(github_token))
        resp.raise_for_status()
        return resp.json()["object"]["sha"]


async def create_branch(
    repo_full_name: str, branch_name: str, base_branch: str, github_token: str
) -> dict:
    sha = await get_default_branch_sha(repo_full_name, base_branch, github_token)
    url = f"{GITHUB_API}/repos/{repo_full_name}/git/refs"
    payload = {"ref": f"refs/heads/{branch_name}", "sha": sha}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=_headers(github_token))
        resp.raise_for_status()
        return resp.json()


async def create_pull_request(
    repo_full_name: str,
    branch_name: str,
    base_branch: str,
    title: str,
    body: str,
    github_token: str,
) -> dict:
    url = f"{GITHUB_API}/repos/{repo_full_name}/pulls"
    payload = {"title": title, "body": body, "head": branch_name, "base": base_branch}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=_headers(github_token))
        resp.raise_for_status()
        return resp.json()


async def list_repo_tree(
    repo_full_name: str, branch: str, github_token: str
) -> list[str]:
    url = f"{GITHUB_API}/repos/{repo_full_name}/git/trees/{branch}?recursive=1"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(github_token))
        resp.raise_for_status()
        tree = resp.json().get("tree", [])
        return [item["path"] for item in tree if item["type"] == "blob"]

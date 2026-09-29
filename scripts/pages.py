import json
import os
from typing import Dict

import requests
from github import Github, InputGitTreeElement
from github.GithubException import UnknownObjectException
from rich.console import Console

console = Console()


def load_gh_pages_tokenlist(repo_name: str, file_path: str) -> Dict:
    gh_pages_url = f"https://{repo_name.split('/')[0]}.github.io/{repo_name.split('/')[1]}/{file_path}"
    try:
        # A 404 here is an expected, recoverable state: the branch has not been
        # published yet, so there is simply no token list to merge against.
        # Every other RequestException (timeout, 5xx, TLS) is a genuine failure
        # and is re-raised rather than being reported as "no existing list",
        # which would silently discard previously published tokens on the next
        # generation run.
        response = requests.get(gh_pages_url, timeout=30)
        if response.status_code == 404:
            console.print(
                f"[warning]No published tokenlist at {gh_pages_url}; starting from an empty list.[/warning]"
            )
            return {}
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Failed to load the existing tokenlist from {gh_pages_url}: {exc}. "
            "Refusing to continue, because regenerating without the previous list "
            "would drop every token that is not re-discovered from the images folder."
        ) from exc


def upload_to_github_pages(content: Dict, repo_name: str, file_path: str):
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN is not set in environment variables")

    g = Github(github_token)
    repo = g.get_repo(repo_name)

    # Get the gh-pages branch. A missing branch raises UnknownObjectException,
    # which we handle by creating it; every other failure (auth, rate limit,
    # network) must propagate instead of being silently swallowed by a bare
    # `except:`, which previously turned a hard failure into a confusing
    # "branch does not exist" path.
    try:
        branch = repo.get_branch("gh-pages")
    except UnknownObjectException:
        # If gh-pages branch doesn't exist, create it from the default branch
        sb = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref="refs/heads/gh-pages", sha=sb.commit.sha)
        branch = repo.get_branch("gh-pages")

    # Create blob
    blob = repo.create_git_blob(json.dumps(content, indent=2), "utf-8")
    element = InputGitTreeElement(path=file_path, mode="100644", type="blob", sha=blob.sha)

    # Create tree and commit
    head_sha = branch.commit.sha
    base_tree = repo.get_git_tree(sha=head_sha)
    tree = repo.create_git_tree([element], base_tree)
    parent = repo.get_git_commit(sha=head_sha)
    commit = repo.create_git_commit("Update tokenlist", tree, [parent])
    branch_ref = repo.get_git_ref("heads/gh-pages")
    branch_ref.edit(sha=commit.sha)

    return f"https://{repo.owner.login}.github.io/{repo.name}/{file_path}"

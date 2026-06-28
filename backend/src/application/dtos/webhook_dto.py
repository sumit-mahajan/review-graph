from dataclasses import dataclass
from enum import StrEnum


class WebhookEventType(StrEnum):
    PULL_REQUEST = "pull_request"
    INSTALLATION = "installation"
    INSTALLATION_REPOSITORIES = "installation_repositories"
    PING = "ping"
    OTHER = "other"


class PullRequestAction(StrEnum):
    OPENED = "opened"
    SYNCHRONIZE = "synchronize"
    REOPENED = "reopened"
    CLOSED = "closed"
    OTHER = "other"


@dataclass(frozen=True)
class PullRequestWebhookData:
    action: PullRequestAction
    installation_id: int
    repository_github_id: int
    repository_owner: str
    repository_name: str
    repository_full_name: str
    repository_default_branch: str
    repository_language: str | None
    pr_number: int
    pr_title: str
    pr_author: str
    pr_url: str
    base_sha: str
    head_sha: str


@dataclass(frozen=True)
class InstallationWebhookData:
    action: str
    installation_id: int
    account_login: str
    account_type: str
    account_avatar_url: str | None


@dataclass(frozen=True)
class WebhookResult:
    accepted: bool
    job_enqueued: bool
    message: str

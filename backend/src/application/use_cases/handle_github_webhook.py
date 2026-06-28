from typing import Any

import structlog

from application.dtos.webhook_dto import (
    InstallationWebhookData,
    PullRequestAction,
    PullRequestWebhookData,
    WebhookEventType,
    WebhookResult,
)
from application.use_cases.enqueue_embedding_cleanup import EnqueueEmbeddingCleanupUseCase
from application.use_cases.start_review import StartReviewUseCase
from application.use_cases.sync_installation import SyncInstallationUseCase
from domain.errors import EntityNotFoundError

logger = structlog.get_logger()

REVIEW_ACTIONS = {
    PullRequestAction.OPENED,
    PullRequestAction.SYNCHRONIZE,
    PullRequestAction.REOPENED,
}


class HandleGithubWebhookUseCase:
    """Route GitHub webhook events to the appropriate handler."""

    def __init__(
        self,
        start_review: StartReviewUseCase,
        enqueue_cleanup: EnqueueEmbeddingCleanupUseCase,
        sync_installation: SyncInstallationUseCase,
    ) -> None:
        self._start_review = start_review
        self._enqueue_cleanup = enqueue_cleanup
        self._sync_installation = sync_installation

    async def execute(self, event_type: str, payload: dict[str, Any]) -> WebhookResult:
        parsed_event = _parse_event_type(event_type)

        if parsed_event == WebhookEventType.PING:
            return WebhookResult(accepted=True, job_enqueued=False, message="pong")

        if parsed_event in {
            WebhookEventType.INSTALLATION,
            WebhookEventType.INSTALLATION_REPOSITORIES,
        }:
            data = _parse_installation_payload(payload)
            if data.action in {"created", "added"}:
                await self._sync_installation.execute(
                    installation_id=data.installation_id,
                    account_login=data.account_login,
                    account_type=data.account_type,
                    account_avatar_url=data.account_avatar_url,
                )
            return WebhookResult(
                accepted=True,
                job_enqueued=False,
                message="installation processed",
            )

        if parsed_event == WebhookEventType.PULL_REQUEST:
            return await self._handle_pull_request(payload)

        await logger.ainfo("webhook_ignored", event_type=event_type)
        return WebhookResult(accepted=True, job_enqueued=False, message="event ignored")

    async def _handle_pull_request(self, payload: dict[str, Any]) -> WebhookResult:
        data = _parse_pull_request_payload(payload)

        if data.action == PullRequestAction.CLOSED:
            try:
                await self._enqueue_cleanup.execute(
                    repository_github_id=data.repository_github_id,
                    head_sha=data.head_sha,
                    pr_number=data.pr_number,
                )
            except EntityNotFoundError:
                await logger.awarning(
                    "embedding_cleanup_skipped_unknown_repo",
                    repo_github_id=data.repository_github_id,
                )
                return WebhookResult(
                    accepted=True,
                    job_enqueued=False,
                    message="repository not registered",
                )
            return WebhookResult(
                accepted=True,
                job_enqueued=True,
                message="embedding cleanup enqueued",
            )

        if data.action in REVIEW_ACTIONS:
            try:
                _job, enqueued = await self._start_review.execute(
                    repository_github_id=data.repository_github_id,
                    pr_number=data.pr_number,
                    pr_title=data.pr_title,
                    pr_author=data.pr_author,
                    pr_url=data.pr_url,
                    base_sha=data.base_sha,
                    head_sha=data.head_sha,
                )
            except EntityNotFoundError:
                await logger.awarning(
                    "review_skipped_unknown_repo",
                    repo_github_id=data.repository_github_id,
                )
                return WebhookResult(
                    accepted=True,
                    job_enqueued=False,
                    message="repository not registered",
                )

            return WebhookResult(
                accepted=True,
                job_enqueued=enqueued,
                message="review job enqueued" if enqueued else "review job idempotent skip",
            )

        return WebhookResult(accepted=True, job_enqueued=False, message="pr action ignored")


def _parse_event_type(event_type: str) -> WebhookEventType:
    try:
        return WebhookEventType(event_type)
    except ValueError:
        return WebhookEventType.OTHER


def _parse_pull_request_payload(payload: dict[str, Any]) -> PullRequestWebhookData:
    action_raw = payload.get("action", "")
    try:
        action = PullRequestAction(action_raw)
    except ValueError:
        action = PullRequestAction.OTHER

    installation = payload.get("installation") or {}
    repository = payload.get("repository") or {}
    pull_request = payload.get("pull_request") or {}
    user = pull_request.get("user") or {}
    base = pull_request.get("base") or {}
    head = pull_request.get("head") or {}
    owner = repository.get("owner") or {}

    return PullRequestWebhookData(
        action=action,
        installation_id=int(installation.get("id", 0)),
        repository_github_id=int(repository.get("id", 0)),
        repository_owner=str(owner.get("login", "")),
        repository_name=str(repository.get("name", "")),
        repository_full_name=str(repository.get("full_name", "")),
        repository_default_branch=str(repository.get("default_branch", "main")),
        repository_language=repository.get("language"),
        pr_number=int(pull_request.get("number", 0)),
        pr_title=str(pull_request.get("title", "")),
        pr_author=str(user.get("login", "")),
        pr_url=str(pull_request.get("html_url", "")),
        base_sha=str(base.get("sha", "")),
        head_sha=str(head.get("sha", "")),
    )


def _parse_installation_payload(payload: dict[str, Any]) -> InstallationWebhookData:
    action = str(payload.get("action", ""))
    installation = payload.get("installation") or {}
    account = installation.get("account") or {}

    account_type = str(account.get("type", "User")).lower()
    normalized_type = "org" if account_type == "organization" else "user"

    return InstallationWebhookData(
        action=action,
        installation_id=int(installation.get("id", 0)),
        account_login=str(account.get("login", "")),
        account_type=normalized_type,
        account_avatar_url=account.get("avatar_url"),
    )

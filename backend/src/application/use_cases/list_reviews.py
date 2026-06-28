from uuid import UUID

from api.schemas.dashboard import PaginatedResponse, ReviewDetailDTO
from application.dtos.dashboard_mappers import to_review_detail_dto, to_review_summary_dto
from domain.entities.review import Review  # noqa: TC001
from domain.entities.user import User
from domain.errors import EntityNotFoundError, ForbiddenError
from domain.repositories.i_repo_repository import IRepoRepository
from domain.repositories.i_review_repository import IReviewRepository


class ListReviewsUseCase:
    def __init__(
        self,
        review_repo: IReviewRepository,
        repo_repo: IRepoRepository,
    ) -> None:

        self._review_repo = review_repo

        self._repo_repo = repo_repo

    async def execute(
        self,
        user: User,
        *,
        repo_id: UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse:

        if repo_id is not None:
            repo = await self._repo_repo.get_by_id(repo_id)

            if repo is None:
                raise EntityNotFoundError(f"Repository {repo_id} not found")

            if repo.owner != user.login:
                raise ForbiddenError(
                    f"User '{user.login}' cannot access reviews for '{repo.full_name}'"
                )

            items, total = await self._review_repo.list_by_repo(repo_id, page=page, limit=limit)

        else:
            repos = await self._repo_repo.list_accessible_for_login(user.login)

            all_items: list[Review] = []

            for repo in repos:
                repo_items, _ = await self._review_repo.list_by_repo(repo.id, page=1, limit=1000)

                all_items.extend(repo_items)

            all_items.sort(key=lambda r: r.created_at, reverse=True)

            total = len(all_items)

            offset = (page - 1) * limit

            items = all_items[offset : offset + limit]

        return PaginatedResponse(
            items=[to_review_summary_dto(r) for r in items],
            total=total,
            page=page,
            limit=limit,
            has_next=(page * limit) < total,
        )


class GetReviewUseCase:
    def __init__(
        self,
        review_repo: IReviewRepository,
        repo_repo: IRepoRepository,
    ) -> None:

        self._review_repo = review_repo

        self._repo_repo = repo_repo

    async def execute(self, user: User, review_id: UUID) -> ReviewDetailDTO:

        review = await self._review_repo.get_by_id(review_id)

        if review is None:
            raise EntityNotFoundError(f"Review {review_id} not found")

        repo = await self._repo_repo.get_by_id(review.repository_id)

        if repo is None or repo.owner != user.login:
            raise ForbiddenError(f"User '{user.login}' cannot access review {review_id}")

        return to_review_detail_dto(review)

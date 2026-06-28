from uuid import UUID

from api.schemas.dashboard import JobStatusDTO
from application.dtos.dashboard_mappers import to_job_status_dto
from domain.entities.user import User
from domain.errors import EntityNotFoundError, ForbiddenError
from domain.repositories.i_job_repository import IJobRepository
from domain.repositories.i_repo_repository import IRepoRepository


class GetJobUseCase:
    def __init__(
        self,
        job_repo: IJobRepository,
        repo_repo: IRepoRepository,
    ) -> None:
        self._job_repo = job_repo
        self._repo_repo = repo_repo

    async def execute(self, user: User, job_id: UUID) -> JobStatusDTO:
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            raise EntityNotFoundError(f"Job {job_id} not found")

        repo = await self._repo_repo.get_by_id(job.repository_id)
        if repo is None or repo.owner != user.login:
            raise ForbiddenError(f"User '{user.login}' cannot access job {job_id}")

        return to_job_status_dto(job)

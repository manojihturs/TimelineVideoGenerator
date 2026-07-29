from pydantic import BaseModel

from app.models.config import RaceConfig


class SaveProjectRequest(BaseModel):
    name: str
    config: RaceConfig
    project_id: str | None = None  # set to update an existing project instead of creating a new one


class ProjectSummary(BaseModel):
    id: str
    name: str
    dataset_id: str
    created_at: str
    updated_at: str


class ProjectDetail(ProjectSummary):
    config: RaceConfig

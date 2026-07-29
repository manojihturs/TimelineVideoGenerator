from fastapi import APIRouter, HTTPException

from app.core import db
from app.models.config import RaceConfig
from app.models.project import ProjectDetail, ProjectSummary, SaveProjectRequest

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def save_project(req: SaveProjectRequest):
    project_id = db.save_project(req.name, req.config.dataset_id, req.config.model_dump(mode="json"), req.project_id)
    return {"project_id": project_id}


@router.get("", response_model=list[ProjectSummary])
def list_projects():
    return db.list_projects()


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str):
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    project["config"] = RaceConfig(**project["config"])
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str):
    if not db.delete_project(project_id):
        raise HTTPException(404, "Project not found")
    return {"deleted": True}

import uuid

from fastapi import APIRouter

from app.agent.graph import agent
from .schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    request_id = str(uuid.uuid4())
    result = agent.invoke({
        "jira_key": req.jira_key,
        "gitlab_project_id": req.gitlab_project_id,
        "gitlab_mr_id": req.gitlab_mr_id,
        "messages": [],
    })
    return AnalyzeResponse(
        request_id=request_id,
        status="completed",
        analysis=result.get("jira_comment_body"),
    )

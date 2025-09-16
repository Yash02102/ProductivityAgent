from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    jira_key: str = Field(..., examples=["PROJ-123"])
    gitlab_project_id: str = Field(..., examples=["8259"])
    gitlab_mr_id: str = Field(..., examples=["2932"])


class AnalyzeResponse(BaseModel):
    request_id: str
    status: str
    report_markdown: str | None = None
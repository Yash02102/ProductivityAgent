from __future__ import annotations
import gitlab
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from httpx import HTTPError
from config import settings


class GitLabClient:
    def __init__(self):
        self._client = gitlab.Gitlab(str(settings.GITLAB_URL), private_token=settings.GITLAB_TOKEN.get_secret_value())
    # Optional: self._client.session.verify = certifi.where()


    # @retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(multiplier=0.5, max=8), retry=retry_if_exception_type((HTTPError, gitlab.GitlabError)))
    def get_mr_changes(self, project_id: str, mr_id: str) -> dict:
        mr = self._client.projects.get(project_id).mergerequests.get(mr_id)
        web_url = mr.web_url
        summary = mr.changes()
        return {"web_url": web_url, "changes": summary.get("changes", [])}
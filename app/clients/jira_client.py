from __future__ import annotations
from typing import Optional, Iterable, Dict, Any
from atlassian import Jira
from app.config import settings

TEST_PLAN_ISSUE_TYPE = "Test Plan"

class JiraClient:
    def __init__(self):
        self._jira = Jira(
            url=str(settings.JIRA_INSTANCE_URL),
            token=settings.JIRA_API_TOKEN.get_secret_value(),
            username=settings.JIRA_USERNAME,
            cloud=settings.JIRA_IS_CLOUD,
        )

    def get_issue(self, key: str) -> dict:
        return self._jira.issue(key)
    
    def add_comment(self, issue_key: str, comment: str):
        self._jira.issue_add_comment(issue_key, comment)

    def search_jql(self, jql: str, start_at: int = 0, max_results: int = 50) -> dict:
        """
        Wrapper around the REST search endpoint.
        """
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ["key", "summary", "issuetype", "status", "components", "description"],
        }
        # NOTE: library expects path without leading slash
        return self._jira.post("rest/api/2/search", data=payload) or {}

    def create_issue(
        self,
        fields: dict,
        *,
        update_history: bool = False,
        update: Optional[dict] = None,
    ) -> dict:
        return self._jira.create_issue(fields=fields, update_history=update_history, update=update)

    def find_existing_test_plan(
        self,
        *,
        project_key: str,
        component: str,
        release_target: str
    ) -> Optional[str]:
        """
        Return the most recent Test Plan key in the same project (optionally same component)
        that references this MR id in summary or text. Idempotency helper.
        """
        comp_clause = f' AND component = "{component}"' if component else ""
        jql = (
            f'project = "{project_key}"'
            f'{comp_clause}'
            f' AND issuetype = "{TEST_PLAN_ISSUE_TYPE}"'
            f' AND ((summary ~ "{release_target.split()[0]}" AND summary ~ "{release_target.split()[1]}")' 
            f' OR (text ~ "{release_target.split()[0]}" AND text ~ "{release_target.split()[1]}"))'
            f' ORDER BY created DESC'
        )
        res = self.search_jql(jql, start_at=0, max_results=1) or {}
        issues = res.get("issues") or []
        return issues[0]["key"] if issues else None

    def ensure_test_plan(
        self,
        project_key: str,
        component: str,
        release_target: str,
    ) -> Dict[str, str]:
        """
        Create a Test Plan if not found; otherwise reuse existing. Returns the plan key.
        """
        existing = self.find_existing_test_plan(
            project_key=project_key, component=component, release_target=release_target
        )
        
        summary = (f'{release_target} - {project_key} - {component}')
        
        if existing:
            return { "key": existing, "summary": summary }

        itype = TEST_PLAN_ISSUE_TYPE
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": itype},
        }
        if component:
            fields["components"] = [{"name": component}]

        created = self.create_issue(fields=fields, update_history=False)
        key = (created or {}).get("key")
        if not key:
            raise RuntimeError(f"Failed to create Test Plan; response: {created}")
        return { "key": key, "summary": summary }

    def link_tests_to_plan(
        self,
        plan_key: str,
        test_keys: Iterable[str]
    ) -> Dict[str, Any]:
        """
        Link each test issue to the Test Plan.
        Returns {"linked": N, "failed": [keys...]}.
        """
        if(not plan_key or not test_keys or len(test_keys) == 0): return {}
        path = f"rest/raven/1.0/testplan/{plan_key}/test"
        payload = {"keys": test_keys, "assignee": None}
        try:
            result = self._jira.post(path, data=payload)
            return {"linked": result.get("tests"), "errors": result.get("errors")} if result else result
        except Exception as e:
            import requests
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                print("STATUS:", e.response.status_code)
                print("BODY  :", e.response.text[:2000])
            raise
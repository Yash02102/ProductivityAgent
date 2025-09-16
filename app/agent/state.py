from typing import Optional
from langgraph.graph import MessagesState

from schemas.functional_category import FunctionalCategory


class AgentState(MessagesState):
    jira_key: str
    gitlab_project_id: str
    gitlab_mr_id: str


    mr_web_url: Optional[str] = None
    merge_request_diffs: Optional[list[dict]] = None
    jira_issue_details: Optional[dict] = None
    impacted_code_entities: Optional[dict] = None


    code_changes_summary: Optional[str] = None
    keywords: Optional[list[str]] = None
    summary: Optional[str] = None
    functional_categories: FunctionalCategory


    jira_tests: Optional[list[dict]] = None
    jira_tests_by_category: dict[str, dict] = {}
    test_plan: dict
    jira_link_stats: dict
    jira_comment_body: str = None
    errors: Optional[list[str]] = None
import os
import re
from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.jira_comment import build_jira_comment
from clients.gitlab_client import GitLabClient
from clients.jira_client import JiraClient
from clients.llm_client import LLMClient
from services.impact_analyzer import ImpactAnalyzer
from services.jql_builder import build_jql
from agent.report import build_report, summarize_changes


_gl = GitLabClient()
_jira = JiraClient()
_llm = LLMClient()
_impact = ImpactAnalyzer(_gl._client)

# Helpers


def _append_error(state: dict, msg: str) -> dict:
    errs = list(state.get("errors") or [])
    errs.append(msg)
    return {"errors": errs}

# Nodes
def get_merge_request_diff(state: dict) -> dict:
    try:
        mr_details = _gl.get_mr_changes(state["gitlab_project_id"], state["gitlab_mr_id"])
        if not mr_details.get("changes"):
            return {"merge_request_diffs": [], **_append_error(state, "No diffs found for the given MR.")}
        return {"merge_request_diffs": mr_details.get("changes"), "mr_web_url": mr_details.get("web_url")}
    except Exception as e:
        return _append_error(state, f"GitLab diff error: {e}")
    
def get_issue_details(state: dict) -> dict:
    try:
        issue = _jira.get_issue(state["jira_key"]) or {}
        fields = issue.get("fields", {})
        comps = fields.get("components") or []
        release_target = fields.get("customfield_10220").get("value")
        comp_name = comps[0]["name"] if comps else None
        return {"jira_issue_details": {
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": (fields.get("status") or {}).get("name"),
                "assignee": (fields.get("assignee") or {}).get("displayName"),
                "component": comp_name,
                "project": (fields.get("project") or {}).get("key"),
                "description": fields.get("description"),
                "releaseTarget": f"{release_target[:4]} {release_target[-4:]}"
            }
        }
    except Exception as e:
        return _append_error(state, f"Jira issue error: {e}")
    
def get_impacted_code_entities(state: dict) -> dict:
    try:
        impacted = _impact.get_impacted_code_areas(state["gitlab_project_id"], state["gitlab_mr_id"]) or {}
        return {"impacted_code_entities": impacted}
    except Exception as e:
        return _append_error(state, f"Impact analyzer error: {e}")
    
def summarize_for_keywords(state: dict) -> dict:
    diffs = state.get("merge_request_diffs") or []
    impacted = state.get("impacted_code_entities") or {}
    jira_details = state.get("jira_issue_details") or {}

    summary = _llm.extract_keywords(impacted, jira_details) if _llm.enabled else None

    if summary:
        jql_terms = summary.jql_terms
        categories = [c.model_dump() for c in summary.categories]
    else:
        jql_terms = _heuristic_keywords(diffs, impacted)

    changes_summary = summarize_changes(diffs) if diffs else "No changes."

    return {
        "keywords": jql_terms,                 
        "functional_categories": categories,
        "code_changes_summary": changes_summary,
    }

def _heuristic_keywords(diffs: list[dict], impacted: dict | None) -> list[str]:
    kws: set[str] = set()

    for diff in diffs:
        for key in ("old_path", "new_path"):
            file_path = diff.get(key)
            if not file_path:
                continue
            fname = os.path.basename(file_path)
            base, ext = os.path.splitext(fname)
            for part in re.findall(r"[A-Za-z]+", base):
                if 2 <= len(part) <= 40:
                    kws.add(part.lower())
            if ext:
                ext_token = ext.replace(".", "").lower()
                if ext_token:
                    kws.add(ext_token)

    def _harvest_tokens(value: str | None):
        if not value:
            return
        for part in re.findall(r"[A-Za-z]+", value):
            if 2 <= len(part) <= 40:
                kws.add(part.lower())

    if impacted:
        files = impacted.get("files") or []
        for entry in files:
            if not isinstance(entry, dict):
                continue
            path_value = entry.get("path") or ""
            if path_value:
                base_name = os.path.splitext(os.path.basename(path_value))[0]
                _harvest_tokens(base_name)
            for block in entry.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                _harvest_tokens(block.get("location"))
                symbol = block.get("symbol") or {}
                if isinstance(symbol, dict):
                    _harvest_tokens(symbol.get("namespace"))
                    _harvest_tokens(symbol.get("name"))
                    for qualifier in symbol.get("qualifiers") or []:
                        _harvest_tokens(str(qualifier))

        summary = impacted.get("summary") or {}
        for key in ("files", "namespaces", "containers", "symbols", "qualified_symbols"):
            for item in summary.get(key) or []:
                _harvest_tokens(str(item))

    stop = {"util","common","core","main","test","impl","service","manager"}
    return sorted([k for k in kws if k not in stop])[:50]


def find_jira_tests(state: dict) -> dict:
    issue = state.get("jira_issue_details") or {}
    project = issue.get("project")
    component = issue.get("component")
    keywords = state.get("keywords") or []
    jql, _meta = build_jql(project, component, keywords)
    try:
        start = 0
        page = _jira.search_jql(jql, start_at=start, max_results=50)
        issues = page.get("issues", []) or []
        tests: list[dict] = []
        for it in issues:
            fields = it.get("fields", {}) or {}
            tests.append({
            "key": it.get("key"),
            "summary": fields.get("summary"),
            "status": (fields.get("status") or {}).get("name"),
            "issuetype": (fields.get("issuetype") or {}).get("name"),
            "components": [c.get("name") for c in (fields.get("components") or [])],
            })
        preferred = {"test","qa test","xray test","manual test","automated test"}
        filtered = [t for t in tests if (t.get("issuetype") or "").lower() in preferred] or tests
        return {"jira_tests": filtered}
    except Exception as e:
        return _append_error(state, f"Jira JQL error: {e}")


PREFERRED_TYPES = {"test", "qa test", "xray test", "manual test", "automated test"}

def _terms_from_category(cat: dict) -> list[str]:
    """Pull top terms from the category payload (from LLM or heuristic)."""
    terms = []
    for k in (cat.get("keywords") or []):
        kw = (k.get("keyword") if isinstance(k, dict) else k) or ""
        kw = kw.strip().lower()
        if 2 <= len(kw) <= 40:
            terms.append(kw)
    seen = set()
    out = []
    for t in terms:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

def find_jira_tests_by_category(state: dict) -> dict:
    issue = state.get("jira_issue_details") or {}
    project = issue.get("project")
    component = issue.get("component")

    cats = state.get("functional_categories") or []
    if not cats:
        return find_jira_tests(state)

    buckets: dict[str, dict] = {}
    flat: list[dict] = []
    seen_keys: set[str] = set()

    for cat in cats:
        cname = cat.get("name") or "uncategorized"
        terms = _terms_from_category(cat)
        if not terms:
            continue

        jql, _ = build_jql(project, component, terms)

        try:
            page = _jira.search_jql(jql, start_at=0, max_results=20)
            issues = page.get("issues", []) or []
        except Exception as e:
            buckets[cname] = {"terms_used": terms, "jql": jql, "tests": [], "error": str(e)}
            continue

        items = []
        for it in issues:
            fields = it.get("fields", {}) or {}
            issuetype = (fields.get("issuetype") or {}).get("name", "")
            components = [c.get("name") for c in (fields.get("components") or [])]
            item = {
                "key": it.get("key"),
                "summary": fields.get("summary"),
                "issuetype": issuetype,
                "components": components,
            }
            items.append(item)

            k = item["key"]
            if k and k not in seen_keys:
                seen_keys.add(k)
                flat.append(item)

        filtered = [t for t in items if (t.get("issuetype") or "").lower() in PREFERRED_TYPES] or items

        buckets[cname] = {"terms_used": terms, "jql": jql, "tests": filtered}

    return {
        "jira_tests": flat,                    
        "jira_tests_by_category": buckets,     
    }

def create_or_get_test_plan(state: dict) -> dict:
    issue = state.get("jira_issue_details") or {}
    project = issue.get("project")
    component = issue.get("component")
    release_target = issue.get("releaseTarget")
    test_plan = _jira.ensure_test_plan(project, component, release_target)
    return { "test_plan": test_plan }

def link_tests_to_plan(state: dict) -> dict:
    test_plan = state.get("test_plan")
    test_plan_key = test_plan.get("key")
    jira_tests = [t.get("key") for t in state.get("jira_tests") or []]
    linked_tests_stats = _jira.link_tests_to_plan(test_plan_key, jira_tests)
    return { "jira_link_stats": linked_tests_stats }

def post_jira_comment(state: dict) -> dict:
    try:
        body = build_jira_comment(state)
        issue_key = state.get("jira_key")
        if not issue_key:
            return _append_error(state, "Missing jira_key for posting a comment.")
        # # _jira is your existing atlassian.Jira client
        try:
            _jira.add_comment(issue_key, body)
        except Exception as e:
            return _append_error(state, f"Failed to post Jira comment: {e}")
        return {"jira_comment_posted": True, "jira_comment_body": body}
    except Exception as e:
        return _append_error(state, f"Failed to post Jira comment: {e}")


# Graph wiring
_graph = StateGraph(AgentState)
_graph.add_node("get_merge_request_diff", get_merge_request_diff)
_graph.add_node("get_issue_details", get_issue_details)
_graph.add_node("get_impacted_code_entities", get_impacted_code_entities)
_graph.add_node("summarize_for_keywords", summarize_for_keywords)
_graph.add_node("find_jira_tests", find_jira_tests_by_category)
_graph.add_node("create_or_get_test_plan", create_or_get_test_plan)
_graph.add_node("link_tests_to_plan", link_tests_to_plan)
_graph.add_node("post_jira_comment", post_jira_comment)


_graph.add_edge(START, "get_merge_request_diff")
_graph.add_edge("get_merge_request_diff", "get_issue_details")
_graph.add_edge("get_issue_details", "get_impacted_code_entities")
_graph.add_edge("get_impacted_code_entities", "summarize_for_keywords")
_graph.add_edge("summarize_for_keywords", "find_jira_tests")
_graph.add_edge("find_jira_tests", "create_or_get_test_plan")
_graph.add_edge("create_or_get_test_plan", "link_tests_to_plan")
_graph.add_edge("link_tests_to_plan", "post_jira_comment")
_graph.add_edge("post_jira_comment", END)


agent = _graph.compile()
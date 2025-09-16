def summarize_changes(diffs: list[dict]) -> str:
    added = deleted = modified = renamed = 0
    la = lr = 0
    files: list[str] = []
    for d in diffs:
        files.append(d.get("new_path") or d.get("old_path") or "")
        if d.get("new_file"): added += 1
        if d.get("deleted_file"): deleted += 1
        if d.get("renamed_file"): renamed += 1
        la += d.get("additions", 0)
        lr += d.get("deletions", 0)
        if not (d.get("new_file") or d.get("deleted_file") or d.get("renamed_file")):
            modified += 1
    files_list = "\n".join(f"- {f}" for f in sorted(set(files)) if f)
    return (
        f"Files: {len(set(files))} (added {added}, deleted {deleted}, renamed {renamed}, modified {modified})\n"
        f"Touched files:\n{files_list}"
    )


def build_report(state: dict) -> str:
    issue = state.get("jira_issue_details") or {}
    diffs = state.get("merge_request_diffs") or []
    tests = state.get("jira_tests") or []
    changes_block = f"```\n{state.get('code_changes_summary') or summarize_changes(diffs)}\n```"
    keywords_line = ", ".join(state.get("keywords") or []) or "_-_"


    issue_lines = [
        f"**Jira** `{issue.get('key','?')}` — *{issue.get('summary','?')}*",
        f"- Status: {issue.get('status','?')}",
        f"- Assignee: {issue.get('assignee','-')}",
        f"- Component: {issue.get('component','-')}",
        f"- Project: {issue.get('project','-')}",
    ]


    tests_lines = [
        f"- **{t.get('key','?')}** · *{t.get('issuetype','-')}* · _{t.get('status','-')}_ — {t.get('summary','-')}"
        for t in tests
    ]
    tests_block = "\n".join(tests_lines) if tests_lines else "_No matching Jira tests found._"


    errors = state.get("errors") or []
    err_block = "\n> **Errors/Warnings**:\n" + "\n".join(f"> - {e}" for e in errors) if errors else ""


    return (
        f"# Tracklink MR Analysis\n\n"
        f"**GitLab Project**: `{state.get('gitlab_project_id','?')}`\n"
        f"**MR**: `{state.get('gitlab_mr_id','?')}`\n\n"
        + "\n".join(issue_lines) + "\n\n"
        f"## Code Changes Summary\n{changes_block}\n\n"
        f"## Extracted Keywords\n{keywords_line}\n\n"
        f"## Suggested Jira Tests\n{tests_block}\n"
        f"{err_block}\n---\n*Auto-generated report.*"
    )
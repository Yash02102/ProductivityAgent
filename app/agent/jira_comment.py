from __future__ import annotations
from typing import Any, Dict, List, Optional

def _esc(text: str | None) -> str:
    """Minimal escaping to avoid breaking Jira wiki markup."""
    if not text:
        return ""
    return (text
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("[", r"\[")
            .replace("]", r"\]")
            ).strip()

def _stars(n: int | None) -> str:
    n = 3 if n is None else int(n)
    n = 1 if n < 1 else (5 if n > 5 else n)
    return "★" * n + "☆" * (5 - n)

def _render_changes_block(changes: str) -> str:
    if not changes:
        return ""
    return "\n".join([
        "h3. Code Changes Summary",
        "{code}",
        changes.strip(),
        "{code}",
    ])

def _stars(n: Any) -> str:
    try:
        n = int(n)
    except Exception:
        n = 3
    n = 1 if n < 1 else (5 if n > 5 else n)
    return "★" * n + "☆" * (5 - n)

def _esc(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    return (s.replace("{", r"\{")
             .replace("}", r"\}")
             .replace("[", r"\[")
             .replace("]", r"\]")).strip()

def _to_plain(x: Any) -> Any:
    return x.model_dump() if hasattr(x, "model_dump") else x

def _as_dict(x: Any) -> Dict[str, Any]:
    x = _to_plain(x)
    return x if isinstance(x, dict) else {}

def _as_list(x: Any) -> List[Any]:
    x = _to_plain(x)
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    if isinstance(x, dict) and "categories" in x:
        return _as_list(x.get("categories"))
    return [x]  # single item → list

def _uniq_keep_order(items: List[str]) -> List[str]:
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it); out.append(it)
    return out

def _render_functional_summary(
    functional_summary: Any,
    terms: Optional[List[str]] = None
) -> str:
    """
    Accepts:
      - list[FunctionalCategory|dict]  (your case)
      - FunctionalKeywordSummary model/dict
      - dict with {"categories": [...]}
    `terms` optional; if not provided and a full summary was passed, we'll pull `jql_terms`.
    """
    cats = _as_list(functional_summary)

    if terms is None and (isinstance(functional_summary, dict) or hasattr(functional_summary, "model_dump")):
        fsd = _as_dict(functional_summary)
        terms = _as_list(fsd.get("jql_terms"))
    terms = terms or []

    if not cats and not terms:
        return "h3. Functional Impact Summary\n_No categorized impacts available._"

    lines: List[str] = ["h3. Functional Impact Summary"]
    high_conf_terms: List[str] = []
    any_bullets = False

    for cat_raw in cats:
        cat = _as_dict(cat_raw)
        name = _esc(cat.get("name") or "uncategorized")
        rationale = _esc(cat.get("rationale") or "")
        lines.append(f"* *{name}* — _{rationale}_"); any_bullets = True

        kws = _as_list(cat.get("keywords"))
        for kw_raw in kws:
            kw = _as_dict(kw_raw)
            term = _esc(kw.get("keyword") or "?")
            note = _esc(kw.get("impact_note") or "")
            conf = kw.get("confidence", 3)
            evidence = _as_list(kw.get("evidence"))
            ev_txt = f" (evidence: {', '.join(_esc(x) for x in evidence[:3])})" if evidence else ""
            lines.append(f"** *{term}* — {note}  (confidence: {_stars(conf)}){ev_txt}")

            try:
                if int(conf) >= 4:
                    high_conf_terms.append(term)
            except Exception:
                pass

    if any_bullets:
        lines.append("")

    if terms:
        preview = ", ".join(_esc(t) for t in terms)
        lines.append(f"_*Relevant functional terms*_: {preview}")

    if high_conf_terms:
        lines.append(f"_*High-confidence focus*_: {', '.join(_uniq_keep_order(high_conf_terms)[:8])}")

    return "\n".join(lines)


def _render_tests_by_category(jira_tests_by_category: Dict[str, Any]) -> str:
    if not jira_tests_by_category:
        return "h3. Suggested Jira Tests by Category\n_No category-specific tests found._"

    out: List[str] = ["h3. Suggested Jira Tests by Category"]
    for cat_name, bucket in jira_tests_by_category.items():
        terms = ", ".join((bucket.get("terms_used") or [])) or "-"
        err = bucket.get("error")
        out.append(f"* *{_esc(cat_name)}* _(functionality: {terms})_")
        tests = bucket.get("tests") or []
        if err and not tests:
            out.append(f"** _No matches (error: {_esc(err)})_")
            continue
        if not tests:
            out.append("** _No matches_")
            continue
        for t in tests:
            key  = t.get("key", "?")
            summ = _esc(t.get("summary") or "")
            out.append(f"** {key} — {summ}")
    return "\n".join(out)

def _render_tests_fallback(jira_tests_flat: List[Dict[str, Any]] | None) -> str:
    if not jira_tests_flat:
        return "h3. Suggested Jira Tests\n_No matching Jira tests found._"
    out: List[str] = ["h3. Suggested Jira Tests"]
    for t in jira_tests_flat:
        key  = t.get("key", "?")
        summ = _esc(t.get("summary") or "")
        out.append(f"* {key} — {summ}")
    return "\n".join(out)

def build_jira_comment(state: dict) -> str:
    """
    Build a Jira wiki-markup comment using ONLY FunctionalKeywordSummary
    (categories.rationale + keywords.impact_note/confidence/evidence + jql_terms).
    """
    mr_id = str(state.get('gitlab_mr_id') or '?')
    mr_url = state.get('mr_web_url')
    jira_key = state.get('jira_key', '?')
    test_plan = state.get('test_plan')
    test_plan_key = test_plan.get('key') if test_plan else None
    test_plan_sum = test_plan.get('summary') if test_plan else None

    mr_ref = f"[Merge Request - {mr_id}|{mr_url}]" if mr_url else f"MR {mr_id}"
    plan_line = f"*Test Plan:* {test_plan_key}" + (f" — {test_plan_sum}" if test_plan_sum else "") if test_plan_key else "*Test Plan:* _not set_"
    
    header = (
        f"h2. Tracelink AI — {mr_ref}\n\n"
        f"h3. {plan_line}\n"
        f"_Analysis for Jira {jira_key}_"
    )

    parts: List[str] = [header]

    changes_block = _render_changes_block(state.get("code_changes_summary", ""))
    if changes_block:
        parts.append(changes_block)

    cats = state.get("functional_categories")
    terms = state.get("keywords", [])
    parts.append(_render_functional_summary(cats, terms))
    
    if test_plan_key:
        stats = state.get("jira_link_stats") or {}
        added = stats.get("linked") or stats.get("added")
        failed = stats.get("failed") or []
        count_note = f" ({added} added{', ' + str(len(failed)) + ' failed' if failed else ''})" if added or failed else ""

        tests_intro = f"\nh3. *Test Plan:* \n_Tests below have been added to {test_plan_key}{count_note}._"
        parts.append(tests_intro)

    if state.get("jira_tests_by_category"):
        parts.append(_render_tests_by_category(state.get("jira_tests_by_category") or {}))
    else:
        parts.append(_render_tests_fallback(state.get("jira_tests") or []))

    parts.append("_Generated by *Tracelink AI Agent*._")

    comment = "\n\n".join(p for p in parts if p)
    return comment

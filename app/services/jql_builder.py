import re
from typing import Iterable


_STOP = {"util","common","core","main","test","impl","service","manager"}


def clean_kw(kw: str) -> str:
    kw = kw.strip().replace('"', "")
    kw = re.sub(r"\s+", " ", kw)
    return kw


def build_jql(project: str | None, component: str | None, keywords: Iterable[str]) -> tuple[str, dict]:
    issue_types = ["Test"]
    terms = [f'"{clean_kw(k)}"' for k in keywords if clean_kw(k) and k not in _STOP]
    text_clause = " AND (" + " OR ".join([f"text ~ {t}" for t in terms[:12]]) + ")" if terms else ""
    proj = f'project = "{project}"' if project else ""
    comp = f' AND component = "{component}"' if component else ""
    it = " OR ".join([f'issueType = "{t}"' for t in issue_types])
    base = (proj + comp + f" AND ({it})" + text_clause).strip()
    jql = base[4:] if base.startswith("AND ") else base
    jql += " AND labels in (DSA_FT)"
    return jql or f"issueType in ({', '.join(issue_types)})", {"project": project, "component": component, "terms_used": terms[:12]}
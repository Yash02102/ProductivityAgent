from __future__ import annotations
import json
from typing import Optional, Any
import certifi
import httpx
from langchain_openai import ChatOpenAI
from app.schemas.functional_keyword_summary import FunctionalKeywordSummary
from app.config import settings
from app.utils.prompts import extract_functional_prompt
from langchain_core.messages import SystemMessage, HumanMessage

import re

MAX_JIRA_SUMMARY_CHARS = 300
MAX_JIRA_DESC_CHARS    = 1200

_jira_link_pat = re.compile(r"\[([^\]|]+)\|[^\]]+\]")
_macro_pat     = re.compile(r"\{[^}]+\}")             # {code}, {panel}, etc.
_code_pat      = re.compile(r"\{code[:\w= -]*}.*?\{code\}", re.S)

def _jira_plain_text(s: str) -> str:
    if not s:
        return ""
    s = _code_pat.sub(" ", s)
    s = _jira_link_pat.sub(r"\1", s)
    s = _macro_pat.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def _clip_text(value: str, limit: int) -> str:
    if not value:
        return ""
    if limit and limit > 0 and len(value) > limit:
        return value[:limit].strip()
    return value


def _sanitize_jira_value(key: str, value: Any):
    if value is None:
        return None
    if isinstance(value, str):
        text_value = _jira_plain_text(value)
        if not text_value:
            return None
        lower_key = (key or "").lower()
        if lower_key == "summary":
            text_value = _clip_text(text_value, MAX_JIRA_SUMMARY_CHARS)
        elif "description" in lower_key:
            text_value = _clip_text(text_value, MAX_JIRA_DESC_CHARS)
        return text_value
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for sub_key, sub_value in value.items():
            sanitized = _sanitize_jira_value(str(sub_key), sub_value)
            if sanitized not in (None, "", [], {}):
                cleaned[sub_key] = sanitized
        return cleaned or None
    if isinstance(value, (list, tuple, set)):
        cleaned_list = []
        for item in value:
            sanitized = _sanitize_jira_value(key, item)
            if sanitized not in (None, "", [], {}):
                cleaned_list.append(sanitized)
        return cleaned_list or None
    return value


def _build_jira_payload(details: dict[str, Any]) -> dict[str, Any]:
    if not details:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        sanitized = _sanitize_jira_value(str(key), value)
        if sanitized not in (None, "", [], {}):
            cleaned[key] = sanitized
    return cleaned

class LLMClient:
    def __init__(self) -> None:
        self.enabled = bool(settings.LLM_BASE_URL and settings.LLM_API_KEY)
        if self.enabled:
            self.llm = ChatOpenAI(
                model="llama-3-3-70b-instruct",
                base_url=settings.LLM_BASE_URL.__str__(),
                api_key=settings.LLM_API_KEY.get_secret_value(),
                temperature=0,
                http_client=httpx.Client(verify=certifi.where())
            )


    def extract_keywords(self, impacted_entities: dict, jira_issue_details: dict) -> Optional[FunctionalKeywordSummary]:
        if not self.enabled:
            return None
        
        structured_llm = self.llm.with_structured_output(FunctionalKeywordSummary)

        files = impacted_entities.get("files") or impacted_entities.get("impacted") or []

        def _format_symbol_path(symbol: dict) -> str | None:
            parts: list[str] = []
            namespace = symbol.get("namespace")
            if namespace:
                parts.extend([p for p in str(namespace).split(".") if p])
            for qualifier in symbol.get("qualifiers") or []:
                parts.extend([p for p in str(qualifier).split(".") if p and p not in parts])
            name = symbol.get("name") or symbol.get("display_name")
            if name:
                if not parts or parts[-1] != name:
                    parts.append(str(name))
            if parts:
                return ".".join(parts)
            return symbol.get("qualified_name") or symbol.get("display_name") or name

        def _format_block(block: dict) -> dict:
            symbol = block.get("symbol") or {}
            return {
                "location": block.get("location") or _format_symbol_path(symbol),
                "kind": symbol.get("kind"),
                "name": symbol.get("name"),
                "namespace": symbol.get("namespace"),
                "containers": symbol.get("qualifiers"),
                "signature": symbol.get("signature"),
                "span": block.get("span"),
                "changed_lines": block.get("changed_lines"),
                "code": block.get("snippet"),
            }

        payload = {
            "files": [
                {
                    "path": f.get("path"),
                    "language": f.get("language"),
                    "change": f.get("change"),
                    "blocks": [_format_block(b) for b in (f.get("blocks") or []) if b],
                }
                for f in files
                if f and f.get("blocks")
            ]
        }

        summary = impacted_entities.get("summary")
        if summary:
            payload["summary"] = summary
        
        jira_payload = _build_jira_payload(jira_issue_details or {})
        if jira_payload:
            payload["jira"] = jira_payload

        messages = [
            SystemMessage(content=extract_functional_prompt),
            HumanMessage(content=json.dumps(payload)),
        ]
        
        try:
            out: FunctionalKeywordSummary = structured_llm.invoke(messages)
            out.jql_terms = [t.strip().lower() for t in (out.jql_terms or []) if 2 <= len(t) <= 40][:12]
            return out
        except Exception as e:
            raise Exception (f"LLM error: {e}")

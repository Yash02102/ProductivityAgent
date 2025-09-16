from __future__ import annotations
import json
from typing import Optional
import certifi
import httpx
from langchain_openai import ChatOpenAI
from schemas.functional_keyword_summary import FunctionalKeywordSummary
from config import settings
from utils.prompts import extract_functional_prompt
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


    def extract_keywords(self, impacted_entities: dict, jira_issue_details: dict) -> FunctionalKeywordSummary:
        if not self.enabled:
            return None
        
        structured_llm = self.llm.with_structured_output(FunctionalKeywordSummary)
        
        payload = {
            "impacted": [
                {
                    "path": d.get("file"),
                    "enities":[
                        {
                            "type": entity.get("type"),
                            "name": entity.get("name"),
                            "code": entity.get("snippet"),
                        }
                        for entity in d.get("impacted")
                    ]
                }
                for d in impacted_entities.get("impacted")
            ]
        }
        
        if jira_issue_details:
            js = (jira_issue_details.get("summary") or "")[:MAX_JIRA_SUMMARY_CHARS]
            jd = (jira_issue_details.get("description") or "")
            jd = _jira_plain_text(jd)[:MAX_JIRA_DESC_CHARS]
            payload["jira"] = {
                "summary": js,
                "description": jd,
            }

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
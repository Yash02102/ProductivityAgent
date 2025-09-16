from pydantic import BaseModel, Field

from schemas.functional_category import FunctionalCategory

class FunctionalKeywordSummary(BaseModel):
    categories: list[FunctionalCategory] = Field(default_factory=list)
    # top domain-bearing terms flattened; cap at 12 for JQL
    jql_terms: list[str] = Field(default_factory=list)
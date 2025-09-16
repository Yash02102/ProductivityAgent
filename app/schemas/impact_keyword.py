from pydantic import BaseModel, Field

class ImpactKeyword(BaseModel):
    keyword: str = Field(..., description="domain-bearing term (1–4 words, lowercase)")
    impact_note: str = Field(..., description="≤18 words, what to test/what might break")
    evidence: list[str] = Field(default_factory=list, description="brief evidence tokens: file paths, entities")
    confidence: int = Field(ge=1, le=5, default=3)
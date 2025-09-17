from pydantic import BaseModel, Field

from app.schemas.impact_keyword import ImpactKeyword



class FunctionalCategory(BaseModel):
    name: str = Field(..., description="functional area, e.g., pricing, delivery, inventory, payments")
    rationale: str = Field(..., description="≤18 words, why this category exists in this MR")
    keywords: list[ImpactKeyword] = Field(default_factory=list)
from pydantic import BaseModel, Field
from typing import List, Literal


class AnalyzeRequest(BaseModel):
    user_story: str = Field(..., min_length=10, description="Jira-style user story text")


class StoryAnalysis(BaseModel):
    intent: str
    modules: List[str]
    acceptance_criteria: List[str]
    risk_factors: List[str]


TestType = Literal["functional", "boundary", "edge_case", "regression"]
RiskLevel = Literal["low", "medium", "high"]


class TestCase(BaseModel):
    id: str
    type: TestType
    module: str
    description: str
    steps: List[str]
    expected_result: str
    risk_level: RiskLevel
    automated: bool


RegressionRisk = Literal["low", "medium", "high", "critical"]


class ModuleRisk(BaseModel):
    module: str
    defect_probability: float
    historical_defect_count: int
    regression_risk: RegressionRisk
    top_defect_types: List[str]


class DefectAnalysis(BaseModel):
    module_risks: List[ModuleRisk]
    overall_confidence_score: int
    deployment_recommendation: Literal["GO", "NO-GO", "CONDITIONAL GO"]
    recommendation_rationale: str
    critical_test_ids: List[str]


class PipelineDashboard(BaseModel):
    story: StoryAnalysis
    tests: List[TestCase]
    defects: DefectAnalysis

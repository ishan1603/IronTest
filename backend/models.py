from pydantic import BaseModel, Field
from typing import List, Literal


class AnalyzeRequest(BaseModel):
    user_story: str = Field(..., min_length=10, description="Jira-style user story text")


class JiraIngestRequest(BaseModel):
    url: str = Field(..., description="Jira ticket URL")
    token: str = Field(..., description="Jira API Token or PAT")


class StoryAnalysis(BaseModel):
    intent: str = ""
    modules: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    security_vectors: List[str] = Field(default_factory=list)
    microservices: List[str] = Field(default_factory=list)


TestType = Literal["functional", "boundary", "edge_case", "regression"]
RiskLevel = Literal["low", "medium", "high"]


class TestCase(BaseModel):
    id: str = ""
    type: TestType = "functional"
    module: str = ""
    description: str = ""
    steps: List[str] = Field(default_factory=list)
    expected_result: str = ""
    risk_level: RiskLevel = "low"
    automated: bool = False
    automation_snippet: List[str] = Field(default_factory=list)


class TestResult(BaseModel):
    test_id: str = ""
    status: Literal["pass", "fail", "error", "skipped"] = "pass"
    error_message: str = ""


class TestExecutionSummary(BaseModel):
    results: List[TestResult] = Field(default_factory=list)
    duration_seconds: float = 0.0


RegressionRisk = Literal["low", "medium", "high", "critical"]


class ModuleRisk(BaseModel):
    module: str = ""
    defect_probability: float = 0.0
    historical_defect_count: int = 0
    regression_risk: RegressionRisk = "low"
    top_defect_types: List[str] = Field(default_factory=list)
    vulnerability_heatmap: str = ""


class DefectAnalysis(BaseModel):
    module_risks: List[ModuleRisk] = Field(default_factory=list)
    overall_confidence_score: int = 0
    deployment_recommendation: Literal["GO", "NO-GO", "CONDITIONAL GO"] = "GO"
    recommendation_rationale: str = ""
    critical_test_ids: List[str] = Field(default_factory=list)


class PipelineDashboard(BaseModel):
    story: StoryAnalysis
    tests: List[TestCase]
    execution: TestExecutionSummary
    defects: DefectAnalysis

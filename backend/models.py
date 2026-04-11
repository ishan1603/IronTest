from pydantic import BaseModel, Field
from typing import List, Literal


class AnalyzeRequest(BaseModel):
    user_story: str = Field(..., min_length=10, description="Jira-style user story text")


class JiraIngestRequest(BaseModel):
    url: str = Field(..., description="Jira ticket URL")
    token: str | None = Field(default=None, description="Jira API Token or PAT")
    email: str | None = Field(default=None, description="Jira user email for API auth")
    issue_key: str | None = Field(default=None, description="Optional issue key like PROJ-123")


class AzureDevOpsIngestRequest(BaseModel):
    url: str = Field(..., description="Azure DevOps work item URL")
    pat: str | None = Field(default=None, description="Azure DevOps Personal Access Token")
    organization: str | None = Field(default=None, description="Optional organization override")
    project: str | None = Field(default=None, description="Optional project override")
    work_item_id: str | None = Field(default=None, description="Optional work item id override")


class StoryHistoryRequest(BaseModel):
    story_text: str | None = Field(default=None, description="Original user story text")
    story_intent: str | None = Field(default=None, description="Parsed story intent")
    modules: List[str] = Field(default_factory=list, description="Story module list")
    limit: int = Field(default=80, ge=1, le=300, description="Maximum runs to return")


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
    module_test_count: int = 0
    module_pass_rate: float = 0.0
    module_failed: int = 0
    module_errors: int = 0
    module_skipped: int = 0
    historical_pass_rate: float = 0.0
    pass_rate_delta: float = 0.0
    trend_vs_history: Literal["improving", "stable", "declining"] = "stable"
    risk_drivers: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    llm_score: int = 0
    current_pass_rate: float = 0.0
    current_score: int = 0
    historical_average_pass_rate: float = 0.0
    historical_score: int = 0
    recent_pass_rate: float = 0.0
    trend_delta_recent: float = 0.0
    trend_adjustment: int = 0
    module_risk_penalty: int = 0
    execution_penalty: int = 0
    final_score: int = 0


class HistoricalComparison(BaseModel):
    total_runs: int = 0
    current_pass_rate: float = 0.0
    historical_average_pass_rate: float = 0.0
    recent_pass_rate: float = 0.0
    delta_vs_average: float = 0.0
    delta_vs_recent: float = 0.0
    trend: Literal["improving", "stable", "declining"] = "stable"


class DefectAnalysis(BaseModel):
    module_risks: List[ModuleRisk] = Field(default_factory=list)
    overall_confidence_score: int = 0
    deployment_recommendation: Literal["GO", "NO-GO", "CONDITIONAL GO"] = "GO"
    recommendation_rationale: str = ""
    critical_test_ids: List[str] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown | None = None
    historical_comparison: HistoricalComparison | None = None


class PipelineDashboard(BaseModel):
    story: StoryAnalysis
    tests: List[TestCase]
    execution: TestExecutionSummary
    defects: DefectAnalysis

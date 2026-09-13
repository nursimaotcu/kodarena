from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Submission(StrictModel):
    problem_id: str = Field(max_length=80)
    language: Literal["python", "javascript"]
    source: str = Field(min_length=1, max_length=16_000)


class Claim(StrictModel):
    worker_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class Lease(Claim):
    token: str = Field(min_length=16, max_length=128)


class CaseResult(StrictModel):
    index: int = Field(ge=0, le=10)
    verdict: Literal[
        "accepted", "wrong_answer", "time_limit", "memory_limit", "output_limit", "runtime_error"
    ]
    elapsed_ms: float = Field(ge=0, le=120_000, allow_inf_nan=False)
    stdout: str = Field(default="", max_length=4096)
    stderr: str = Field(default="", max_length=4096)


class Completion(Lease):
    kind: Literal["judged", "infrastructure_error"]
    cases: list[CaseResult] = Field(default_factory=list, max_length=10)
    error: str = Field(default="", max_length=500)

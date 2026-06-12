from pydantic import Field, model_validator

from nanobot.evolve._base import EvolveBase


class RubricScore(EvolveBase):
    process: float = Field(ge=0.0, le=1.0)
    output: float = Field(ge=0.0, le=1.0)
    token: float = Field(ge=0.0, le=1.0)
    aggregate: float = Field(ge=0.0, le=1.0)


class RubricWeights(EvolveBase):
    process: float = Field(default=0.4, ge=0.0, le=1.0)
    output: float = Field(default=0.4, ge=0.0, le=1.0)
    token: float = Field(default=0.2, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "RubricWeights":
        s = self.process + self.output + self.token
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                f"RubricWeights must sum to 1.0 (got {s:.6f}); "
                f"process={self.process}, output={self.output}, token={self.token}"
            )
        return self


def _assert_odd_pool_size(n: int, *, context: str) -> None:
    if n == 0 or n % 2 == 0:
        raise ValueError(
            f"{context}: judge pool size must be odd and >= 1 (got {n})"
        )

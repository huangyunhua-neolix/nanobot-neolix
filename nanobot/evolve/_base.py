from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class EvolveBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=False,
    )


class FrozenEvolveBase(EvolveBase):
    """EvolveBase + frozen=True. Use for immutable manifest records.

    Centralised so future EvolveBase config additions (e.g. ser_json_*, json_encoders)
    propagate automatically — three sites previously hand-rolled the frozen overlay
    in three different ways (dict-merge, inline ConfigDict, @dataclass), which is the
    drift this class is here to prevent.
    """

    model_config = ConfigDict(**{**EvolveBase.model_config, "frozen": True})

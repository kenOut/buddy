from pydantic import BaseModel, ConfigDict
from typing_extensions import TypeAliasType

# A precisely-typed stand-in for arbitrary JSON, used for fields whose
# shape genuinely varies by caller (e.g. QuestAttempt.submission, which
# differs per quest type) without falling back to `Any`. Built with
# TypeAliasType (Pydantic's documented approach for recursive aliases) —
# a plain recursive `Union[..., "JSONValue"]` hits Python's forward-ref
# resolver recursion limit on this Python/Pydantic combination.
JSONValue = TypeAliasType(
    "JSONValue", "str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]"
)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

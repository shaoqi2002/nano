from typing import Any


def model_for_structured_output(model: Any) -> Any:
    """Return a model copy compatible with forced structured output.

    DeepSeek V4 enables thinking by default but rejects the forced tool_choice
    used by LangChain's function-calling structured output. Keep thinking for
    normal agent turns and disable it only for schema-constrained calls.
    """
    model_copy = getattr(model, "model_copy", None)
    if not callable(model_copy):
        return model

    extra_body = dict(getattr(model, "extra_body", None) or {})
    extra_body["thinking"] = {"type": "disabled"}
    return model_copy(update={"extra_body": extra_body})


def with_structured_output(model: Any, schema: Any) -> Any:
    return model_for_structured_output(model).with_structured_output(schema)

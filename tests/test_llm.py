import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.llm import GroqSQLGenerator
from backend.models import QueryFailure
from tests.test_policy import CATALOG


@pytest.mark.parametrize("content,valid", [
    ('{"sql":"SELECT name FROM products","reason":null}', True),
    ('{"sql":42}', False),
    ("malformed JSON", False),
])
def test_groq_adapter_parses_json_and_sends_permitted_schema(content, valid):
    completion = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    ))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
    generator = GroqSQLGenerator(client, "test-model")
    if valid:
        assert asyncio.run(generator.generate("List product names", CATALOG)).sql == "SELECT name FROM products"
    else:
        with pytest.raises(QueryFailure) as error:
            asyncio.run(generator.generate("List product names", CATALOG))
        assert error.value.code == "invalid_model_response"
    sent = completion.await_args.kwargs
    assert sent["response_format"] == {"type": "json_object"}
    assert "shop.products: id (integer), name (varchar)" in sent["messages"][0]["content"]
    assert sent["messages"][1]["content"] == "List product names"

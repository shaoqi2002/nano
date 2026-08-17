import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from app.schema.conversation import MessageResponse


class MessageOptionsTests(unittest.TestCase):
    def test_user_message_serializes_request_option_snapshot(self) -> None:
        options = {
            "mode": "research",
            "use_rag": True,
            "allow_write_tools": True,
        }
        response = MessageResponse.model_validate(SimpleNamespace(
            id=1,
            role="user",
            content="测试",
            sources=[],
            options=options,
            created_at=datetime.now(timezone.utc),
        ))

        self.assertEqual(response.options, options)


if __name__ == "__main__":
    unittest.main()

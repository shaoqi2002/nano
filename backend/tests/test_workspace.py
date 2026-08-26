import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.repository.conversation import list_conversations
from app.repository.document import get_document
from app.service.workspace import (
    CH4_WORKSPACE_ID,
    current_workspace_id,
    require_ch4_workspace,
    get_workspace_session,
)


class WorkspaceSession:
    def __init__(self, workspace_id: UUID):
        self.info = {"workspace_id": workspace_id}
        self.execute = AsyncMock(return_value=[])
        self.scalar = AsyncMock(return_value=None)


class WorkspaceIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_workspace_lookup_finishes_implicit_transaction(self) -> None:
        workspace = SimpleNamespace(id=CH4_WORKSPACE_ID, slug="ch4")

        class ScopedSession:
            def __init__(self):
                self.info = {}
                self.get = AsyncMock(return_value=workspace)
                self.rollback = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            def in_transaction(self):
                return True

        scoped_session = ScopedSession()
        with patch("app.service.workspace.SessionLocal", return_value=scoped_session):
            dependency = get_workspace_session(str(CH4_WORKSPACE_ID), None)
            yielded = await anext(dependency)
            self.assertIs(yielded, scoped_session)
            self.assertEqual(yielded.info["workspace_id"], CH4_WORKSPACE_ID)
            scoped_session.rollback.assert_awaited_once()
            await dependency.aclose()

    async def test_conversation_queries_are_workspace_scoped(self) -> None:
        session = WorkspaceSession(CH4_WORKSPACE_ID)
        await list_conversations(session)
        statement = session.execute.await_args.args[0]
        self.assertIn("conversations.workspace_id", str(statement))

    async def test_document_lookup_is_workspace_scoped(self) -> None:
        session = WorkspaceSession(UUID("00000000-0000-0000-0000-000000000123"))
        await get_document(session, UUID("00000000-0000-0000-0000-000000000456"))
        statement = session.scalar.await_args.args[0]
        self.assertIn("documents.workspace_id", str(statement))

    async def test_ch4_only_features_reject_other_workspaces(self) -> None:
        ch4_session = WorkspaceSession(CH4_WORKSPACE_ID)
        self.assertEqual(current_workspace_id(ch4_session), CH4_WORKSPACE_ID)
        require_ch4_workspace(ch4_session)

        other_session = WorkspaceSession(
            UUID("00000000-0000-0000-0000-000000000123")
        )
        with self.assertRaises(HTTPException) as context:
            require_ch4_workspace(other_session)
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

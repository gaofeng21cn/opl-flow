from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "inspect_codex_recovery.py"
)
SPEC = importlib.util.spec_from_file_location("inspect_codex_recovery", SCRIPT)
assert SPEC and SPEC.loader
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class RecoveryInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.database = self.root / "state.sqlite"
        self.rollout = self.root / "rollout-parent.jsonl"

        connection = sqlite3.connect(self.database)
        connection.executescript(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                rollout_path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                cwd TEXT NOT NULL,
                title TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                preview TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE thread_spawn_edges (
                parent_thread_id TEXT NOT NULL,
                child_thread_id TEXT NOT NULL PRIMARY KEY,
                status TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO threads
                (id, rollout_path, created_at, updated_at, cwd, title, preview)
            VALUES (?, ?, 1, 2, '/workspace', ?, ?)
            """,
            (
                "parent",
                str(self.rollout),
                "Fleet runner coordinator " * 12,
                "Recover the runner task",
            ),
        )
        connection.execute(
            """
            INSERT INTO threads
                (id, rollout_path, created_at, updated_at, cwd, title, preview)
            VALUES ('child', '', 1, 2, '/workspace', 'Child task', '')
            """
        )
        connection.execute(
            """
            INSERT INTO thread_spawn_edges
                (parent_thread_id, child_thread_id, status)
            VALUES ('parent', 'child', 'open')
            """
        )
        connection.commit()
        connection.close()

        records = [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "spawn-1",
                    "arguments": json.dumps(
                        {"task_name": "runner_audit", "fork_turns": "3"}
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "status-1",
                    "output": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "agents": [
                                        {
                                            "agent_name": "/root/runner_audit",
                                            "agent_status": {
                                                "completed": "Runner evidence complete"
                                            },
                                        }
                                    ]
                                }
                            ),
                        }
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "The runner recovery evidence is complete.",
                        }
                    ],
                },
            },
        ]
        self.rollout.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_inspect_recovers_spawn_graph_and_ephemeral_status(self) -> None:
        result = recovery.inspect_thread(
            argparse.Namespace(
                database=str(self.database),
                thread_id="parent",
                depth=3,
                graph_limit=5,
                term=["runner"],
                excerpt_limit=80,
                event_limit=5,
                metadata_limit=80,
            )
        )

        self.assertTrue(result["thread_found"])
        self.assertEqual(
            result["persistent_spawn_graph"]["edges"][0]["child_id"],
            "child",
        )
        self.assertEqual(
            result["rollout"]["ephemeral_spawn_calls"][0]["task_name"],
            "runner_audit",
        )
        self.assertEqual(
            result["rollout"]["ephemeral_task_statuses"][
                "/root/runner_audit"
            ]["status"],
            "completed",
        )
        self.assertTrue(result["thread"]["title"]["truncated"])

    def test_search_supports_reduced_legacy_schema(self) -> None:
        result = recovery.search_threads(
            argparse.Namespace(
                database=str(self.database),
                terms=["Fleet", "runner"],
                limit=10,
                metadata_limit=80,
            )
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["threads"][0]["id"], "parent")
        self.assertIsNone(result["threads"][0]["recency_at_ms"])

    def test_database_connection_is_query_only(self) -> None:
        with recovery.connect_read_only(self.database) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute(
                    """
                    INSERT INTO threads
                        (id, rollout_path, created_at, updated_at, cwd, title)
                    VALUES ('forbidden', '', 1, 1, '/workspace', 'Forbidden')
                    """
                )


if __name__ == "__main__":
    unittest.main()

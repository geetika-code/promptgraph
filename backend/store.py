"""SQLite persistence: workflows, per-node prompt versions, and test cases."""
import sqlite3
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

from . import config
from .models import TestCase, Workflow

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS prompt_versions (
  workflow_id TEXT NOT NULL, node_id TEXT NOT NULL, version INTEGER NOT NULL, prompt TEXT NOT NULL, created_at REAL NOT NULL,
  PRIMARY KEY (workflow_id, node_id, version));
CREATE TABLE IF NOT EXISTS test_cases (workflow_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
"""


@contextmanager
def db():
    conn = sqlite3.connect(config.db_path())
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_workflow(workflow_id: str) -> Optional[Workflow]:
    with db() as c:
        row = c.execute("SELECT payload FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    return Workflow.model_validate_json(row[0]) if row else None


def list_workflows() -> List[dict]:
    with db() as c:
        rows = c.execute("SELECT id, name FROM workflows ORDER BY updated_at DESC").fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def save_workflow(w: Workflow) -> None:
    now = time.time()
    with db() as c:
        c.execute("INSERT OR REPLACE INTO workflows(id,name,payload,updated_at) VALUES (?,?,?,?)",
                  (w.id, w.name, w.model_dump_json(), now))
        for n in w.nodes:
            row = c.execute("SELECT version, prompt FROM prompt_versions WHERE workflow_id=? AND node_id=? ORDER BY version DESC LIMIT 1",
                            (w.id, n.id)).fetchone()
            if row is None or row[1] != n.prompt:
                c.execute("INSERT INTO prompt_versions VALUES (?,?,?,?,?)",
                          (w.id, n.id, (row[0] + 1) if row else 1, n.prompt, now))


def delete_workflow(workflow_id: str) -> None:
    with db() as c:
        for table, col in (("workflows", "id"), ("prompt_versions", "workflow_id"), ("test_cases", "workflow_id")):
            c.execute(f"DELETE FROM {table} WHERE {col}=?", (workflow_id,))


def prompt_history(workflow_id: str) -> Dict[str, List[str]]:
    """node_id -> prompts ordered by version (index + 1 == version number)."""
    with db() as c:
        rows = c.execute("SELECT node_id, prompt FROM prompt_versions WHERE workflow_id=? ORDER BY node_id, version",
                         (workflow_id,)).fetchall()
    out: Dict[str, List[str]] = {}
    for node_id, prompt in rows:
        out.setdefault(node_id, []).append(prompt)
    return out


def get_cases(workflow_id: str) -> List[TestCase]:
    with db() as c:
        row = c.execute("SELECT payload FROM test_cases WHERE workflow_id=?", (workflow_id,)).fetchone()
    if not row:
        return []
    import json
    return [TestCase(**x) for x in json.loads(row[0])]


def save_cases(workflow_id: str, cases: List[TestCase]) -> None:
    import json
    with db() as c:
        c.execute("INSERT OR REPLACE INTO test_cases VALUES (?,?)", (workflow_id, json.dumps([x.model_dump() for x in cases])))

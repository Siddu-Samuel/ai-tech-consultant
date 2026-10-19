"""SQLite persistence for meeting transcripts, draft scopes and approved baselines."""
import json
import sqlite3
from pathlib import Path
import re
from threading import RLock

from app.schemas import Requirement, ScopeResult
from app.config import get_settings

_lock = RLock()
_path = Path(__file__).resolve().parents[1] / "scope.db"


def _connect():
    db = sqlite3.connect(_path, timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS scopes(id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_scopes_baseline ON scopes(title, status, created_at)")
    return db


def _pg_connect():
    import psycopg

    db = psycopg.connect(get_settings().database_url)
    db.execute("CREATE TABLE IF NOT EXISTS meeting_scopes(id TEXT PRIMARY KEY, title TEXT NOT NULL, body JSONB NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS meeting_scopes_baseline ON meeting_scopes(title, status, created_at)")
    return db


def _reconcile_with_baseline(scope: ScopeResult, previous: dict) -> None:
    """Retain baseline IDs, record explicit changes, and mark additions for scope review."""
    old = {row["id"]: row for row in previous["requirements"] if row.get("active", True)}
    unmatched = set(old)
    reconciled = []
    next_id = max([int(key.split("-")[-1]) for key in old if key.startswith("REQ-") and key.split("-")[-1].isdigit()] or [0]) + 1
    for requirement in scope.requirements:
        current_terms = set(re.findall(r"[a-z0-9]+", requirement.description.casefold())) - {"the", "and", "for", "with", "from", "that", "this", "must", "need", "please", "client"}
        best_id = None
        best_score = 0.0
        for key in unmatched:
            prior_terms = set(re.findall(r"[a-z0-9]+", old[key]["description"].casefold())) - {"the", "and", "for", "with", "from", "that", "this", "must", "need", "please", "client"}
            score = len(current_terms & prior_terms) / max(1, len(current_terms | prior_terms))
            if score > best_score:
                best_id, best_score = key, score
        if best_id and best_score >= 0.2:
            unmatched.remove(best_id)
            requirement.id = best_id
            requirement.version = int(old[best_id].get("version", 1)) + 1
            if re.search(r"\b(remove|drop|delete|exclude)\b", requirement.description, re.I):
                deleted = type(requirement).model_validate(old[best_id])
                deleted.active = False
                deleted.source_passage = requirement.source_passage
                reconciled.append(deleted)
                continue
        else:
            requirement.id = f"REQ-{next_id:03d}"
            requirement.version = 1
            next_id += 1
        reconciled.append(requirement)
    # A complete revised transcript that omits a previously active item removes it from scope.
    for key in sorted(unmatched):
        removed = Requirement.model_validate(old[key])
        removed.active = False
        removed.version += 1
        reconciled.append(removed)
    scope.requirements = reconciled
    old_by_id = old
    new_by_id = {r.id: r.model_dump() for r in reconciled if r.active}
    changes = []
    for key in sorted(old_by_id.keys() | new_by_id.keys()):
        if key not in old_by_id:
            changes.append({"type": "addition", "potential_out_of_scope": True, "requires_approval": True, "id": key, "new": new_by_id[key]})
        elif key not in new_by_id:
            changes.append({"type": "removal", "id": key, "old": old_by_id[key], "source_passage": next((r.source_passage for r in reconciled if r.id == key), "Requirement absent from revised transcript")})
        elif old_by_id[key]["description"] != new_by_id[key]["description"]:
            changes.append({"type": "modification", "id": key, "old": old_by_id[key], "new": new_by_id[key]})
    scope.changes = changes


def put_scope(scope: ScopeResult) -> ScopeResult:
    if get_settings().storage_mode == "postgres":
        with _lock, _pg_connect() as db:
            previous_row = db.execute("SELECT body FROM meeting_scopes WHERE id=%s AND status='approved'", (scope.baseline_id,)).fetchone() if scope.baseline_id else None
            if scope.baseline_id and not previous_row:
                raise ValueError("Only an existing human-approved scope can be used as a baseline")
            if previous_row:
                previous = previous_row[0]
                if isinstance(previous, str): previous = json.loads(previous)
                _reconcile_with_baseline(scope, previous)
            db.execute("INSERT INTO meeting_scopes(id,title,body,status,created_at) VALUES(%s,%s,%s::jsonb,%s,%s)", (scope.id, scope.title, scope.model_dump_json(), scope.status, scope.created_at))
        return scope
    with _lock, _connect() as db:
        previous = None
        if scope.baseline_id:
            row = db.execute("SELECT body FROM scopes WHERE id=? AND status='approved'", (scope.baseline_id,)).fetchone()
            if row:
                previous = json.loads(row[0])
            else:
                raise ValueError("Only an existing human-approved scope can be used as a baseline")
        if previous:
            _reconcile_with_baseline(scope, previous)
        db.execute("INSERT INTO scopes(id,title,body,status,created_at) VALUES(?,?,?,?,?)", (scope.id, scope.title, scope.model_dump_json(), scope.status, scope.created_at))
    return scope


def get_scope(scope_id: str) -> ScopeResult | None:
    if get_settings().storage_mode == "postgres":
        with _lock, _pg_connect() as db:
            row = db.execute("SELECT body FROM meeting_scopes WHERE id=%s", (scope_id,)).fetchone()
        if not row: return None
        body = row[0] if isinstance(row[0], str) else json.dumps(row[0])
        return ScopeResult.model_validate_json(body)
    with _lock, _connect() as db:
        row = db.execute("SELECT body FROM scopes WHERE id=?", (scope_id,)).fetchone()
    return ScopeResult.model_validate_json(row[0]) if row else None


def list_scopes() -> list[ScopeResult]:
    if get_settings().storage_mode == "postgres":
        with _lock, _pg_connect() as db:
            rows = db.execute("SELECT body FROM meeting_scopes ORDER BY created_at DESC").fetchall()
        return [ScopeResult.model_validate(row[0]) if isinstance(row[0], dict) else ScopeResult.model_validate_json(row[0]) for row in rows]
    with _lock, _connect() as db:
        rows = db.execute("SELECT body FROM scopes ORDER BY created_at DESC").fetchall()
    return [ScopeResult.model_validate_json(row[0]) for row in rows]


def review_scope(scope_id: str, approve: bool, reviewer: str) -> ScopeResult | None:
    if get_settings().storage_mode == "postgres":
        with _lock, _pg_connect() as db:
            row = db.execute("SELECT body FROM meeting_scopes WHERE id=%s", (scope_id,)).fetchone()
            if not row: return None
            scope = ScopeResult.model_validate(row[0]) if isinstance(row[0], dict) else ScopeResult.model_validate_json(row[0])
            scope.status = "approved" if approve else "rejected"
            scope.reviewer = reviewer
            scope.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            db.execute("UPDATE meeting_scopes SET body=%s::jsonb,status=%s WHERE id=%s", (scope.model_dump_json(), scope.status, scope_id))
        return scope
    with _lock, _connect() as db:
        row = db.execute("SELECT body FROM scopes WHERE id=?", (scope_id,)).fetchone()
        if not row: return None
        scope = ScopeResult.model_validate_json(row[0])
        scope.status = "approved" if approve else "rejected"
        scope.reviewer = reviewer
        scope.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        db.execute("UPDATE scopes SET body=?, status=? WHERE id=?", (scope.model_dump_json(), scope.status, scope_id))
    return scope

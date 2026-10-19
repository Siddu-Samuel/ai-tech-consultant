"""Persistent article, chunk, image, ingestion, and escalation storage.

PostgreSQL uses pgvector with a configured dimension. SQLite is deliberately
limited to deterministic test/demo runs and stores vectors as JSON arrays.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote


SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
CREATE TABLE IF NOT EXISTS articles(
  id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
  content_hash TEXT NOT NULL, sitemap_lastmod TEXT, status TEXT NOT NULL,
  last_ingested_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS knowledge_chunks(
  id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES articles(id),
  section_heading TEXT NOT NULL, content TEXT NOT NULL, embedding TEXT NOT NULL,
  metadata_json TEXT NOT NULL, content_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_article_active ON knowledge_chunks(article_id, active);
CREATE TABLE IF NOT EXISTS image_assets(
  id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES articles(id), image_url TEXT NOT NULL,
  alt_text TEXT NOT NULL, nearby_context TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  analysis_status TEXT NOT NULL DEFAULT 'pending', content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(article_id, image_url)
);
CREATE TABLE IF NOT EXISTS ingestion_runs(
  id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
  urls_discovered INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0, removed INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0, error_summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ingestion_pages(
  url TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT, content_hash TEXT, retry_after TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS escalations(
  id TEXT PRIMARY KEY, question TEXT NOT NULL, reason TEXT NOT NULL, evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open', approved_answer TEXT, reviewer TEXT,
  reviewed_at TEXT, version INTEGER NOT NULL DEFAULT 1, expires_at TEXT, request_id TEXT UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS approved_knowledge(
  id TEXT PRIMARY KEY, answer TEXT NOT NULL, evidence_json TEXT NOT NULL,
  scope TEXT NOT NULL, customer_id TEXT, approved_by TEXT NOT NULL,
  version INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, expires_at TEXT,
  embedding TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS query_audits(
  request_id TEXT PRIMARY KEY, question_hash TEXT NOT NULL, status TEXT NOT NULL,
  evidence_json TEXT NOT NULL, model_id TEXT, prompt_version TEXT NOT NULL,
  latency_ms INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
  answer_text TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_SQLITE_LOCKS: dict[str, threading.Lock] = {}
_SQLITE_LOCKS_GUARD = threading.Lock()


class IngestionLease:
    def __init__(self, connection: Any, *, sqlite_lock: threading.Lock | None = None, lock_key: int = 0):
        self.connection = connection
        self.sqlite_lock = sqlite_lock
        self.lock_key = lock_key
        self.acquired = connection is not None

    def release(self) -> None:
        if not self.acquired:
            return
        if self.sqlite_lock is not None:
            self.sqlite_lock.release()
        else:
            try:
                self.connection.execute("SELECT pg_advisory_unlock(%s)", (self.lock_key,))
            finally:
                self.connection.close()
        self.acquired = False

    def __enter__(self) -> "IngestionLease":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


class KnowledgeStore:
    def __init__(self, database_url: str, embedding_dimensions: int = 64, embedding_provider: str = "local-test"):
        if embedding_dimensions < 8 or embedding_dimensions > 2000:
            raise ValueError("embedding_dimensions must be between 8 and 2000 (the pgvector HNSW limit)")
        self.database_url = database_url
        self.embedding_dimensions = embedding_dimensions
        self.embedding_provider = embedding_provider
        self.is_sqlite = database_url.startswith("sqlite:")
        self._sqlite: sqlite3.Connection | None = None
        if self.is_sqlite:
            raw = database_url.removeprefix("sqlite:///")
            path = unquote(raw)
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = sqlite3.connect(path, check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row

    def _pg(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL mode requires psycopg and pgvector; install Task 1 requirements") from exc
        # Vector values are passed and read as PostgreSQL's textual vector form,
        # so registration is not required before the vector extension exists.
        return psycopg.connect(self.database_url)

    def initialize(self) -> None:
        if self.is_sqlite:
            assert self._sqlite is not None
            self._sqlite.executescript(SQLITE_SCHEMA)
            self._sqlite.commit()
            return
        vector_size = self.embedding_dimensions
        schema = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
        INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;
        CREATE TABLE IF NOT EXISTS articles(
          id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
          content_hash TEXT NOT NULL, sitemap_lastmod TEXT, status TEXT NOT NULL,
          last_ingested_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks(
          id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES articles(id), section_heading TEXT NOT NULL,
          content TEXT NOT NULL, embedding vector({vector_size}) NOT NULL, metadata_json JSONB NOT NULL,
          content_hash TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_article_active ON knowledge_chunks(article_id, active);
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
        CREATE TABLE IF NOT EXISTS image_assets(
          id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES articles(id), image_url TEXT NOT NULL,
          alt_text TEXT NOT NULL, nearby_context TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          analysis_status TEXT NOT NULL DEFAULT 'pending', content_hash TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(article_id, image_url)
        );
        CREATE TABLE IF NOT EXISTS ingestion_runs(
          id TEXT PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ, status TEXT NOT NULL,
          urls_discovered INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL DEFAULT 0,
          removed INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, error_summary TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ingestion_pages(
          url TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT, content_hash TEXT, retry_after TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS escalations(
          id TEXT PRIMARY KEY, question TEXT NOT NULL, reason TEXT NOT NULL, evidence_json JSONB NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', approved_answer TEXT, reviewer TEXT,
          reviewed_at TIMESTAMPTZ, version INTEGER NOT NULL DEFAULT 1, expires_at TIMESTAMPTZ, request_id TEXT UNIQUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS approved_knowledge(
          id TEXT PRIMARY KEY, answer TEXT NOT NULL, evidence_json JSONB NOT NULL,
          scope TEXT NOT NULL, customer_id TEXT, approved_by TEXT NOT NULL,
          version INTEGER NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE, expires_at TIMESTAMPTZ,
          embedding vector({vector_size}) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS query_audits(
          request_id TEXT PRIMARY KEY, question_hash TEXT NOT NULL, status TEXT NOT NULL,
          evidence_json JSONB NOT NULL, model_id TEXT, prompt_version TEXT NOT NULL,
          latency_ms INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
          answer_text TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        with self._pg() as connection:
            connection.execute(schema)

    def acquire_ingestion_lease(self) -> IngestionLease:
        if self.is_sqlite:
            with _SQLITE_LOCKS_GUARD:
                lock = _SQLITE_LOCKS.setdefault(self.database_url, threading.Lock())
            acquired = lock.acquire(blocking=False)
            return IngestionLease(lock if acquired else None, sqlite_lock=lock if acquired else None)
        import psycopg
        connection = psycopg.connect(self.database_url)
        lock_key = 2026101801
        acquired = connection.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,)).fetchone()[0]
        if not acquired:
            connection.close()
            return IngestionLease(None)
        return IngestionLease(connection, lock_key=lock_key)

    def sync_manifest(self, manifest: dict[str, Any]) -> None:
        """Mirror the crawl checkpoint into relational article/chunk/image tables."""
        pages = manifest.get("pages", {})
        if self.is_sqlite:
            assert self._sqlite is not None
            connection = self._sqlite
            with connection:
                for url, page in pages.items():
                    article_id = page.get("article_id") or url
                    connection.execute(
                        """INSERT INTO articles(id,url,title,content_hash,sitemap_lastmod,status,last_ingested_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(url) DO UPDATE SET title=excluded.title,
                        content_hash=excluded.content_hash,sitemap_lastmod=excluded.sitemap_lastmod,status=excluded.status,
                        last_ingested_at=excluded.last_ingested_at,updated_at=CURRENT_TIMESTAMP""",
                        (article_id, url, page.get("title", ""), page.get("content_hash", ""), page.get("lastmod"), page.get("status", "failed"), page.get("last_ingested_at")),
                    )
                    connection.execute("UPDATE knowledge_chunks SET active=0 WHERE article_id=?", (article_id,))
                    connection.execute("UPDATE image_assets SET analysis_status='removed',updated_at=CURRENT_TIMESTAMP WHERE article_id=?", (article_id,))
                    if page.get("status") != "active":
                        continue
                    for chunk in page.get("chunks", []):
                        vector = chunk.get("embedding")
                        if not vector:
                            if self.embedding_provider != "local-test":
                                raise RuntimeError("Live indexing requires embeddings to be generated by the configured provider")
                            from app.embeddings import embed_local_test
                            vector = embed_local_test(chunk.get("content", ""), self.embedding_dimensions)
                        if len(vector) != self.embedding_dimensions:
                            raise ValueError("Chunk vector dimension does not match configured database dimension")
                        metadata = {"url": url, "title": page.get("title", ""), "image_urls": chunk.get("image_urls", [])}
                        connection.execute(
                            """INSERT INTO knowledge_chunks(id,article_id,section_heading,content,embedding,metadata_json,content_hash,active,updated_at)
                            VALUES(?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET content=excluded.content,
                            embedding=excluded.embedding,metadata_json=excluded.metadata_json,content_hash=excluded.content_hash,active=1,updated_at=CURRENT_TIMESTAMP""",
                            (chunk["chunk_id"], article_id, chunk.get("section_heading", ""), chunk.get("content", ""), json.dumps(vector), json.dumps(metadata), page.get("content_hash", "")),
                        )
                    for image in page.get("images", []):
                        image_id = image.get("id") or f"{article_id}:{image['url']}"
                        connection.execute(
                            """INSERT INTO image_assets(id,article_id,image_url,alt_text,nearby_context,description,content_hash,analysis_status,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(article_id,image_url) DO UPDATE SET
                            alt_text=excluded.alt_text,nearby_context=excluded.nearby_context,description=excluded.description,
                            content_hash=excluded.content_hash,analysis_status=excluded.analysis_status,updated_at=CURRENT_TIMESTAMP""",
                            (image_id, article_id, image["url"], image.get("alt_text", ""), image.get("nearby_context", ""), image.get("description", ""), image.get("content_hash", page.get("content_hash", "")), image.get("analysis_status", "pending")),
                        )
            return

        from app.embeddings import embed_local_test

        with self._pg() as connection:
            for url, page in pages.items():
                article_id = page.get("article_id") or url
                connection.execute(
                    """INSERT INTO articles(id,url,title,content_hash,sitemap_lastmod,status,last_ingested_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(url) DO UPDATE SET title=excluded.title,
                    content_hash=excluded.content_hash,sitemap_lastmod=excluded.sitemap_lastmod,status=excluded.status,
                    last_ingested_at=excluded.last_ingested_at,updated_at=now()""",
                    (article_id, url, page.get("title", ""), page.get("content_hash", ""), page.get("lastmod"), page.get("status", "failed"), page.get("last_ingested_at")),
                )
                connection.execute("UPDATE knowledge_chunks SET active=false WHERE article_id=%s", (article_id,))
                connection.execute("UPDATE image_assets SET analysis_status='removed',updated_at=now() WHERE article_id=%s", (article_id,))
                if page.get("status") != "active":
                    continue
                for chunk in page.get("chunks", []):
                    vector = chunk.get("embedding")
                    if not vector:
                        if self.embedding_provider != "local-test":
                            raise RuntimeError("Live indexing requires embeddings to be generated by the configured provider")
                        vector = embed_local_test(chunk.get("content", ""), self.embedding_dimensions)
                    if len(vector) != self.embedding_dimensions:
                        raise ValueError("Chunk vector dimension does not match configured database dimension")
                    metadata = {"url": url, "title": page.get("title", ""), "image_urls": chunk.get("image_urls", [])}
                    vector_literal = "[" + ",".join(str(float(x)) for x in vector) + "]"
                    connection.execute(
                        """INSERT INTO knowledge_chunks(id,article_id,section_heading,content,embedding,metadata_json,content_hash,active)
                        VALUES(%s,%s,%s,%s,%s::vector,%s::jsonb,%s,true) ON CONFLICT(id) DO UPDATE SET content=excluded.content,
                        embedding=excluded.embedding,metadata_json=excluded.metadata_json,content_hash=excluded.content_hash,active=true,updated_at=now()""",
                        (chunk["chunk_id"], article_id, chunk.get("section_heading", ""), chunk.get("content", ""), vector_literal, json.dumps(metadata), page.get("content_hash", "")),
                    )
                for image in page.get("images", []):
                    image_id = image.get("id") or f"{article_id}:{image['url']}"
                    connection.execute(
                        """INSERT INTO image_assets(id,article_id,image_url,alt_text,nearby_context,description,content_hash,analysis_status)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(article_id,image_url) DO UPDATE SET
                        alt_text=excluded.alt_text,nearby_context=excluded.nearby_context,description=excluded.description,
                        content_hash=excluded.content_hash,analysis_status=excluded.analysis_status,updated_at=now()""",
                        (image_id, article_id, image["url"], image.get("alt_text", ""), image.get("nearby_context", ""), image.get("description", ""), image.get("content_hash", page.get("content_hash", "")), image.get("analysis_status", "pending")),
                    )

    def search_chunks(self, vector: list[float], limit: int = 6) -> list[dict[str, Any]]:
        if len(vector) != self.embedding_dimensions:
            raise ValueError("Query vector dimension does not match configured database dimension")
        if self.is_sqlite:
            assert self._sqlite is not None
            rows = self._sqlite.execute(
                """SELECT c.id,c.article_id,c.section_heading,c.content,c.embedding,c.metadata_json,a.url,a.title
                FROM knowledge_chunks c JOIN articles a ON a.id=c.article_id
                WHERE c.active=1 AND a.status='active'"""
            ).fetchall()
            return [
                {"chunk_id": row["id"], "article_id": row["article_id"], "section_heading": row["section_heading"],
                 "content": row["content"], "embedding": json.loads(row["embedding"]), "metadata": json.loads(row["metadata_json"]),
                 "url": row["url"], "title": row["title"]}
                for row in rows
            ]
        vector_literal = "[" + ",".join(str(float(x)) for x in vector) + "]"
        with self._pg() as connection:
            rows = connection.execute(
                """SELECT c.id,c.article_id,c.section_heading,c.content,c.embedding::text AS embedding,c.metadata_json,
                a.url,a.title,(c.embedding <=> %s::vector) AS distance FROM knowledge_chunks c
                JOIN articles a ON a.id=c.article_id WHERE c.active=true AND a.status='active'
                ORDER BY c.embedding <=> %s::vector LIMIT %s""",
                (vector_literal, vector_literal, limit),
            ).fetchall()
        return [
            {"chunk_id": row[0], "article_id": row[1], "section_heading": row[2], "content": row[3],
             "embedding": json.loads(row[4].replace(" ", ",")) if isinstance(row[4], str) and not row[4].startswith("[") else row[4],
             "metadata": row[5], "url": row[6], "title": row[7], "vector_score": 1 - float(row[8])}
            for row in rows
        ]

    def get_image_references(self, article_id: str, urls: list[str]) -> list[dict[str, str]]:
        if not urls:
            return []
        if self.is_sqlite:
            assert self._sqlite is not None
            placeholders = ",".join("?" for _ in urls)
            rows = self._sqlite.execute(
                f"SELECT image_url,alt_text,description,analysis_status FROM image_assets WHERE article_id=? AND image_url IN ({placeholders})",
                (article_id, *urls),
            ).fetchall()
            return [{"url": row[0], "alt_text": row[1], "description": row[2], "analysis_status": row[3]} for row in rows]
        with self._pg() as connection:
            rows = connection.execute(
                "SELECT image_url,alt_text,description,analysis_status FROM image_assets WHERE article_id=%s AND image_url = ANY(%s)",
                (article_id, urls),
            ).fetchall()
        return [{"url": row[0], "alt_text": row[1], "description": row[2], "analysis_status": row[3]} for row in rows]

    def search_approved_knowledge(self, vector: list[float], customer_id: str | None) -> list[dict[str, Any]]:
        if len(vector) != self.embedding_dimensions:
            raise ValueError("Query vector dimension does not match configured database dimension")
        if self.is_sqlite:
            assert self._sqlite is not None
            rows = self._sqlite.execute(
                """SELECT id,answer,evidence_json,scope,customer_id,approved_by,version,embedding FROM approved_knowledge
                WHERE active=1 AND (expires_at IS NULL OR expires_at>CURRENT_TIMESTAMP)
                AND (scope='global' OR (? IS NOT NULL AND scope='customer' AND customer_id=?))""",
                (customer_id, customer_id),
            ).fetchall()
            return [
                {"id": row[0], "answer": row[1], "evidence": json.loads(row[2]), "scope": row[3], "customer_id": row[4],
                 "approved_by": row[5], "version": row[6], "embedding": json.loads(row[7])}
                for row in rows
            ]
        vector_literal = "[" + ",".join(str(float(x)) for x in vector) + "]"
        with self._pg() as connection:
            rows = connection.execute(
                """SELECT id,answer,evidence_json,scope,customer_id,approved_by,version,embedding::text AS embedding
                FROM approved_knowledge WHERE active=true AND (expires_at IS NULL OR expires_at>now())
                AND (scope='global' OR (%s IS NOT NULL AND scope='customer' AND customer_id=%s))
                ORDER BY embedding <=> %s::vector LIMIT 20""",
                (customer_id, customer_id, vector_literal),
            ).fetchall()
        return [
            {"id": row[0], "answer": row[1], "evidence": row[2], "scope": row[3], "customer_id": row[4],
             "approved_by": row[5], "version": row[6], "embedding": json.loads(row[7])}
            for row in rows
        ]

    def source_is_active(self, url: str) -> bool:
        if self.is_sqlite:
            assert self._sqlite is not None
            row = self._sqlite.execute("SELECT 1 FROM articles WHERE url=? AND status='active'", (url,)).fetchone()
            return row is not None
        with self._pg() as connection:
            row = connection.execute("SELECT 1 FROM articles WHERE url=%s AND status='active'", (url,)).fetchone()
        return row is not None

    def sync_ingestion(self, manifest: dict[str, Any]) -> None:
        runs = manifest.get("runs", [])
        pages = manifest.get("pages", {})
        if self.is_sqlite:
            assert self._sqlite is not None
            with self._sqlite:
                for run in runs:
                    self._sqlite.execute(
                        """INSERT OR REPLACE INTO ingestion_runs(id,started_at,finished_at,status,urls_discovered,created,updated,removed,failed,error_summary)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (run["run_id"], run["started_at"], run.get("finished_at"), run.get("status", "unknown"), run.get("discovered", 0), run.get("created", 0), run.get("updated", 0), run.get("removed", 0), run.get("failed", 0), "\n".join(run.get("errors", []))),
                    )
                for url, page in pages.items():
                    self._sqlite.execute(
                        """INSERT INTO ingestion_pages(url,status,attempts,last_error,content_hash,retry_after,updated_at)
                        VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(url) DO UPDATE SET status=excluded.status,
                        attempts=excluded.attempts,last_error=excluded.last_error,content_hash=excluded.content_hash,
                        retry_after=excluded.retry_after,updated_at=CURRENT_TIMESTAMP""",
                        (url, page.get("status", "failed"), page.get("attempts", 0), page.get("last_error"), page.get("content_hash"), page.get("retry_after")),
                    )
            return
        with self._pg() as connection:
            for run in runs:
                connection.execute(
                    """INSERT INTO ingestion_runs(id,started_at,finished_at,status,urls_discovered,created,updated,removed,failed,error_summary)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET finished_at=excluded.finished_at,
                    status=excluded.status,urls_discovered=excluded.urls_discovered,created=excluded.created,updated=excluded.updated,
                    removed=excluded.removed,failed=excluded.failed,error_summary=excluded.error_summary""",
                    (run["run_id"], run["started_at"], run.get("finished_at"), run.get("status", "unknown"), run.get("discovered", 0), run.get("created", 0), run.get("updated", 0), run.get("removed", 0), run.get("failed", 0), "\n".join(run.get("errors", []))),
                )
            for url, page in pages.items():
                connection.execute(
                    """INSERT INTO ingestion_pages(url,status,attempts,last_error,content_hash,retry_after)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(url) DO UPDATE SET status=excluded.status,
                    attempts=excluded.attempts,last_error=excluded.last_error,content_hash=excluded.content_hash,
                    retry_after=excluded.retry_after,updated_at=now()""",
                    (url, page.get("status", "failed"), page.get("attempts", 0), page.get("last_error"), page.get("content_hash"), page.get("retry_after")),
                )

    def create_escalation(self, question: str, reason: str, evidence: list[dict[str, Any]], request_id: str) -> str:
        from uuid import uuid4
        escalation_id = str(uuid4())
        if self.is_sqlite:
            assert self._sqlite is not None
            self._sqlite.execute(
                "INSERT OR IGNORE INTO escalations(id,question,reason,evidence_json,request_id) VALUES(?,?,?,?,?)",
                (escalation_id, question, reason, json.dumps(evidence), request_id),
            )
            self._sqlite.commit()
            row = self._sqlite.execute("SELECT id FROM escalations WHERE request_id=?", (request_id,)).fetchone()
            return row["id"]
        with self._pg() as connection:
            row = connection.execute(
                """INSERT INTO escalations(id,question,reason,evidence_json,request_id) VALUES(%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT(request_id) DO UPDATE SET request_id=excluded.request_id RETURNING id""",
                (escalation_id, question, reason, json.dumps(evidence), request_id),
            ).fetchone()
        return str(row[0])

    def record_query_audit(
        self,
        request_id: str,
        question_hash: str,
        status: str,
        evidence: list[dict[str, Any]],
        model_id: str | None,
        prompt_version: str,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        answer_text: str,
    ) -> None:
        summary = [{"chunk_id": item.get("chunk_id"), "url": item.get("url"), "score": item.get("score")} for item in evidence]
        if self.is_sqlite:
            assert self._sqlite is not None
            self._sqlite.execute(
                """INSERT OR REPLACE INTO query_audits(request_id,question_hash,status,evidence_json,model_id,prompt_version,
                latency_ms,input_tokens,output_tokens,answer_text) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (request_id, question_hash, status, json.dumps(summary), model_id, prompt_version, latency_ms, input_tokens, output_tokens, answer_text),
            )
            self._sqlite.commit()
            return
        with self._pg() as connection:
            connection.execute(
                """INSERT INTO query_audits(request_id,question_hash,status,evidence_json,model_id,prompt_version,latency_ms,input_tokens,output_tokens,answer_text)
                VALUES(%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s) ON CONFLICT(request_id) DO UPDATE SET status=excluded.status,
                evidence_json=excluded.evidence_json,model_id=excluded.model_id,latency_ms=excluded.latency_ms,
                input_tokens=excluded.input_tokens,output_tokens=excluded.output_tokens,answer_text=excluded.answer_text""",
                (request_id, question_hash, status, json.dumps(summary), model_id, prompt_version, latency_ms, input_tokens, output_tokens, answer_text),
            )

    def list_escalations(self, include_resolved: bool = False) -> list[dict[str, Any]]:
        clause = "" if include_resolved else " WHERE status='open'"
        if self.is_sqlite:
            assert self._sqlite is not None
            rows = self._sqlite.execute("SELECT * FROM escalations" + clause + " ORDER BY created_at DESC").fetchall()
            return [{**dict(row), "evidence": json.loads(row["evidence_json"])} for row in rows]
        with self._pg() as connection:
            rows = connection.execute("SELECT * FROM escalations" + clause + " ORDER BY created_at DESC").fetchall()
        names = ["id", "question", "reason", "evidence_json", "status", "approved_answer", "reviewer", "reviewed_at", "version", "expires_at", "request_id", "created_at"]
        return [{**dict(zip(names, row)), "evidence": row[3]} for row in rows]

    def resolve_escalation(self, escalation_id: str, answer: str, reviewer: str, scope: str, customer_id: str | None, vector: list[float], expires_at: str | None = None) -> bool:
        if len(vector) != self.embedding_dimensions:
            raise ValueError("Approved knowledge vector dimension does not match configured database dimension")
        if self.is_sqlite:
            assert self._sqlite is not None
            cursor = self._sqlite.execute(
                "UPDATE escalations SET status='resolved',approved_answer=?,reviewer=?,reviewed_at=CURRENT_TIMESTAMP,version=version+1 WHERE id=? AND status='open'",
                (answer, reviewer, escalation_id),
            )
            if cursor.rowcount != 1:
                self._sqlite.rollback()
                return False
            row = self._sqlite.execute("SELECT evidence_json,version FROM escalations WHERE id=?", (escalation_id,)).fetchone()
            self._sqlite.execute(
                "INSERT INTO approved_knowledge(id,answer,evidence_json,scope,customer_id,approved_by,version,expires_at,embedding) VALUES(?,?,?,?,?,?,?,?,?)",
                (f"approved:{escalation_id}", answer, row["evidence_json"], scope, customer_id, reviewer, row["version"], expires_at, json.dumps(vector)),
            )
            self._sqlite.commit()
            return True
        vector_literal = "[" + ",".join(str(float(x)) for x in vector) + "]"
        with self._pg() as connection:
            row = connection.execute(
                "UPDATE escalations SET status='resolved',approved_answer=%s,reviewer=%s,reviewed_at=now(),version=version+1 WHERE id=%s AND status='open' RETURNING evidence_json,version",
                (answer, reviewer, escalation_id),
            ).fetchone()
            if not row:
                return False
            connection.execute(
                "INSERT INTO approved_knowledge(id,answer,evidence_json,scope,customer_id,approved_by,version,expires_at,embedding) VALUES(%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s::vector)",
                (f"approved:{escalation_id}", answer, json.dumps(row[0]), scope, customer_id, reviewer, row[1], expires_at, vector_literal),
            )
        return True

    def close(self) -> None:
        if self._sqlite is not None:
            self._sqlite.close()
            self._sqlite = None


def store_from_settings() -> KnowledgeStore:
    from app.config import get_settings
    settings = get_settings()
    store = KnowledgeStore(settings.database_url, settings.embedding_dimensions, settings.embedding_provider)
    store.initialize()
    return store


if __name__ == "__main__":
    from app.config import get_settings
    settings = get_settings()
    KnowledgeStore(settings.database_url, settings.embedding_dimensions, settings.embedding_provider).initialize()
    print("Knowledge Brain database schema is initialized.")

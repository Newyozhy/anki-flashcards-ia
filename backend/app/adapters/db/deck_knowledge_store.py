import contextlib
import json
import math
import os
import re
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "deck_knowledge.db"


def _cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


class DeckKnowledgeStore:
    """SQLite-backed persistent store for semantic deck embeddings and knowledge index."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self._db_path = Path(db_path)
            if self._db_path != Path(":memory:") and self._db_path.parent:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._db_path = DEFAULT_DB_PATH

        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create required tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deck_metadata (
                    deck_name TEXT PRIMARY KEY,
                    last_indexed_at TEXT,
                    total_notes INTEGER DEFAULT 0,
                    topic_overview TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_notes (
                    deck_name TEXT,
                    note_id INTEGER,
                    tags TEXT,
                    front TEXT,
                    back TEXT,
                    explanation TEXT,
                    clean_text TEXT,
                    embedding BLOB,
                    updated_at TEXT,
                    quality_status TEXT DEFAULT 'unreviewed',
                    quality_score REAL DEFAULT NULL,
                    quality_feedback TEXT DEFAULT NULL,
                    audited_at TEXT DEFAULT NULL,
                    PRIMARY KEY(deck_name, note_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_indexed_notes_deck ON indexed_notes(deck_name)"
            )

            # Defensive schema migration for existing databases (MUST run before creating indexes on these columns)
            for col_name, col_def in [
                ("quality_status", "TEXT DEFAULT 'unreviewed'"),
                ("quality_score", "REAL DEFAULT NULL"),
                ("quality_feedback", "TEXT DEFAULT NULL"),
                ("audited_at", "TEXT DEFAULT NULL"),
                ("cluster_name", "TEXT DEFAULT NULL"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE indexed_notes ADD COLUMN {col_name} {col_def}")
                except sqlite3.OperationalError:
                    pass

            try:
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_indexed_notes_quality ON indexed_notes(deck_name, quality_status)"
                )
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_indexed_notes_cluster ON indexed_notes(deck_name, cluster_name)"
                )
            except sqlite3.OperationalError:
                pass

            # Canonical quality state migration: map legacy 'debt' and 'broken' to 'bad'
            try:
                cursor.execute(
                    "UPDATE indexed_notes SET quality_status = 'bad' WHERE quality_status IN ('debt', 'broken')"
                )
            except sqlite3.OperationalError:
                pass

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deck_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_name TEXT NOT NULL,
                    cluster_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    scope TEXT,
                    note_ids TEXT,
                    centroid_note_ids TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_deck_clusters_deck ON deck_clusters(deck_name)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS thematic_coverage_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_name TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    description TEXT,
                    coverage_percentage INTEGER DEFAULT 0,
                    covered_facets TEXT,
                    orphan_gaps TEXT,
                    summary_assessment TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_thematic_audits_deck ON thematic_coverage_audits(deck_name)"
            )

            # Concept DAG Tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS concept_nodes (
                    deck_name TEXT NOT NULL,
                    id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    taxonomy_path TEXT DEFAULT 'general',
                    description TEXT,
                    depth_level INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'RAW',
                    is_in_scope INTEGER DEFAULT 1,
                    stage_id TEXT DEFAULT 'stage_1',
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (deck_name, id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_nodes_deck ON concept_nodes(deck_name)"
            )

            # Defensive migration for existing concept_nodes tables
            for col_name, col_def in [
                ("status", "TEXT DEFAULT 'RAW'"),
                ("is_in_scope", "INTEGER DEFAULT 1"),
                ("stage_id", "TEXT DEFAULT 'stage_1'"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE concept_nodes ADD COLUMN {col_name} {col_def}")
                except sqlite3.OperationalError:
                    pass
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_nodes_stage ON concept_nodes(deck_name, stage_id)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS concept_edges (
                    deck_name TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL DEFAULT 'requires',
                    PRIMARY KEY (deck_name, source_id, target_id, relation_type)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_edges_deck ON concept_edges(deck_name)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS card_concept_mappings (
                    deck_name TEXT NOT NULL,
                    note_id INTEGER NOT NULL,
                    concept_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'target',
                    PRIMARY KEY (deck_name, note_id, concept_id, role)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_concept_deck ON card_concept_mappings(deck_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_concept_note ON card_concept_mappings(deck_name, note_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_concept_concept ON card_concept_mappings(deck_name, concept_id)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS note_extracted_knowledge (
                    deck_name TEXT NOT NULL,
                    note_id INTEGER NOT NULL,
                    raw_front TEXT,
                    raw_back TEXT,
                    extracted_facts TEXT,
                    target_concepts TEXT,
                    assumed_prerequisites TEXT,
                    taxonomy_path TEXT,
                    extracted_at TEXT,
                    PRIMARY KEY (deck_name, note_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_extracted_deck ON note_extracted_knowledge(deck_name)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deck_learning_contracts (
                    deck_name TEXT PRIMARY KEY,
                    contract_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sanitation_coverage_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_name TEXT NOT NULL,
                    source_sanitized_note_id INTEGER NOT NULL,
                    colliding_pending_note_id INTEGER NOT NULL,
                    covered_concept_title TEXT NOT NULL,
                    covered_facet_summary TEXT,
                    created_atomic_note_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_ledger_pending_note ON sanitation_coverage_ledger(deck_name, colliding_pending_note_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_ledger_deck ON sanitation_coverage_ledger(deck_name)"
            )

            # Unify preevaluated status to optimal across all notes
            cursor.execute(
                "UPDATE indexed_notes SET quality_status = 'optimal' WHERE quality_status = 'preevaluated'"
            )
            conn.commit()


    def get_indexed_note_ids(self, deck_name: str) -> Set[int]:
        """Return the set of note IDs currently indexed for the given deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT note_id FROM indexed_notes WHERE deck_name = ?",
                (deck_name,),
            )
            rows = cursor.fetchall()
            return {row["note_id"] for row in rows}

    def save_note_embeddings(self, deck_name: str, notes: List[Dict]) -> None:
        """Store or update note records with packed float32 vector embeddings."""
        if not notes:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        records_to_insert = []

        for note in notes:
            nid = int(note["note_id"])
            front = note.get("front", "") or ""
            back = note.get("back", "") or ""
            explanation = note.get("explanation") or ""
            clean_text = note.get("clean_text") or f"{front} | {back}".strip()

            tags_val = note.get("tags", [])
            if isinstance(tags_val, (list, set)):
                tags_str = json.dumps(list(tags_val))
            else:
                tags_str = str(tags_val)

            embedding_list = note.get("embedding")
            if embedding_list and len(embedding_list) > 0:
                blob = struct.pack(f"{len(embedding_list)}f", *embedding_list)
            else:
                blob = None

            quality_status = note.get("quality_status") or "unreviewed"
            if quality_status in ("debt", "broken"):
                quality_status = "bad"
            quality_score = note.get("quality_score")
            quality_feedback = note.get("quality_feedback")
            audited_at = note.get("audited_at")

            records_to_insert.append(
                (
                    deck_name,
                    nid,
                    tags_str,
                    front,
                    back,
                    explanation,
                    clean_text,
                    blob,
                    now_iso,
                    quality_status,
                    quality_score,
                    quality_feedback,
                    audited_at,
                )
            )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Purge any previous records for same deck with identical front & back but different note_id
            for rec in records_to_insert:
                cursor.execute(
                    "DELETE FROM indexed_notes WHERE deck_name = ? AND front = ? AND back = ? AND note_id != ?",
                    (rec[0], rec[3], rec[4], rec[1]),
                )
            cursor.executemany(
                """
                INSERT INTO indexed_notes (
                    deck_name, note_id, tags, front, back, explanation, clean_text, embedding, updated_at,
                    quality_status, quality_score, quality_feedback, audited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_name, note_id) DO UPDATE SET
                    tags = excluded.tags,
                    front = excluded.front,
                    back = excluded.back,
                    explanation = excluded.explanation,
                    clean_text = excluded.clean_text,
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at,
                    quality_status = CASE
                        WHEN excluded.quality_status IS NOT NULL AND excluded.quality_status != 'unreviewed'
                        THEN (CASE WHEN excluded.quality_status IN ('debt', 'broken') THEN 'bad' ELSE excluded.quality_status END)
                        ELSE (CASE WHEN indexed_notes.quality_status IN ('debt', 'broken') THEN 'bad' ELSE indexed_notes.quality_status END)
                    END,
                    quality_score = COALESCE(excluded.quality_score, indexed_notes.quality_score),
                    quality_feedback = COALESCE(excluded.quality_feedback, indexed_notes.quality_feedback),
                    audited_at = COALESCE(excluded.audited_at, indexed_notes.audited_at)
                """,
                records_to_insert,
            )

            # Update deck_metadata total count and last indexed timestamp
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM indexed_notes WHERE deck_name = ?",
                (deck_name,),
            )
            total_notes = cursor.fetchone()["cnt"]

            cursor.execute(
                """
                INSERT OR REPLACE INTO deck_metadata (deck_name, last_indexed_at, total_notes)
                VALUES (?, ?, ?)
                """,
                (deck_name, now_iso, total_notes),
            )
            conn.commit()

    def delete_note_embeddings(self, deck_name: str, note_ids: List[int]) -> None:
        """Remove obsolete or superseded note records from SQLite index and update metadata count."""
        if not note_ids:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in note_ids)
        query = f"DELETE FROM indexed_notes WHERE deck_name = ? AND note_id IN ({placeholders})"
        params = [deck_name] + [int(nid) for nid in note_ids]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            # Re-compute total count for deck_metadata
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM indexed_notes WHERE deck_name = ?",
                (deck_name,),
            )
            total_notes = cursor.fetchone()["cnt"]

            cursor.execute(
                """
                INSERT OR REPLACE INTO deck_metadata (deck_name, last_indexed_at, total_notes)
                VALUES (?, ?, ?)
                """,
                (deck_name, now_iso, total_notes),
            )
            conn.commit()

    def semantic_search(
        self,
        deck_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.4,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Perform cosine similarity vector search over the indexed notes of a deck."""
        if not query_embedding:
            return []

        exclude_set = set(exclude_note_ids) if exclude_note_ids else set()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, tags, front, back, explanation, clean_text, embedding,
                       quality_status, quality_score, quality_feedback, audited_at
                FROM indexed_notes
                WHERE deck_name = ? AND embedding IS NOT NULL
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        candidates = []
        for row in rows:
            if exclude_set and row["note_id"] in exclude_set:
                continue

            blob = row["embedding"]
            if not blob:
                continue

            num_floats = len(blob) // 4
            if num_floats != len(query_embedding):
                continue

            stored_vec = struct.unpack(f"{num_floats}f", blob)
            sim = _cosine_similarity(query_embedding, stored_vec)

            if sim >= min_similarity:
                tags_raw = row["tags"] or ""
                try:
                    tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
                except Exception:
                    tags = [tags_raw]

                q_status = row["quality_status"] or "unreviewed"
                if q_status in ("debt", "broken"):
                    q_status = "bad"

                candidates.append(
                    {
                        "note_id": row["note_id"],
                        "similarity": round(float(sim), 4),
                        "front": row["front"],
                        "back": row["back"],
                        "explanation": row["explanation"],
                        "tags": tags,
                        "clean_text": row["clean_text"],
                        "quality_status": q_status,
                        "quality_score": row["quality_score"],
                        "quality_feedback": row["quality_feedback"],
                        "audited_at": row["audited_at"],
                    }
                )

        # Sort descending by similarity
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:top_k]

    def search_similar(
        self,
        deck_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.4,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Convenience alias for semantic_search."""
        return self.semantic_search(
            deck_name=deck_name,
            query_embedding=query_embedding,
            top_k=top_k,
            min_similarity=min_similarity,
            exclude_note_ids=exclude_note_ids,
        )

    def get_deck_stats(self, deck_name: str) -> Dict:
        """Return indexing statistics and honest quality distribution for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT total_notes, last_indexed_at FROM deck_metadata WHERE deck_name = ?",
                (deck_name,),
            )
            meta = cursor.fetchone()
            last_indexed_at = meta["last_indexed_at"] if meta else None

            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_notes,
                    SUM(CASE WHEN quality_status IS NOT NULL AND quality_status != 'unreviewed' THEN 1 ELSE 0 END) as audited_count,
                    SUM(CASE WHEN quality_status = 'unreviewed' OR quality_status IS NULL THEN 1 ELSE 0 END) as unreviewed_count,
                    SUM(CASE WHEN quality_status = 'preevaluated' THEN 1 ELSE 0 END) as preevaluated_count,
                    SUM(CASE WHEN quality_status = 'optimal' THEN 1 ELSE 0 END) as optimal_count,
                    SUM(CASE WHEN quality_status IN ('bad', 'debt', 'broken') THEN 1 ELSE 0 END) as bad_count,
                    SUM(CASE WHEN quality_status IN ('bad', 'debt') THEN 1 ELSE 0 END) as debt_count,
                    SUM(CASE WHEN quality_status = 'broken' THEN 1 ELSE 0 END) as broken_count
                FROM indexed_notes
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            row = cursor.fetchone()
            total_indexed = row["total_notes"] if row and row["total_notes"] is not None else (meta["total_notes"] if meta else 0)
            audited_count = row["audited_count"] or 0 if row else 0
            unreviewed_count = row["unreviewed_count"] or 0 if row else 0
            preevaluated_count = row["preevaluated_count"] or 0 if row else 0
            optimal_count = row["optimal_count"] or 0 if row else 0
            bad_count = row["bad_count"] or 0 if row else 0
            debt_count = row["debt_count"] or 0 if row else 0
            broken_count = row["broken_count"] or 0 if row else 0

            health_pct = round(((optimal_count + preevaluated_count) / audited_count) * 100, 1) if audited_count > 0 else 0.0

            return {
                "deck_name": deck_name,
                "total_indexed": total_indexed,
                "last_indexed_at": last_indexed_at,
                "audited_count": audited_count,
                "unreviewed_count": unreviewed_count,
                "preevaluated_count": preevaluated_count,
                "optimal_count": optimal_count,
                "bad_count": bad_count,
                "debt_count": bad_count if bad_count > 0 else debt_count,
                "broken_count": broken_count,
                "deck_health_percentage": health_pct,
            }

    def update_note_quality(
        self,
        deck_name: str,
        note_id: int,
        quality_status: str,
        quality_score: Optional[float] = None,
        quality_feedback: Optional[str] = None,
        audited_at: Optional[str] = None,
    ) -> bool:
        """Update quality status and audit feedback for a specific note."""
        now_iso = audited_at or datetime.now(timezone.utc).isoformat()
        normalized_status = "bad" if quality_status in ("debt", "broken") else quality_status
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE indexed_notes
                SET quality_status = ?,
                    quality_score = ?,
                    quality_feedback = ?,
                    audited_at = ?,
                    updated_at = ?
                WHERE deck_name = ? AND note_id = ?
                """,
                (
                    normalized_status,
                    quality_score,
                    quality_feedback,
                    now_iso,
                    now_iso,
                    deck_name,
                    int(note_id),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_notes_quality_batch(
        self,
        deck_name: str,
        audit_results: List[Dict],
    ) -> int:
        """Batch update quality evaluations for notes."""
        if not audit_results:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        params = []
        for res in audit_results:
            if "note_id" not in res:
                continue
            qs = res.get("quality_status", "unreviewed")
            if qs in ("debt", "broken"):
                qs = "bad"
            params.append((
                qs,
                res.get("quality_score"),
                res.get("quality_feedback"),
                res.get("audited_at") or now_iso,
                now_iso,
                deck_name,
                int(res["note_id"]),
            ))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                UPDATE indexed_notes
                SET quality_status = ?,
                    quality_score = ?,
                    quality_feedback = ?,
                    audited_at = ?,
                    updated_at = ?
                WHERE deck_name = ? AND note_id = ?
                """,
                params,
            )
            conn.commit()
            return cursor.rowcount

    def mark_notes_optimal(
        self,
        deck_name: str,
        note_ids: List[int],
    ) -> int:
        """Mark newly created/exported notes as 'optimal' with default optimal score."""
        if not note_ids:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in note_ids)
            cursor.execute(
                f"""
                UPDATE indexed_notes
                SET quality_status = 'optimal',
                    quality_score = COALESCE(quality_score, 1.0),
                    quality_feedback = COALESCE(quality_feedback, 'Generada por IA de forma atómica y pre-evaluada por diseño.'),
                    audited_at = COALESCE(audited_at, ?),
                    updated_at = ?
                WHERE deck_name = ? AND note_id IN ({placeholders})
                """,
                [now_iso, now_iso, deck_name] + [int(nid) for nid in note_ids],
            )
            for nid in note_ids:
                cursor.execute(
                    """
                    INSERT INTO indexed_notes (
                        deck_name, note_id, quality_status, quality_score, quality_feedback, audited_at, updated_at
                    ) VALUES (?, ?, 'optimal', 1.0, 'Generada por IA de forma atómica y pre-evaluada por diseño.', ?, ?)
                    ON CONFLICT(deck_name, note_id) DO UPDATE SET
                        quality_status = 'optimal',
                        quality_score = COALESCE(indexed_notes.quality_score, 1.0),
                        quality_feedback = COALESCE(indexed_notes.quality_feedback, 'Generada por IA de forma atómica y pre-evaluada por diseño.')
                    """,
                    (deck_name, int(nid), now_iso, now_iso),
                )
            conn.commit()
            return len(note_ids)

    def mark_notes_preevaluated(
        self,
        deck_name: str,
        note_ids: List[int],
    ) -> int:
        """Alias for mark_notes_optimal following H-08 / Decision 3 unification."""
        return self.mark_notes_optimal(deck_name, note_ids)

    def get_notes_for_audit(
        self,
        deck_name: str,
        limit: int = 5,
        note_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Fetch notes pending quality evaluation or specific note IDs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if note_ids:
                placeholders = ",".join("?" for _ in note_ids)
                query = f"""
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE deck_name = ? AND note_id IN ({placeholders})
                ORDER BY note_id ASC
                """
                params = [deck_name] + [int(nid) for nid in note_ids]
                cursor.execute(query, params)
            else:
                query = """
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE deck_name = ? AND (quality_status = 'unreviewed' OR quality_status IS NULL)
                ORDER BY note_id ASC
                LIMIT ?
                """
                cursor.execute(query, (deck_name, limit))
            rows = cursor.fetchall()

        result = []
        for row in rows:
            tags_raw = row["tags"] or ""
            try:
                tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
            except Exception:
                tags = [tags_raw]

            result.append(
                {
                    "note_id": row["note_id"],
                    "tags": tags,
                    "front": row["front"] or "",
                    "back": row["back"] or "",
                    "explanation": row["explanation"] or "",
                    "clean_text": row["clean_text"] or "",
                    "quality_status": "bad" if row["quality_status"] in ("debt", "broken") else (row["quality_status"] or "unreviewed"),
                    "quality_score": row["quality_score"],
                    "quality_feedback": row["quality_feedback"],
                    "audited_at": row["audited_at"],
                    "cluster_name": row["cluster_name"],
                }
            )
        return result

    def save_coverage_audit(
        self,
        deck_name: str,
        topic: str,
        description: Optional[str],
        coverage_percentage: int,
        covered_facets: List[Dict],
        orphan_gaps: List[Dict],
        summary_assessment: str,
    ) -> int:
        """Persist a thematic coverage audit and return its generated ID."""
        now_iso = datetime.now(timezone.utc).isoformat()
        facets_json = json.dumps(covered_facets, ensure_ascii=False)
        gaps_json = json.dumps(orphan_gaps, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO thematic_coverage_audits (
                    deck_name, topic, description, coverage_percentage,
                    covered_facets, orphan_gaps, summary_assessment,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deck_name,
                    topic,
                    description or "",
                    coverage_percentage,
                    facets_json,
                    gaps_json,
                    summary_assessment,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def list_coverage_audits(self, deck_name: str) -> List[Dict]:
        """Retrieve all thematic coverage audits for a deck, ordered by newest first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, topic, description, coverage_percentage,
                       covered_facets, orphan_gaps, summary_assessment, created_at, updated_at
                FROM thematic_coverage_audits
                WHERE deck_name = ?
                ORDER BY id DESC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        audits = []
        for r in rows:
            facets = []
            if r["covered_facets"]:
                try:
                    facets = json.loads(r["covered_facets"])
                except Exception:
                    facets = []
            gaps = []
            if r["orphan_gaps"]:
                try:
                    gaps = json.loads(r["orphan_gaps"])
                except Exception:
                    gaps = []

            audits.append(
                {
                    "id": r["id"],
                    "deck_name": r["deck_name"],
                    "topic": r["topic"],
                    "description": r["description"],
                    "coverage_percentage": r["coverage_percentage"],
                    "covered_facets": facets,
                    "orphan_gaps": gaps,
                    "summary_assessment": r["summary_assessment"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return audits

    def get_coverage_audit(self, audit_id: int) -> Optional[Dict]:
        """Fetch a single thematic coverage audit by ID with parsed JSON fields."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, topic, description, coverage_percentage,
                       covered_facets, orphan_gaps, summary_assessment, created_at, updated_at
                FROM thematic_coverage_audits
                WHERE id = ?
                """,
                (audit_id,),
            )
            r = cursor.fetchone()

        if not r:
            return None

        facets = []
        if r["covered_facets"]:
            try:
                facets = json.loads(r["covered_facets"])
            except Exception:
                facets = []
        gaps = []
        if r["orphan_gaps"]:
            try:
                gaps = json.loads(r["orphan_gaps"])
            except Exception:
                gaps = []

        return {
            "id": r["id"],
            "deck_name": r["deck_name"],
            "topic": r["topic"],
            "description": r["description"],
            "coverage_percentage": r["coverage_percentage"],
            "covered_facets": facets,
            "orphan_gaps": gaps,
            "summary_assessment": r["summary_assessment"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def update_gap_status(
        self,
        audit_id: int,
        gap_index: int,
        status: str,
        generated_note_id: Optional[int] = None,
    ) -> bool:
        """Update resolution status and optional generated note ID of a specific orphan gap."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT orphan_gaps FROM thematic_coverage_audits WHERE id = ?",
                (audit_id,),
            )
            r = cursor.fetchone()
            if not r or not r["orphan_gaps"]:
                return False

            try:
                gaps = json.loads(r["orphan_gaps"])
            except Exception:
                return False

            if gap_index < 0 or gap_index >= len(gaps):
                return False

            gaps[gap_index]["status"] = status
            if generated_note_id is not None:
                gaps[gap_index]["generated_note_id"] = generated_note_id

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE thematic_coverage_audits
                SET orphan_gaps = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(gaps, ensure_ascii=False), now_iso, audit_id),
            )
            conn.commit()
            return True

    def get_all_indexed_notes(self, deck_name: str) -> List[Dict]:
        """Fetch all indexed notes for a deck without BLOB embeddings for lightweight map building."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE deck_name = ?
                ORDER BY note_id ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        result = []
        for row in rows:
            tags_raw = row["tags"] or ""
            try:
                tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
            except Exception:
                tags = [tags_raw]

            result.append(
                {
                    "note_id": row["note_id"],
                    "tags": tags,
                    "front": row["front"] or "",
                    "back": row["back"] or "",
                    "explanation": row["explanation"] or "",
                    "clean_text": row["clean_text"] or "",
                    "quality_status": "bad" if row["quality_status"] in ("debt", "broken") else (row["quality_status"] or "unreviewed"),
                    "quality_score": row["quality_score"],
                    "quality_feedback": row["quality_feedback"],
                    "audited_at": row["audited_at"],
                    "cluster_name": row["cluster_name"],
                }
            )
        return result

    def get_indexed_note(self, note_id: int) -> Optional[Dict]:
        """Fetch indexed note record by note_id if present in SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, deck_name, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE note_id = ?
                """,
                (note_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        raw_status = row["quality_status"] or "unreviewed"
        canonical_status = "bad" if raw_status in ("debt", "broken") else raw_status
        tags_raw = row["tags"] or ""
        try:
            tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
        except Exception:
            tags = [tags_raw]
        return {
            "note_id": row["note_id"],
            "deck_name": row["deck_name"],
            "tags": tags,
            "front": row["front"] or "",
            "back": row["back"] or "",
            "explanation": row["explanation"] or "",
            "clean_text": row["clean_text"] or "",
            "quality_status": canonical_status,
            "quality_score": row["quality_score"],
            "quality_feedback": row["quality_feedback"],
            "audited_at": row["audited_at"],
            "cluster_name": row["cluster_name"],
        }

    def get_all_notes_with_embeddings(self, deck_name: str) -> List[Dict]:
        """Fetch all indexed notes for a deck including unpacked float32 embeddings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at,
                       cluster_name, embedding
                FROM indexed_notes
                WHERE deck_name = ? AND embedding IS NOT NULL
                ORDER BY note_id ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        result = []
        for row in rows:
            blob = row["embedding"]
            if not blob:
                continue
            num_floats = len(blob) // 4
            vec = list(struct.unpack(f"{num_floats}f", blob))
            tags_raw = row["tags"] or ""
            try:
                tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
            except Exception:
                tags = [tags_raw]

            result.append(
                {
                    "note_id": row["note_id"],
                    "tags": tags,
                    "front": row["front"] or "",
                    "back": row["back"] or "",
                    "explanation": row["explanation"] or "",
                    "clean_text": row["clean_text"] or "",
                    "quality_status": "bad" if row["quality_status"] in ("debt", "broken") else (row["quality_status"] or "unreviewed"),
                    "quality_score": row["quality_score"],
                    "quality_feedback": row["quality_feedback"],
                    "audited_at": row["audited_at"],
                    "cluster_name": row["cluster_name"],
                    "embedding": vec,
                }
            )
        return result

    def save_deck_clusters(self, deck_name: str, clusters: List[Dict[str, Any]]) -> None:
        """Persist discovered thematic clusters and map note cluster_names in SQLite."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Clean existing clusters for this deck
            cursor.execute("DELETE FROM deck_clusters WHERE deck_name = ?", (deck_name,))

            # 2. Insert new clusters
            records = []
            note_updates = []
            for cl in clusters:
                idx = int(cl.get("cluster_index", 0))
                title = cl.get("title", f"Cluster {idx + 1}").strip()
                scope = cl.get("scope", "").strip()
                note_ids = cl.get("note_ids", [])
                centroid_note_ids = cl.get("centroid_note_ids", [])

                records.append(
                    (
                        deck_name,
                        idx,
                        title,
                        scope,
                        json.dumps(note_ids),
                        json.dumps(centroid_note_ids),
                        now_iso,
                        now_iso,
                    )
                )

                for nid in note_ids:
                    note_updates.append((title, now_iso, deck_name, int(nid)))

            cursor.executemany(
                """
                INSERT INTO deck_clusters (
                    deck_name, cluster_index, title, scope, note_ids, centroid_note_ids,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )

            # 3. Update cluster_name on indexed_notes
            if note_updates:
                cursor.executemany(
                    """
                    UPDATE indexed_notes
                    SET cluster_name = ?, updated_at = ?
                    WHERE deck_name = ? AND note_id = ?
                    """,
                    note_updates,
                )
            conn.commit()

    def get_deck_clusters(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve saved thematic clusters for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, cluster_index, title, scope, note_ids, centroid_note_ids,
                       created_at, updated_at
                FROM deck_clusters
                WHERE deck_name = ?
                ORDER BY cluster_index ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        clusters = []
        for r in rows:
            try:
                nids = json.loads(r["note_ids"]) if r["note_ids"] else []
            except Exception:
                nids = []
            try:
                c_nids = json.loads(r["centroid_note_ids"]) if r["centroid_note_ids"] else []
            except Exception:
                c_nids = []

            clusters.append(
                {
                    "id": r["id"],
                    "deck_name": r["deck_name"],
                    "cluster_index": r["cluster_index"],
                    "title": r["title"],
                    "scope": r["scope"],
                    "note_ids": nids,
                    "centroid_note_ids": c_nids,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return clusters

    def replace_cluster_notes(
        self,
        deck_name: str,
        cluster_index: int,
        obsolete_note_ids: List[int],
        new_note_ids: List[int],
    ) -> None:
        """Atomically update a cluster's note_ids after transactional sanitation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, note_ids FROM deck_clusters WHERE deck_name = ? AND cluster_index = ?",
                (deck_name, cluster_index),
            )
            row = cursor.fetchone()
            if not row:
                return
            cluster_title = row["title"]
            try:
                curr_nids = json.loads(row["note_ids"]) if row["note_ids"] else []
            except Exception:
                curr_nids = []

            # Remove obsolete and append new
            obsolete_set = {int(x) for x in obsolete_note_ids}
            updated_nids = [nid for nid in curr_nids if int(nid) not in obsolete_set]
            for nid in new_note_ids:
                if int(nid) not in updated_nids:
                    updated_nids.append(int(nid))

            cursor.execute(
                """
                UPDATE deck_clusters
                SET note_ids = ?, updated_at = ?
                WHERE deck_name = ? AND cluster_index = ?
                """,
                (json.dumps(updated_nids), now_iso, deck_name, cluster_index),
            )
            # Update cluster_name on newly indexed notes
            for nid in new_note_ids:
                cursor.execute(
                    """
                    UPDATE indexed_notes
                    SET cluster_name = ?, updated_at = ?
                    WHERE deck_name = ? AND note_id = ?
                    """,
                    (cluster_title, now_iso, deck_name, int(nid)),
                )
            conn.commit()

    def get_cluster_sibling_boundaries(
        self,
        deck_name: str,
        note_id: Optional[int] = None,
        text_context: Optional[str] = None,
        limit: int = 12,
    ) -> List[str]:
        """
        Extract sibling topic titles and breadcrumbs from the same semantic cluster.
        Serves as Mutual Negative Boundaries to strictly prevent intra-cluster redundancy
        without compressing or sacrificing technical depth.
        """
        if not deck_name:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cluster_note_ids: List[int] = []
            target_cluster_title: Optional[str] = None

            # 1. Look up cluster by note_id if provided
            if note_id:
                cursor.execute(
                    """
                    SELECT cluster_index, title, note_ids 
                    FROM deck_clusters 
                    WHERE deck_name = ?
                    """,
                    (deck_name,),
                )
                rows = cursor.fetchall()
                for r in rows:
                    try:
                        nids = json.loads(r["note_ids"]) if r["note_ids"] else []
                        if int(note_id) in nids:
                            cluster_note_ids = [nid for nid in nids if nid != int(note_id)]
                            target_cluster_title = r["title"]
                            break
                    except Exception:
                        continue

            # 2. If no cluster found by note_id in deck_clusters, check indexed_notes.cluster_name
            if not cluster_note_ids and note_id:
                cursor.execute(
                    """
                    SELECT cluster_name FROM indexed_notes
                    WHERE deck_name = ? AND note_id = ?
                    """,
                    (deck_name, note_id),
                )
                c_row = cursor.fetchone()
                if c_row and c_row["cluster_name"]:
                    target_cluster_title = c_row["cluster_name"]
                    cursor.execute(
                        """
                        SELECT note_id FROM indexed_notes
                        WHERE deck_name = ? AND cluster_name = ? AND note_id != ?
                        """,
                        (deck_name, target_cluster_title, note_id),
                    )
                    cluster_note_ids = [r["note_id"] for r in cursor.fetchall()]

            # 3. Fallback: If no note_id provided, but text_context is given, match closest cluster title
            if not cluster_note_ids and text_context:
                cursor.execute(
                    """
                    SELECT cluster_index, title, note_ids, scope
                    FROM deck_clusters
                    WHERE deck_name = ?
                    """,
                    (deck_name,),
                )
                rows = cursor.fetchall()
                clean_text_lower = text_context.lower()
                for r in rows:
                    title = r["title"] or ""
                    if title.lower() in clean_text_lower or any(word in clean_text_lower for word in title.lower().split() if len(word) > 4):
                        try:
                            nids = json.loads(r["note_ids"]) if r["note_ids"] else []
                            cluster_note_ids = nids
                            target_cluster_title = title
                            break
                        except Exception:
                            continue

            if not cluster_note_ids:
                return []

            # 4. Fetch sibling fronts and clean descriptors
            placeholders = ",".join("?" for _ in cluster_note_ids)
            cursor.execute(
                f"""
                SELECT note_id, front, clean_text 
                FROM indexed_notes 
                WHERE deck_name = ? AND note_id IN ({placeholders})
                """,
                [deck_name] + cluster_note_ids,
            )
            sibling_rows = cursor.fetchall()

        # Clean and extract atomic concept descriptors
        boundaries: List[str] = []
        for row in sibling_rows:
            front = row["front"] or ""
            clean_front = re.sub(r"<[^>]+>", " ", front).strip()
            # If breadcrumb [A > B > C] is present, take the innermost leaf or specific question
            m = re.match(r"^\[(.*?)\]\s*(.*)", clean_front)
            if m:
                path = m.group(1).strip()
                leaf = path.split(">")[-1].strip() if ">" in path else path
                q = m.group(2).strip()
                descriptor = leaf if len(leaf) > 3 else q[:50]
            else:
                descriptor = clean_front.split("\n")[0][:60].strip()

            descriptor = re.sub(r"\s+", " ", descriptor)
            if descriptor and len(descriptor) > 3 and descriptor not in boundaries:
                boundaries.append(descriptor)
            if len(boundaries) >= limit:
                break

        return boundaries

    # -------------------------------------------------------------------------
    # Concept DAG Persistence Methods
    # -------------------------------------------------------------------------


    def upsert_concept_node(
        self,
        deck_name: str,
        concept_id: str,
        name: str,
        taxonomy_path: str = "general",
        description: Optional[str] = None,
        depth_level: int = 1,
        status: Optional[str] = None,
        is_in_scope: Optional[bool] = None,
        stage_id: Optional[str] = None,
    ) -> None:
        """Insert or update a concept node in the deck DAG."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            scope_val = 1 if is_in_scope is None or is_in_scope else 0
            cursor.execute(
                """
                INSERT INTO concept_nodes (deck_name, id, name, taxonomy_path, description, depth_level, status, is_in_scope, stage_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, 'RAW'), ?, COALESCE(?, 'stage_1'), ?, ?)
                ON CONFLICT(deck_name, id) DO UPDATE SET
                    name = excluded.name,
                    taxonomy_path = excluded.taxonomy_path,
                    description = COALESCE(excluded.description, concept_nodes.description),
                    depth_level = excluded.depth_level,
                    status = COALESCE(?, concept_nodes.status, 'RAW'),
                    is_in_scope = COALESCE(excluded.is_in_scope, concept_nodes.is_in_scope),
                    stage_id = COALESCE(?, concept_nodes.stage_id, 'stage_1'),
                    updated_at = excluded.updated_at
                """,
                (deck_name, concept_id, name, taxonomy_path, description, depth_level, status, scope_val, stage_id, now, now, status, stage_id),
            )
            conn.commit()

    def upsert_concept_edge(
        self,
        deck_name: str,
        source_id: str,
        target_id: str,
        relation_type: str = "requires",
    ) -> None:
        """Insert a directed edge between concepts (e.g. source_id required by target_id)."""
        if source_id == target_id:
            return  # prevent direct self-loops
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO concept_edges (deck_name, source_id, target_id, relation_type)
                VALUES (?, ?, ?, ?)
                """,
                (deck_name, source_id, target_id, relation_type),
            )
            conn.commit()

    def link_card_to_concept(
        self,
        deck_name: str,
        note_id: int,
        concept_id: str,
        role: str = "target",
    ) -> None:
        """Link an Anki note to a concept node as either 'target' (note explains concept) or 'prerequisite'."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO card_concept_mappings (deck_name, note_id, concept_id, role)
                VALUES (?, ?, ?, ?)
                """,
                (deck_name, note_id, concept_id, role),
            )
            conn.commit()

    def get_concept_node(self, deck_name: str, concept_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific concept node by deck and id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, taxonomy_path, description, depth_level, status, is_in_scope, stage_id
                FROM concept_nodes
                WHERE deck_name = ? AND id = ?
                """,
                (deck_name, concept_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_cards_for_concept(self, deck_name: str, concept_id: str) -> List[Dict[str, Any]]:
        """Fetch all indexed notes mapped to a given concept node."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT n.note_id, n.front, n.back, n.explanation, n.quality_status, n.quality_score, m.role
                FROM card_concept_mappings m
                JOIN indexed_notes n ON n.deck_name = m.deck_name AND n.note_id = m.note_id
                WHERE m.deck_name = ? AND m.concept_id = ?
                ORDER BY n.note_id ASC
                """,
                (deck_name, concept_id),
            )
            return [dict(r) for r in cursor.fetchall()]

    def update_concept_node_status(self, deck_name: str, concept_id: str, status: str) -> None:
        """Update lifecycle status of a concept node (e.g. MASTERED)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE concept_nodes
                SET status = ?, updated_at = ?
                WHERE deck_name = ? AND id = ?
                """,
                (status, now, deck_name, concept_id),
            )
            conn.commit()


    def save_note_extracted_knowledge(
        self,
        deck_name: str,
        note_id: int,
        raw_front: str,
        raw_back: str,
        extracted_facts: List[str],
        target_concepts: List[str],
        assumed_prerequisites: List[str],
        taxonomy_path: Optional[str] = None,
    ) -> None:
        """Persist structured ontological extraction for an individual note."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO note_extracted_knowledge
                    (deck_name, note_id, raw_front, raw_back, extracted_facts, target_concepts, assumed_prerequisites, taxonomy_path, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_name, note_id) DO UPDATE SET
                    raw_front = excluded.raw_front,
                    raw_back = excluded.raw_back,
                    extracted_facts = excluded.extracted_facts,
                    target_concepts = excluded.target_concepts,
                    assumed_prerequisites = excluded.assumed_prerequisites,
                    taxonomy_path = excluded.taxonomy_path,
                    extracted_at = excluded.extracted_at
                """,
                (
                    deck_name,
                    note_id,
                    raw_front,
                    raw_back,
                    json.dumps(extracted_facts, ensure_ascii=False),
                    json.dumps(target_concepts, ensure_ascii=False),
                    json.dumps(assumed_prerequisites, ensure_ascii=False),
                    taxonomy_path,
                    now,
                ),
            )
            conn.commit()

    def get_note_extracted_knowledge(self, deck_name: str, note_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve stored extraction for a specific note."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, raw_front, raw_back, extracted_facts, target_concepts, assumed_prerequisites, taxonomy_path, extracted_at
                FROM note_extracted_knowledge
                WHERE deck_name = ? AND note_id = ?
                """,
                (deck_name, note_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "source_note_id": row["note_id"],
                "raw_front": row["raw_front"],
                "raw_back": row["raw_back"],
                "extracted_facts": json.loads(row["extracted_facts"] or "[]"),
                "target_concepts": json.loads(row["target_concepts"] or "[]"),
                "assumed_prerequisites": json.loads(row["assumed_prerequisites"] or "[]"),
                "taxonomy_path": row["taxonomy_path"],
                "extracted_at": row["extracted_at"],
            }

    def get_all_deck_extracted_knowledge(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all extracted note knowledge for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, raw_front, raw_back, extracted_facts, target_concepts, assumed_prerequisites, taxonomy_path, extracted_at
                FROM note_extracted_knowledge
                WHERE deck_name = ?
                ORDER BY note_id ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "source_note_id": r["note_id"],
                "raw_front": r["raw_front"],
                "raw_back": r["raw_back"],
                "extracted_facts": json.loads(r["extracted_facts"] or "[]"),
                "target_concepts": json.loads(r["target_concepts"] or "[]"),
                "assumed_prerequisites": json.loads(r["assumed_prerequisites"] or "[]"),
                "taxonomy_path": r["taxonomy_path"],
                "extracted_at": r["extracted_at"],
            })
        return results

    def get_deck_concepts(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all concept nodes for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, taxonomy_path, description, depth_level, status, is_in_scope, stage_id, created_at, updated_at
                FROM concept_nodes
                WHERE deck_name = ?
                ORDER BY depth_level ASC, name ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_deck_edges(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all concept dependency edges for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT source_id, target_id, relation_type
                FROM concept_edges
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()
            return [{"source": r["source_id"], "target": r["target_id"], "relation_type": r["relation_type"]} for r in rows]

    def get_card_concept_mappings(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all card-concept mappings for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, concept_id, role
                FROM card_concept_mappings
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def clear_deck_dag(self, deck_name: str) -> None:
        """Purge all concept nodes, edges, card mappings, and extracted knowledge for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM concept_nodes WHERE deck_name = ?", (deck_name,))
            cursor.execute("DELETE FROM concept_edges WHERE deck_name = ?", (deck_name,))
            cursor.execute("DELETE FROM card_concept_mappings WHERE deck_name = ?", (deck_name,))
            cursor.execute("DELETE FROM note_extracted_knowledge WHERE deck_name = ?", (deck_name,))
            conn.commit()

    # -------------------------------------------------------------------------
    # Learning Plan Contract Persistence Methods
    # -------------------------------------------------------------------------

    def save_learning_contract(
        self,
        deck_name: str,
        contract: Dict[str, Any],
        status: str = "draft",
    ) -> None:
        """Save or update learning contract for a deck."""
        resolved_status = contract.get("status") if status == "draft" and "status" in contract else status
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO deck_learning_contracts (deck_name, contract_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(deck_name) DO UPDATE SET
                    contract_json = excluded.contract_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (deck_name, json.dumps(contract, ensure_ascii=False), resolved_status, now, now),
            )
            conn.commit()


    def get_learning_contract(self, deck_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored learning contract for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contract_json, status, created_at, updated_at
                FROM deck_learning_contracts
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            try:
                data = json.loads(row["contract_json"])
                data["status"] = row["status"]
                data["created_at"] = row["created_at"]
                data["updated_at"] = row["updated_at"]
                return data
            except Exception:
                return None

    def delete_learning_contract(self, deck_name: str) -> None:
        """Delete stored learning contract for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM deck_learning_contracts WHERE deck_name = ?", (deck_name,))
            conn.commit()

    def record_ledger_coverage(
        self,
        deck_name: str,
        source_note_id: int,
        colliding_note_id: int,
        concept_title: str,
        facet_summary: Optional[str],
        created_atomic_note_ids: List[int],
    ) -> int:
        """Record a coverage entry linking a sanitized note's created cards to a colliding pending note."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            ids_json = json.dumps(created_atomic_note_ids or [])
            cursor.execute(
                """
                INSERT INTO sanitation_coverage_ledger
                (deck_name, source_sanitized_note_id, colliding_pending_note_id, covered_concept_title, covered_facet_summary, created_atomic_note_ids, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (deck_name, source_note_id, colliding_note_id, concept_title, facet_summary or "", ids_json, now),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_ledger_entries_for_note(self, deck_name: str, note_id: int) -> List[Dict[str, Any]]:
        """Fetch all coverage entries where colliding_pending_note_id == note_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, source_sanitized_note_id, colliding_pending_note_id, covered_concept_title, covered_facet_summary, created_atomic_note_ids, created_at
                FROM sanitation_coverage_ledger
                WHERE deck_name = ? AND colliding_pending_note_id = ?
                ORDER BY id ASC
                """,
                (deck_name, note_id),
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                cids = []
                try:
                    cids = json.loads(r["created_atomic_note_ids"]) if r["created_atomic_note_ids"] else []
                except Exception:
                    cids = []
                results.append({
                    "id": r["id"],
                    "deck_name": r["deck_name"],
                    "source_sanitized_note_id": r["source_sanitized_note_id"],
                    "colliding_pending_note_id": r["colliding_pending_note_id"],
                    "covered_concept_title": r["covered_concept_title"],
                    "covered_facet_summary": r["covered_facet_summary"],
                    "created_atomic_note_ids": cids,
                    "created_at": r["created_at"],
                })
            return results

    def delete_ledger_entries_for_note(self, deck_name: str, note_id: int) -> int:
        """Purge ledger entries and extracted knowledge for a note once it is sanitized/deleted."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM sanitation_coverage_ledger
                WHERE deck_name = ? AND colliding_pending_note_id = ?
                """,
                (deck_name, note_id),
            )
            deleted_ledger = cursor.rowcount
            cursor.execute(
                """
                DELETE FROM note_extracted_knowledge
                WHERE deck_name = ? AND note_id = ?
                """,
                (deck_name, note_id),
            )
            conn.commit()
            return deleted_ledger



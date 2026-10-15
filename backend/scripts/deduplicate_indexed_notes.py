import json
import logging
import sqlite3
import urllib.request
from typing import List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deduplicator")

DB_PATH = "backend/data/deck_knowledge.db"


def anki_invoke(action: str, **params):
    """Invoke AnkiConnect API if available."""
    try:
        payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8765", data=payload)
        resp = urllib.request.urlopen(req, timeout=5)
        res = json.loads(resp.read())
        if res.get("error"):
            logger.warning("AnkiConnect error: %s", res["error"])
            return None
        return res.get("result")
    except Exception as e:
        logger.warning("AnkiConnect unavailable: %s", e)
        return None


def deduplicate_indexed_notes():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find duplicate content groups
    cursor.execute("""
        SELECT deck_name, front, back, COUNT(*) as cnt, GROUP_CONCAT(note_id) as ids
        FROM indexed_notes
        GROUP BY deck_name, front, back
        HAVING cnt > 1;
    """)
    dup_groups = cursor.fetchall()

    if not dup_groups:
        logger.info("Zero duplicate note groups found in indexed_notes. Database is clean.")
        conn.close()
        return

    logger.info("Found %d duplicate groups in indexed_notes.", len(dup_groups))

    notes_to_delete: List[int] = []

    for deck_name, front, back, cnt, ids_str in dup_groups:
        id_list = [int(x) for x in ids_str.split(",")]
        # Keep the highest (newest) note_id, delete older duplicate IDs
        keep_id = max(id_list)
        discard_ids = [nid for nid in id_list if nid != keep_id]
        logger.info(
            "Group [%s]: Keeping newest note #%d, discarding duplicates: %s (Front: %s...)",
            deck_name,
            keep_id,
            discard_ids,
            front[:60].replace("\n", " "),
        )
        notes_to_delete.extend(discard_ids)

    # Deduplicate notes_to_delete list
    notes_to_delete = sorted(list(set(notes_to_delete)))
    logger.info("Total obsolete duplicate notes to purge: %d", len(notes_to_delete))

    # 1. Purge from Anki collection via AnkiConnect
    anki_res = anki_invoke("deleteNotes", notes=notes_to_delete)
    if anki_res is not None:
        logger.info("Successfully deleted %d duplicate notes from live Anki collection.", len(notes_to_delete))
    else:
        logger.warning("Could not delete from live Anki collection (AnkiConnect skipped or failed).")

    # 2. Purge from SQLite indexed_notes
    placeholders = ",".join("?" for _ in notes_to_delete)
    cursor.execute(f"DELETE FROM indexed_notes WHERE note_id IN ({placeholders})", notes_to_delete)
    deleted_idx = cursor.rowcount

    cursor.execute(f"DELETE FROM card_concept_mappings WHERE note_id IN ({placeholders})", notes_to_delete)
    cursor.execute(f"DELETE FROM note_extracted_knowledge WHERE note_id IN ({placeholders})", notes_to_delete)

    conn.commit()
    logger.info("Purged %d rows from SQLite indexed_notes.", deleted_idx)

    # 3. Verify zero duplicates remaining
    cursor.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT deck_name, front, back
            FROM indexed_notes
            GROUP BY deck_name, front, back
            HAVING COUNT(*) > 1
        );
    """)
    remaining = cursor.fetchone()[0]
    logger.info("Integrity check: %d duplicate groups remain.", remaining)

    conn.close()


if __name__ == "__main__":
    deduplicate_indexed_notes()

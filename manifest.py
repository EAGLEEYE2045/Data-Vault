"""
Manifest store: tracks each uploaded file's metadata, encryption key,
and where its (single, for now) chunk lives in the storage backend.

SQLite for now -- swap for Postgres later without changing the pipeline.
"""

import json
import sqlite3
from dataclasses import dataclass

from base import StoredRef

DB_PATH = "cloudvault.db"


@dataclass
class FileRecord:
    file_id: str
    filename: str
    size_bytes: int
    content_hash: str    # sha256 of the *plaintext* file, used for dedup
    key: bytes          # AES key, keep this safe -- losing it = losing the file
    ref: StoredRef       # backend reference to fetch the encrypted blob
    created_at: float


class Manifest:
    def __init__(self, db_path: str = DB_PATH):
        # self.conn = sqlite3.connect(db_path)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                filename TEXT,
                size_bytes INTEGER,
                content_hash TEXT,
                key_hex TEXT,
                backend TEXT,
                ref_json TEXT,
                created_at REAL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_hash ON files(content_hash)"
        )
        self.conn.commit()

    def save(self, record: FileRecord) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO files
                (file_id, filename, size_bytes, content_hash, key_hex, backend, ref_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.file_id,
                record.filename,
                record.size_bytes,
                record.content_hash,
                record.key.hex(),
                record.ref.backend,
                json.dumps(record.ref.data),
                record.created_at,
            ),
        )
        self.conn.commit()

    def find_by_hash(self, content_hash: str) -> FileRecord | None:
        row = self.conn.execute(
            "SELECT file_id FROM files WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        return self.get(row[0])

    def get(self, file_id: str) -> FileRecord:
        row = self.conn.execute(
            "SELECT file_id, filename, size_bytes, content_hash, key_hex, backend, ref_json, created_at "
            "FROM files WHERE file_id = ?",
            (file_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No file with id {file_id}")
        file_id, filename, size_bytes, content_hash, key_hex, backend, ref_json, created_at = row
        return FileRecord(
            file_id=file_id,
            filename=filename,
            size_bytes=size_bytes,
            content_hash=content_hash,
            key=bytes.fromhex(key_hex),
            ref=StoredRef(backend=backend, data=json.loads(ref_json)),
            created_at=created_at,
        )

    def list_files(self):
        rows = self.conn.execute(
            "SELECT file_id, filename, size_bytes, created_at FROM files ORDER BY created_at DESC"
        ).fetchall()
        return rows

    def delete(self, file_id: str) -> None:
        self.conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        self.conn.commit()
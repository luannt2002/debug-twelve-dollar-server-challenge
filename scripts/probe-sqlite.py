"""Kiểm tra ngữ nghĩa SQLite bằng fixture tạm; không phải benchmark tải."""
import json
import pathlib
import sqlite3
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
results = {"sqlite_version": sqlite3.sqlite_version, "checks": []}
def record(name, **values):
    results["checks"].append({"name": name, **values})
with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "fixture.db"
    writer = sqlite3.connect(path, isolation_level=None)
    writer.executescript((root / "upstream/twelve-dollar-server-challenge/schema.sql").read_text())
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("INSERT INTO users(id,username) VALUES(1,'fixture')")
    foreign_keys = writer.execute("PRAGMA foreign_keys").fetchone()[0]
    writer.execute("INSERT INTO posts(user_id,body) VALUES(999,'orphan')")
    record("foreign_keys_default", enabled=foreign_keys, orphan_inserted=True)
    writer.execute("DELETE FROM posts")
    writer.execute("PRAGMA foreign_keys=ON")
    try:
        writer.execute("INSERT INTO posts(user_id,body) VALUES(999,'orphan')")
        raise AssertionError("foreign key should reject")
    except sqlite3.IntegrityError:
        record("foreign_keys_enabled", orphan_rejected=True)
    reader = sqlite3.connect(path, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO posts(user_id,body) VALUES(1,'tentative')")
    own = writer.execute("SELECT count(*) FROM posts").fetchone()[0]
    other = reader.execute("SELECT count(*) FROM posts").fetchone()[0]
    writer.execute("ROLLBACK")
    record("read_during_write_batch", same_connection_count=own, other_connection_count=other,
           after_rollback=reader.execute("SELECT count(*) FROM posts").fetchone()[0])
    writer.execute("INSERT INTO posts(user_id,body) VALUES(1,'before')")
    reader.execute("BEGIN")
    before = reader.execute("SELECT count(*) FROM posts").fetchone()[0]
    writer.execute("INSERT INTO posts(user_id,body) VALUES(1,'after')")
    pinned = reader.execute("SELECT count(*) FROM posts").fetchone()[0]
    reader.execute("COMMIT")
    fresh = reader.execute("SELECT count(*) FROM posts").fetchone()[0]
    record("pinned_read_snapshot", before=before, after_external_commit=pinned, after_reader_commit=fresh)
    plan = writer.execute("EXPLAIN QUERY PLAN SELECT p.id,p.body,p.created_at,u.username,(SELECT count(*) FROM likes l WHERE l.post_id=p.id) FROM posts p JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC,p.id DESC LIMIT 20").fetchall()
    record("feed_query_plan", plan=plan)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO posts(user_id,body) VALUES(1,'good')")
    try:
        writer.execute("INSERT INTO posts(user_id,body) VALUES(1,'')")
    except sqlite3.IntegrityError:
        pass
    writer.execute("COMMIT")
    record("statement_constraint_error", successful_peer_committed=bool(reader.execute("SELECT 1 FROM posts WHERE body='good'").fetchone()))
    reader.close()
    writer.close()
    exclusive = sqlite3.connect(path, isolation_level=None, timeout=0.05)
    exclusive.execute("PRAGMA locking_mode=EXCLUSIVE")
    exclusive.execute("SELECT count(*) FROM posts").fetchone()
    second = sqlite3.connect(path, isolation_level=None, timeout=0.05)
    try:
        second.execute("SELECT count(*) FROM posts").fetchone()
        blocked = False
    except sqlite3.OperationalError as error:
        blocked = str(error)
    record("exclusive_second_connection", result=blocked)
    second.close()
    exclusive.close()
print(json.dumps(results, indent=2, ensure_ascii=False))

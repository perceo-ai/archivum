"""The Kuzu constraint behind "Could not set lock on file", reproduced for real.

`backend` and `mcp` used to each run `archivum.db.graph` in their own OS
process, each with its own `_db`/`_conn` singleton on the same file. This
test does exactly that with the real `kuzu` package: one process owns the
database and is writing, a second process tries to open it.

The second process has to be a real subprocess. Kuzu's file lock is held per
process (POSIX record locks are), so a second `kuzu.Database` on the same
path inside the *same* process opens without complaint and would not
reproduce anything.

This asserts the bug's precondition, not the fix: it passes on main and is
meant to. If a Kuzu upgrade ever makes a second process able to open a file
another process holds, this fails, and the single-owner design in
`db/graph.py` can be revisited.
"""

from __future__ import annotations

import subprocess
import sys
import threading

import kuzu
import pytest

from archivum.db.graph import _init_schema


_OPEN_FROM_SECOND_PROCESS = """
import sys
import kuzu
kwargs = {"read_only": True} if sys.argv[2] == "ro" else {}
try:
    kuzu.Database(sys.argv[1], **kwargs)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(3)
print("opened")
"""


@pytest.fixture
def owner_writing(tmp_path):
    """Open the database the way the owner does and keep writing to it."""
    db_file = tmp_path / "archivum.kuzu"
    db = kuzu.Database(str(db_file))
    conn = kuzu.Connection(db)
    _init_schema(conn)

    stop = threading.Event()
    writes = [0]
    errors: list[BaseException] = []

    def hammer() -> None:
        try:
            while not stop.is_set():
                n = writes[0]
                conn.execute(
                    "MERGE (p:Page {slug: $slug}) SET p.title = $title, p.wiki_id = 'default'",
                    {"slug": f"owner-{n % 50}", "title": f"Owner {n}"},
                )
                writes[0] += 1
        except BaseException as exc:  # noqa: BLE001 - surfaced by the test
            errors.append(exc)

    writer = threading.Thread(target=hammer, daemon=True)
    writer.start()
    try:
        yield db_file, writes
    finally:
        stop.set()
        writer.join(timeout=10)
        assert not errors, errors
        conn.close()
        db.close()


@pytest.mark.parametrize("mode", ["rw", "ro"])
def test_second_process_cannot_open_a_database_another_process_is_writing(owner_writing, mode):
    db_file, writes = owner_writing
    before = writes[0]

    proc = subprocess.run(
        [sys.executable, "-c", _OPEN_FROM_SECOND_PROCESS, str(db_file), mode],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # The owner was really writing while the second process tried to open.
    assert writes[0] > before
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "lock" in proc.stdout.lower(), proc.stdout
    # Read-only is not an escape hatch while a writer holds the file: that is
    # why `mcp` talks to the owner instead of opening the file itself.

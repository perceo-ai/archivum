"""Distillation was built and never triggered, so memory stayed empty forever.

These cover the pump rather than the pipeline: that capture enqueues, that the
worker drains, and that a failure is classified rather than retried blindly.
"""

import pytest

from archivum.config import Settings
from archivum.db import sqlite as sqlite_mod
from archivum.distillation import MAX_ATTEMPTS, run_pending_distillations
from archivum.memory.service import DistillationError


@pytest.fixture
async def settings(tmp_path):
    s = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(s)
    return s


async def test_enqueue_is_idempotent(settings):
    await sqlite_mod.enqueue_distillation("source:a", "default")
    await sqlite_mod.enqueue_distillation("source:a", "default")

    jobs = await sqlite_mod.list_distillation_jobs("default")
    assert len(jobs) == 1, "re-capturing a source must not queue it twice"
    assert jobs[0]["status"] == "pending"


async def test_a_job_is_claimed_only_once(settings):
    await sqlite_mod.enqueue_distillation("source:a", "default")

    first = await sqlite_mod.claim_distillation()
    second = await sqlite_mod.claim_distillation()

    assert first is not None and first["source_id"] == "source:a"
    assert second is None, "a running job must not be claimed again"


async def test_worker_distils_queued_sources(settings, monkeypatch):
    calls: list[str] = []

    class Report:
        atoms_total = 3
        atoms_pending_review = 2

    async def fake_distill(source_id, *, wiki_id, settings=None):
        calls.append(source_id)
        return Report()

    monkeypatch.setattr("archivum.distillation.distill_source", fake_distill)
    await sqlite_mod.enqueue_distillation("source:a", "default")

    done = await run_pending_distillations(settings=settings)

    assert done == 1
    assert calls == ["source:a"]
    assert (await sqlite_mod.list_distillation_jobs("default"))[0]["status"] == "done"


async def test_an_unusable_source_is_not_retried(settings, monkeypatch):
    async def rejects(source_id, *, wiki_id, settings=None):
        raise DistillationError("source has no document")

    monkeypatch.setattr("archivum.distillation.distill_source", rejects)
    await sqlite_mod.enqueue_distillation("source:bad", "default")

    await run_pending_distillations(settings=settings)

    job = (await sqlite_mod.list_distillation_jobs("default"))[0]
    assert job["status"] == "error"
    assert "no document" in job["error"]


async def test_a_transient_failure_is_retried_then_abandoned(settings, monkeypatch):
    """A flaky model call should be retried; an endlessly failing one should not
    spin forever."""

    async def flaky(source_id, *, wiki_id, settings=None):
        raise RuntimeError("model timed out")

    monkeypatch.setattr("archivum.distillation.distill_source", flaky)
    await sqlite_mod.enqueue_distillation("source:flaky", "default")

    for _ in range(MAX_ATTEMPTS + 1):
        await run_pending_distillations(settings=settings)

    job = (await sqlite_mod.list_distillation_jobs("default"))[0]
    assert job["status"] == "error"
    assert job["attempts"] >= MAX_ATTEMPTS


async def test_capture_enqueues_distillation():
    """Capture must not block on a model, so it queues instead of distilling."""
    import inspect

    from archivum.api import capture

    source = inspect.getsource(capture.capture_endpoint)
    assert "enqueue_distillation" in source
    assert "distill_conversation" not in source

"""The CLI model runner's process lifecycle."""

from __future__ import annotations

from unittest.mock import patch

import pytest

async def test_a_cancelled_run_kills_its_child_process():
    """An abandoned model process would run unbounded.

    `proc.kill()` only happened on timeout, and cancelling takes the timeout
    with it — so a cancelled narration left its CLI running, holding memory and
    model capacity while whatever cancelled it carried on. Reindexing a
    repository cancels its previous narration, which is exactly this case.
    """
    import asyncio

    from archivum.llm import cli_client

    started = asyncio.Event()
    killed = asyncio.Event()

    class _Proc:
        returncode = None

        async def communicate(self, _stdin=None):
            started.set()
            await asyncio.Event().wait()  # never finishes on its own

        def kill(self):
            killed.set()
            self.returncode = -9

        async def wait(self):
            return self.returncode

    async def _fake_exec(*_args, **_kwargs):
        return _Proc()

    with patch.object(asyncio, "create_subprocess_exec", new=_fake_exec):
        task = asyncio.create_task(
            cli_client._run_process(["claude"], None, timeout_seconds=600)
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert killed.is_set(), "the child must be killed when the run is cancelled"

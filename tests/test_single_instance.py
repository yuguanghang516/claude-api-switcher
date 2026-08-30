import os
import uuid

import pytest

from app.single_instance import SingleInstanceGuard


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex test")
def test_named_mutex_blocks_a_second_instance_and_releases_cleanly():
    name = rf"Local\ClaudeAPISwitcher.Tests.{uuid.uuid4().hex}"
    first = SingleInstanceGuard(name)
    second = SingleInstanceGuard(name)

    assert first.acquire() is True
    assert second.acquire() is False

    first.release()
    assert second.acquire() is True
    second.release()


def test_release_is_idempotent():
    guard = SingleInstanceGuard(r"Local\ClaudeAPISwitcher.Tests.Idempotent")
    guard.release()
    guard.release()

from __future__ import annotations

from django.test import SimpleTestCase

from global_utils.distributed_lock import DistributedLock, LockAcquireError, lock

from .fakes import InMemoryLockKV


class DistributedLockUnitTests(SimpleTestCase):
    def setUp(self) -> None:
        self.kv = InMemoryLockKV()

    def test_acquires_and_releases(self) -> None:
        l = DistributedLock("k", ttl_ms=5000, client=self.kv)
        self.assertTrue(l.acquire())
        self.assertTrue(l.release())

    def test_second_acquire_fails_while_held(self) -> None:
        a = DistributedLock("k", ttl_ms=5000, client=self.kv)
        b = DistributedLock("k", ttl_ms=5000, client=self.kv)
        self.assertTrue(a.acquire())
        self.assertFalse(b.acquire())
        a.release()
        self.assertTrue(b.acquire())

    def test_release_with_wrong_token_is_noop(self) -> None:
        a = DistributedLock("k", ttl_ms=5000, client=self.kv)
        a.acquire()
        # Simulate another process trying to release without owning the key.
        rogue = DistributedLock("k", ttl_ms=5000, client=self.kv)
        rogue._token = "not-the-real-token"
        self.assertFalse(rogue.release())
        # Original still owns it.
        self.assertEqual(self.kv.get("k"), a._token)

    def test_context_manager_raises_when_contended(self) -> None:
        a = DistributedLock("k", ttl_ms=5000, client=self.kv)
        a.acquire()
        with self.assertRaises(LockAcquireError):
            with lock("k", ttl_ms=5000, client=self.kv):
                self.fail("should not enter")

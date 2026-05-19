import pathlib
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from load_worker_assignment import build_worker_user_index_assignment
from reporting import RunRecorder


class LoadWorkerAssignmentTests(unittest.TestCase):
    def test_all_users_false_reuses_same_user_index(self) -> None:
        assignment = build_worker_user_index_assignment(
            all_users=False,
            worker_count=5,
            plan_user_count=3,
        )
        self.assertEqual(assignment, [0, 0, 0, 0, 0])

    def test_all_users_true_selects_first_n_users(self) -> None:
        assignment = build_worker_user_index_assignment(
            all_users=True,
            worker_count=3,
            plan_user_count=5,
        )
        self.assertEqual(assignment, [0, 1, 2])

    def test_all_users_true_round_robins_when_workers_exceed_users(self) -> None:
        assignment = build_worker_user_index_assignment(
            all_users=True,
            worker_count=8,
            plan_user_count=3,
        )
        self.assertEqual(assignment, [0, 1, 2, 0, 1, 2, 0, 1])

    def test_all_users_true_requires_plan_users(self) -> None:
        with self.assertRaises(ValueError):
            build_worker_user_index_assignment(
                all_users=True,
                worker_count=2,
                plan_user_count=0,
            )


class UserSimWorkerOverrideTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_uses_worker_count_override(self) -> None:
        import config
        import user_sim

        seen_worker_ids: list[int] = []

        class FakeWatcher:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            async def start(self) -> None:
                return None

            async def stop(self) -> None:
                return None

        async def fake_worker(*args, **kwargs):
            worker_id = int(args[2])
            seen_worker_ids.append(worker_id)
            return None

        previous_users = config.N_USERS
        config.N_USERS = 9
        try:
            with (
                mock.patch.object(user_sim, "_UserOrderWatcher", FakeWatcher),
                mock.patch.object(user_sim, "_worker", fake_worker),
            ):
                await user_sim.run(
                    recorder=RunRecorder.bootstrap(),
                    session=user_sim.UserSession(
                        token="token",
                        user_id=11,
                        user={"id": 11},
                        token_source="test",
                    ),
                    fixtures=types.SimpleNamespace(),
                    worker_count=3,
                )
        finally:
            config.N_USERS = previous_users

        self.assertEqual(seen_worker_ids, [1, 2, 3])

    async def test_run_defaults_to_config_worker_count(self) -> None:
        import config
        import user_sim

        seen_worker_ids: list[int] = []

        class FakeWatcher:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            async def start(self) -> None:
                return None

            async def stop(self) -> None:
                return None

        async def fake_worker(*args, **kwargs):
            worker_id = int(args[2])
            seen_worker_ids.append(worker_id)
            return None

        previous_users = config.N_USERS
        config.N_USERS = 4
        try:
            with (
                mock.patch.object(user_sim, "_UserOrderWatcher", FakeWatcher),
                mock.patch.object(user_sim, "_worker", fake_worker),
            ):
                await user_sim.run(
                    recorder=RunRecorder.bootstrap(),
                    session=user_sim.UserSession(
                        token="token",
                        user_id=11,
                        user={"id": 11},
                        token_source="test",
                    ),
                    fixtures=types.SimpleNamespace(),
                )
        finally:
            config.N_USERS = previous_users

        self.assertEqual(seen_worker_ids, [1, 2, 3, 4])

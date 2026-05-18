import os
import unittest
from unittest import mock

from api.app.integrations import routing


class GitHubWebhookRoutingTests(unittest.TestCase):
    def test_route_by_branch_defaults_to_environment_mode(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SIMULATOR_WEBHOOK_ROUTE_BY", None)
            self.assertFalse(routing.route_by_branch())

    def test_route_key_from_workflow_run_uses_head_branch_in_branch_mode(self) -> None:
        with mock.patch.dict(os.environ, {"SIMULATOR_WEBHOOK_ROUTE_BY": "branch"}, clear=False):
            key = routing.route_key_from_workflow_run({"head_branch": "dev"})
            self.assertEqual(key, "dev")

    def test_route_key_from_workflow_run_uses_fallback_in_environment_mode(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SIMULATOR_WEBHOOK_ROUTE_BY": "environment",
                "SIMULATOR_WORKFLOW_RUN_DEFAULT_ENVIRONMENT": "production",
            },
            clear=False,
        ):
            key = routing.route_key_from_workflow_run({"head_branch": "dev"})
            self.assertEqual(key, "production")

    def test_route_key_from_deployment_uses_ref_in_branch_mode(self) -> None:
        with mock.patch.dict(os.environ, {"SIMULATOR_WEBHOOK_ROUTE_BY": "branch"}, clear=False):
            key = routing.route_key_from_deployment({"ref": "dev", "environment": "production"})
            self.assertEqual(key, "dev")

    def test_normalize_route_key_strips_refs_heads(self) -> None:
        self.assertEqual(routing.normalize_route_key("refs/heads/main"), "main")


if __name__ == "__main__":
    unittest.main()

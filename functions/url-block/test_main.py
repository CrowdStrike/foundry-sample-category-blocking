"""Test module for the main function handlers."""

import importlib
import unittest
from unittest.mock import patch, MagicMock, mock_open

from crowdstrike.foundry.function import Request

import main


def mock_handler(*_args, **_kwargs):
    """Mock handler decorator for testing."""

    def identity(func):
        return func

    return identity


class TestMainHandlers(unittest.TestCase):
    """Test case class for main function handler tests."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        patcher = patch("crowdstrike.foundry.function.Function.handler", new=mock_handler)
        self.addCleanup(patcher.stop)
        self.handler_patch = patcher.start()

        importlib.reload(main)

    @patch("main.process_csv_records")
    @patch("main.CustomStorage")
    @patch("main.APIHarnessV2")
    @patch("main.cloud")
    @patch("os.path.dirname")
    @patch("os.path.join")
    @patch("os.path.abspath")
    def test_import_csv_handler_success(self, mock_abspath, mock_join, mock_dirname,
                                      mock_cloud, mock_api_harness, mock_custom_storage, mock_process):
        """Test successful CSV import handler."""
        # Setup mocks
        mock_dirname.return_value = "/test/dir"
        mock_join.return_value = "/test/dir/output.csv"
        mock_abspath.return_value = "/test/dir/main.py"
        mock_cloud.return_value = "https://api.crowdstrike.com"

        mock_api_client = MagicMock()
        mock_api_harness.return_value = mock_api_client
        mock_customobjects = MagicMock()
        mock_custom_storage.return_value = mock_customobjects

        # Mock process_csv_records
        mock_process.return_value = {
            "total_rows": 5,
            "success_count": 5,
            "error_count": 0
        }

        request = Request()
        response = main.import_csv_handler(request)

        self.assertEqual(response.code, 200)
        self.assertTrue(response.body["success"])
        self.assertEqual(response.body["total_rows"], 5)
        self.assertEqual(response.body["successful_imports"], 5)
        self.assertEqual(response.body["failed_imports"], 0)

    @patch("main.APIHarnessV2")
    def test_import_csv_handler_error(self, mock_api_harness):
        """Test CSV import handler with error."""
        # Setup mocks to raise exception
        mock_api_harness.side_effect = OSError("File system error")

        request = Request()
        response = main.import_csv_handler(request)

        self.assertEqual(response.code, 500)
        self.assertEqual(len(response.errors), 1)
        self.assertIn("File system error", response.errors[0].message)

    @patch("main.get_host_groups")
    def test_on_create_success(self, mock_get_host_groups):
        """Test successful host groups handler."""
        mock_get_host_groups.return_value = [
            {"id": "group-1", "name": "Group 1"},
            {"id": "group-2", "name": "Group 2"}
        ]

        request = Request()
        logger = MagicMock()
        response = main.on_create(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertIn("host_groups", response.body)
        self.assertEqual(len(response.body["host_groups"]), 2)
        self.assertEqual(response.body["host_groups"][0]["id"], "group-1")
        self.assertEqual(response.body["host_groups"][0]["name"], "Group 1")

    @patch("main.get_host_groups")
    def test_on_create_api_error(self, mock_get_host_groups):
        """Test host groups handler with API error."""
        from exceptions import FirewallAPIError
        mock_get_host_groups.side_effect = FirewallAPIError("API initialization failed")

        request = Request()
        logger = MagicMock()
        response = main.on_create(request, None, logger)

        self.assertEqual(response.code, 500)
        self.assertIn("error", response.body)
        self.assertIn("Failed to retrieve host groups", response.body["error"])

    @patch("main.read_categories_from_csv")
    @patch("os.path.dirname")
    @patch("os.path.join")
    @patch("os.path.abspath")
    def test_get_categories_success(self, mock_abspath, mock_join, mock_dirname, mock_read_csv):
        """Test successful categories retrieval."""
        # Setup path mocks
        mock_dirname.return_value = "/test/dir"
        mock_join.return_value = "/test/dir/output.csv"
        mock_abspath.return_value = "/test/dir/main.py"
        
        mock_read_csv.return_value = {"gaming": "example.com;gaming.org"}

        request = Request()
        logger = MagicMock()
        response = main.get_categories(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertIn("categories", response.body)
        self.assertIn("gaming", response.body["categories"])
        self.assertEqual(response.body["categories"]["gaming"], "example.com;gaming.org")

    @patch("main.read_categories_from_csv")
    @patch("os.path.dirname")
    @patch("os.path.join")
    @patch("os.path.abspath")
    def test_get_categories_file_not_found(self, mock_abspath, mock_join, mock_dirname, mock_read_csv):
        """Test categories retrieval when CSV file doesn't exist."""
        from exceptions import CSVProcessingError
        
        # Setup path mocks
        mock_dirname.return_value = "/test/dir"
        mock_join.return_value = "/test/dir/output.csv"
        mock_abspath.return_value = "/test/dir/main.py"
        
        mock_read_csv.side_effect = CSVProcessingError("CSV file not found at: /test/dir/output.csv")

        request = Request()
        logger = MagicMock()
        response = main.get_categories(request, None, logger)

        self.assertEqual(response.code, 404)
        self.assertIn("error", response.body)
        self.assertIn("Failed to read CSV file", response.body["error"])

    @patch("main.create_blocking_rule")
    def test_create_rule_success(self, mock_create_blocking_rule):
        """Test successful rule creation."""
        mock_create_blocking_rule.return_value = {
            "policy_id": "policy-123",
            "rule_group_id": "rule-group-456",
            "policy_name": "Test Policy"
        }

        request = Request()
        request.body = {
            "hostGroupId": "host-group-789",
            "urls": "example.com;malicious.com",
            "policyName": "Test Policy"
        }
        logger = MagicMock()

        response = main.create_rule(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertIn("message", response.body)
        self.assertIn("Successfully created blocking rule", response.body["message"])
        self.assertEqual(response.body["policyName"], "Test Policy")
        self.assertEqual(response.body["ruleGroupId"], "rule-group-456")
        self.assertEqual(response.body["policyId"], "policy-123")

    def test_create_rule_missing_fields(self):
        """Test rule creation with missing required fields."""
        request = Request()
        request.body = {
            "hostGroupId": "host-group-789"
            # Missing urls and policyName
        }
        logger = MagicMock()

        response = main.create_rule(request, None, logger)

        self.assertEqual(response.code, 400)
        self.assertIn("error", response.body)
        self.assertIn("urls is required", response.body["error"])

    def test_create_rule_no_body(self):
        """Test rule creation with no request body."""
        request = Request()
        logger = MagicMock()

        response = main.create_rule(request, None, logger)

        self.assertEqual(response.code, 400)
        self.assertIn("error", response.body)
        self.assertIn("Request body is required", response.body["error"])

    @patch("main.generate_domain_analytics")
    def test_get_domain_analytics_success(self, mock_generate_analytics):
        """Test successful domain analytics generation."""
        mock_generate_analytics.return_value = {
            'analysis': {'example.com': {'visit_count': 5}},
            'visualization_data': {'bar_chart': {'domains': ['example.com'], 'visits': [5]}}
        }

        request = Request()
        logger = MagicMock()
        response = main.get_domain_analytics(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertIn("analysis", response.body)
        self.assertIn("visualization_data", response.body)

    def test_healthz(self):
        """Test health check endpoint."""
        request = Request()
        response = main.healthz(request, None)

        self.assertEqual(response.code, 200)

    def test_validate_create_rule_request_success(self):
        """Test successful request validation."""
        request = Request()
        request.body = {
            "hostGroupId": "host-123",
            "urls": "example.com",
            "policyName": "Test Policy"
        }
        
        result = main.validate_create_rule_request(request)
        
        self.assertNotIn("error", result)
        self.assertEqual(result["host_group_id"], "host-123")
        self.assertEqual(result["urls"], "example.com")
        self.assertEqual(result["policy_name"], "Test Policy")

    def test_validate_create_rule_request_no_body(self):
        """Test request validation with no body."""
        request = Request()
        
        result = main.validate_create_rule_request(request)
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Request body is required")


if __name__ == "__main__":
    unittest.main()

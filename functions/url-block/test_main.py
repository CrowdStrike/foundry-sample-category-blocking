"""Test module for the url-block function handler."""

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


class FnTestCase(unittest.TestCase):
    """Test case class for function handler tests."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        patcher = patch("crowdstrike.foundry.function.Function.handler", new=mock_handler)
        self.addCleanup(patcher.stop)
        self.handler_patch = patcher.start()

        importlib.reload(main)

    def test_transform_csv_row(self):
        """Test CSV row transformation."""
        row = ["gaming", "example.com;gaming.com"]
        result = main.transform_csv_row(row)

        self.assertEqual(result["category"], "gaming")
        self.assertEqual(result["domain"], "example.com;gaming.com")
        self.assertEqual(result["wildcard_domain"], "")
        self.assertIn("imported_at", result)

    def test_validate_record_success(self):
        """Test record validation with valid record."""
        record = {
            "category": "gaming",
            "domain": "example.com"
        }
        # Should not raise exception
        main.validate_record(record)

    def test_validate_record_missing_category(self):
        """Test record validation with missing category."""
        record = {
            "domain": "example.com"
        }
        with self.assertRaises(ValueError) as context:
            main.validate_record(record)
        self.assertIn("Missing required field: category", str(context.exception))

    def test_validate_record_missing_domain(self):
        """Test record validation with missing domain."""
        record = {
            "category": "gaming"
        }
        with self.assertRaises(ValueError) as context:
            main.validate_record(record)
        self.assertIn("Missing required field: domain", str(context.exception))

    @patch("main.CustomStorage")
    @patch("builtins.open", new_callable=mock_open, read_data="category,domain\ngaming,example.com")
    def test_process_csv_records_success(self, _mock_file, mock_custom_storage):
        """Test successful CSV processing."""
        mock_customobjects = MagicMock()
        mock_custom_storage.return_value = mock_customobjects
        mock_customobjects.PutObject.return_value = {"status_code": 200}

        result = main.process_csv_records(
            csv_path="/fake/path.csv",
            customobjects=mock_customobjects,
            collection_name="domain",
            collection_version="v2.0"
        )

        self.assertEqual(result["total_rows"], 1)
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["error_count"], 0)
        mock_customobjects.PutObject.assert_called_once()

    @patch("main.CustomStorage")
    @patch("main.APIHarnessV2")
    @patch("main.cloud")
    @patch("os.path.dirname")
    @patch("os.path.join")
    @patch("os.path.abspath")
    def test_import_csv_handler_success(self, mock_abspath, mock_join, mock_dirname,
                                      mock_cloud, mock_api_harness, _mock_custom_storage):
        """Test successful CSV import handler."""
        # Setup mocks
        mock_dirname.return_value = "/test/dir"
        mock_join.return_value = "/test/dir/output.csv"
        mock_abspath.return_value = "/test/dir/main.py"
        mock_cloud.return_value = "https://api.crowdstrike.com"

        mock_api_client = MagicMock()
        mock_api_harness.return_value = mock_api_client
        mock_customobjects = MagicMock()
        _mock_custom_storage.return_value = mock_customobjects

        # Mock process_csv_records
        with patch.object(main, 'process_csv_records') as mock_process:
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

    @patch("main.CustomStorage")
    @patch("main.APIHarnessV2")
    @patch("main.cloud")
    def test_import_csv_handler_error(self, _mock_cloud, mock_api_harness, _mock_custom_storage):
        """Test CSV import handler with error."""
        # Setup mocks to raise exception
        mock_api_harness.side_effect = Exception("API connection failed")

        request = Request()
        response = main.import_csv_handler(request)

        self.assertEqual(response.code, 500)
        self.assertEqual(len(response.errors), 1)
        self.assertIn("CSV import failed", response.errors[0].message)

    @patch("main.HostGroup")
    @patch("main.APIHarnessV2")
    @patch("main.cloud")
    def test_on_create_success(self, mock_cloud, mock_api_harness, mock_host_group):
        """Test successful host groups handler."""
        # Setup mocks
        mock_cloud.return_value = "https://api.crowdstrike.com"
        mock_falcon = MagicMock()
        mock_api_harness.return_value = mock_falcon
        mock_hostgroup = MagicMock()
        mock_host_group.return_value = mock_hostgroup

        # Mock host group query responses
        mock_hostgroup.query_host_groups.return_value = {
            "status_code": 200,
            "body": {"resources": ["group-1", "group-2"]}
        }
        mock_hostgroup.get_host_groups.return_value = {
            "body": {
                "resources": [
                    {"id": "group-1", "name": "Group 1"},
                    {"id": "group-2", "name": "Group 2"}
                ]
            }
        }

        request = Request()
        logger = MagicMock()
        response = main.on_create(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertIn("host_groups", response.body)
        self.assertEqual(len(response.body["host_groups"]), 2)
        self.assertEqual(response.body["host_groups"][0]["id"], "group-1")
        self.assertEqual(response.body["host_groups"][0]["name"], "Group 1")

    @patch("main.HostGroup")
    @patch("main.APIHarnessV2")
    def test_on_create_api_error(self, mock_api_harness, _mock_host_group):
        """Test host groups handler with API error."""
        # Setup mocks to simulate API initialization failure
        mock_api_harness.side_effect = Exception("API initialization failed")

        request = Request()
        logger = MagicMock()
        response = main.on_create(request, None, logger)

        self.assertEqual(response.code, 500)
        self.assertIn("error", response.body)
        self.assertIn("Falcon client initialization failed", response.body["error"])

    @patch("os.path.exists")
    @patch("os.path.dirname")
    @patch("os.path.join")
    @patch("os.path.abspath")
    @patch("builtins.open", new_callable=mock_open, read_data="category,urls\ngaming,example.com;gaming.org")
    def test_get_categories_success(self, _mock_file, mock_abspath, mock_join, mock_dirname, mock_exists):
        """Test successful categories retrieval."""
        # Setup path mocks
        mock_dirname.return_value = "/test/dir"
        mock_join.return_value = "/test/dir/output.csv"
        mock_abspath.return_value = "/test/dir/main.py"
        mock_exists.return_value = True

        request = Request()
        logger = MagicMock()
        response = main.get_categories(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertIn("categories", response.body)
        self.assertIn("gaming", response.body["categories"])
        self.assertEqual(response.body["categories"]["gaming"], "example.com;gaming.org")

    @patch("os.path.exists")
    @patch("os.path.dirname")
    @patch("os.path.join")
    @patch("os.path.abspath")
    def test_get_categories_file_not_found(self, mock_abspath, mock_join, mock_dirname, mock_exists):
        """Test categories retrieval when CSV file doesn't exist."""
        # Setup path mocks
        mock_dirname.return_value = "/test/dir"
        mock_join.return_value = "/test/dir/output.csv"
        mock_abspath.return_value = "/test/dir/main.py"
        mock_exists.return_value = False

        request = Request()
        logger = MagicMock()
        response = main.get_categories(request, None, logger)

        self.assertEqual(response.code, 404)
        self.assertIn("error", response.body)
        self.assertIn("CSV file not found", response.body["error"])

    @patch("main.FirewallPolicies")
    @patch("main.FirewallManagement")
    @patch("main.APIHarnessV2")
    @patch("main.cloud")
    def test_create_rule_success(self, mock_cloud, mock_api_harness, mock_firewall_mgmt, mock_firewall_policies):
        """Test successful rule creation."""
        # Setup mocks
        mock_cloud.return_value = "https://api.crowdstrike.com"
        mock_falcon = MagicMock()
        mock_api_harness.return_value = mock_falcon

        mock_mgmt = MagicMock()
        mock_firewall_mgmt.return_value = mock_mgmt
        mock_policies = MagicMock()
        mock_firewall_policies.return_value = mock_policies

        # Mock policy creation response
        mock_policies.create_policies.return_value = {
            "body": {"resources": [{"id": "policy-123"}]}
        }
        mock_policies.perform_action.return_value = {"status_code": 200}

        # Mock rule group creation response
        mock_mgmt.create_rule_group.return_value = {
            "body": {"resources": ["rule-group-456"]}
        }
        mock_mgmt.update_policy_container.return_value = {"status_code": 200}

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

    def test_healthz(self):
        """Test health check endpoint."""
        request = Request()
        response = main.healthz(request, None)

        self.assertEqual(response.code, 200)


if __name__ == "__main__":
    unittest.main()

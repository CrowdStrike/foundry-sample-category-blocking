"""Test module for firewall management utilities."""

import unittest
from unittest.mock import patch, MagicMock

from firewall_manager import (
    initialize_falcon_client, get_host_groups, create_firewall_policy,
    enable_policy_and_add_host_group, create_rule_group, update_policy_with_rule_group,
    create_blocking_rule, get_rule_group_details, update_rule_group_with_new_urls
)
from exceptions import FirewallAPIError, PolicyError, RuleGroupError


class TestFirewallManager(unittest.TestCase):
    """Test cases for firewall management functions."""

    @patch("firewall_manager.APIHarnessV2")
    def test_initialize_falcon_client_success(self, mock_api_harness):
        """Test successful Falcon client initialization."""
        mock_client = MagicMock()
        mock_api_harness.return_value = mock_client
        
        result = initialize_falcon_client()
        
        self.assertEqual(result, mock_client)
        mock_api_harness.assert_called_once_with(debug=True)

    @patch("firewall_manager.APIHarnessV2")
    def test_initialize_falcon_client_error(self, mock_api_harness):
        """Test Falcon client initialization error."""
        mock_api_harness.side_effect = Exception("Connection failed")
        
        with self.assertRaises(FirewallAPIError) as context:
            initialize_falcon_client()
        self.assertIn("Failed to initialize Falcon client", str(context.exception))

    @patch("firewall_manager.HostGroup")
    @patch("firewall_manager.initialize_falcon_client")
    @patch("firewall_manager.cloud")
    def test_get_host_groups_success(self, mock_cloud, mock_init_client, mock_host_group):
        """Test successful host groups retrieval."""
        mock_cloud.return_value = "https://api.crowdstrike.com"
        mock_falcon = MagicMock()
        mock_init_client.return_value = mock_falcon
        mock_hostgroup = MagicMock()
        mock_host_group.return_value = mock_hostgroup

        # Mock host group query responses
        mock_hostgroup.query_host_groups.return_value = {
            "status_code": 200,
            "body": {"resources": ["group-1", "group-2"]}
        }
        mock_hostgroup.get_host_groups.return_value = {
            "status_code": 200,
            "body": {
                "resources": [
                    {"id": "group-1", "name": "Group 1"},
                    {"id": "group-2", "name": "Group 2"}
                ]
            }
        }

        result = get_host_groups()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "group-1")
        self.assertEqual(result[0]["name"], "Group 1")

    @patch("firewall_manager.FirewallPolicies")
    @patch("firewall_manager.initialize_falcon_client")
    @patch("firewall_manager.cloud")
    def test_create_firewall_policy_success(self, mock_cloud, mock_init_client, mock_policies_class):
        """Test successful firewall policy creation."""
        mock_cloud.return_value = "https://api.crowdstrike.com"
        mock_falcon = MagicMock()
        mock_init_client.return_value = mock_falcon
        mock_policies = MagicMock()
        mock_policies_class.return_value = mock_policies

        mock_policies.create_policies.return_value = {
            "body": {"resources": [{"id": "policy-123"}]}
        }

        result = create_firewall_policy("Test Policy")

        self.assertEqual(result, "policy-123")
        mock_policies.create_policies.assert_called_once()

    @patch("firewall_manager.FirewallPolicies")
    @patch("firewall_manager.initialize_falcon_client")
    @patch("firewall_manager.cloud")
    def test_create_firewall_policy_invalid_response(self, mock_cloud, mock_init_client, mock_policies_class):
        """Test firewall policy creation with invalid response."""
        mock_cloud.return_value = "https://api.crowdstrike.com"
        mock_falcon = MagicMock()
        mock_init_client.return_value = mock_falcon
        mock_policies = MagicMock()
        mock_policies_class.return_value = mock_policies

        mock_policies.create_policies.return_value = {"invalid": "response"}

        with self.assertRaises(PolicyError) as context:
            create_firewall_policy("Test Policy")
        self.assertIn("Invalid policy creation response", str(context.exception))

    @patch("firewall_manager.create_rule_group")
    @patch("firewall_manager.enable_policy_and_add_host_group")
    @patch("firewall_manager.create_firewall_policy")
    @patch("firewall_manager.update_policy_with_rule_group")
    def test_create_blocking_rule_success(self, mock_update_policy, mock_create_policy, 
                                        mock_enable_policy, mock_create_rule_group):
        """Test successful blocking rule creation."""
        mock_create_policy.return_value = "policy-123"
        mock_enable_policy.return_value = True
        mock_create_rule_group.return_value = "rule-group-456"
        mock_update_policy.return_value = True

        result = create_blocking_rule("host-group-789", "example.com;malicious.com", "Test Policy")

        self.assertEqual(result["policy_id"], "policy-123")
        self.assertEqual(result["rule_group_id"], "rule-group-456")
        self.assertEqual(result["policy_name"], "Test Policy")

    def test_create_blocking_rule_no_valid_urls(self):
        """Test blocking rule creation with no valid URLs."""
        with self.assertRaises(RuleGroupError) as context:
            create_blocking_rule("host-group-789", "   ;  ; ", "Test Policy")
        self.assertIn("No valid URLs provided", str(context.exception))


if __name__ == "__main__":
    unittest.main()

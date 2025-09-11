"""Test module for analytics processing utilities."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from analytics_processor import (
    initialize_firewall_management, fetch_firewall_events, analyze_domain_events,
    prepare_visualization_data, generate_domain_analytics
)
from exceptions import AnalyticsError, FirewallAPIError


class TestAnalyticsProcessor(unittest.TestCase):
    """Test cases for analytics processing functions."""

    @patch("analytics_processor.FirewallManagement")
    @patch("analytics_processor.APIHarnessV2")
    @patch("analytics_processor.cloud")
    def test_initialize_firewall_management_success(self, mock_cloud, mock_api_harness, mock_firewall_mgmt):
        """Test successful firewall management initialization."""
        mock_cloud.return_value = "https://api.crowdstrike.com"
        mock_falcon = MagicMock()
        mock_api_harness.return_value = mock_falcon
        mock_mgmt = MagicMock()
        mock_firewall_mgmt.return_value = mock_mgmt
        
        result = initialize_firewall_management()
        
        self.assertEqual(result, mock_mgmt)
        mock_api_harness.assert_called_once_with(debug=True)

    @patch("analytics_processor.FirewallManagement")
    @patch("analytics_processor.APIHarnessV2")
    def test_initialize_firewall_management_error(self, mock_api_harness, mock_firewall_mgmt):
        """Test firewall management initialization error."""
        mock_api_harness.side_effect = Exception("Connection failed")
        
        with self.assertRaises(FirewallAPIError) as context:
            initialize_firewall_management()
        self.assertIn("Failed to initialize firewall management", str(context.exception))

    @patch("analytics_processor.initialize_firewall_management")
    def test_fetch_firewall_events_success(self, mock_init_mgmt):
        """Test successful firewall events fetching."""
        mock_mgmt = MagicMock()
        mock_init_mgmt.return_value = mock_mgmt
        
        # Mock query response
        mock_mgmt.query_events.return_value = {
            'status_code': 200,
            'body': {'resources': ['event-1', 'event-2']}
        }
        
        # Mock get events response
        mock_mgmt.get_events.return_value = {
            'status_code': 200,
            'body': {
                'resources': [
                    {
                        'domain_name_list': 'example.com',
                        'timestamp': '2023-01-01T00:00:00Z',
                        'remote_address': '192.168.1.1',
                        'host_name': 'test-host',
                        'policy_name': 'test-policy',
                        'rule_name': 'test-rule'
                    }
                ]
            }
        }
        
        result = fetch_firewall_events(days_back=1, limit=100)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['domain'], 'example.com')
        self.assertEqual(result[0]['host_name'], 'test-host')

    def test_analyze_domain_events_success(self):
        """Test successful domain events analysis."""
        events = [
            {
                'domain': 'example.com',
                'timestamp': '2023-01-01T00:00:00Z',
                'remote_address': '192.168.1.1',
                'host_name': 'host1',
                'policy_name': 'policy1',
                'rule_name': 'rule1'
            },
            {
                'domain': 'example.com',
                'timestamp': '2023-01-01T01:00:00Z',
                'remote_address': '192.168.1.2',
                'host_name': 'host2',
                'policy_name': 'policy1',
                'rule_name': 'rule1'
            }
        ]
        
        result = analyze_domain_events(events)
        
        self.assertIn('domain_analysis', result)
        self.assertIn('top_domains', result)
        self.assertIn('total_blocks', result)
        self.assertEqual(result['total_blocks'], 2)
        self.assertIn('example.com', result['domain_analysis'])
        self.assertEqual(result['domain_analysis']['example.com']['visit_count'], 2)

    def test_prepare_visualization_data_success(self):
        """Test successful visualization data preparation."""
        analysis_data = {
            'top_domains': [('example.com', 5), ('test.com', 3)],
            'domain_analysis': {
                'example.com': {'unique_ips': 2},
                'test.com': {'unique_ips': 1}
            },
            'total_blocks': 8,
            'unique_hosts': {'host1', 'host2'}
        }
        
        result = prepare_visualization_data(analysis_data)
        
        self.assertIn('bar_chart', result)
        self.assertIn('comparison_chart', result)
        self.assertIn('summary', result)
        self.assertEqual(result['bar_chart']['domains'], ['example.com', 'test.com'])
        self.assertEqual(result['bar_chart']['visits'], [5, 3])
        self.assertEqual(result['summary']['total_blocks'], 8)

    @patch("analytics_processor.prepare_visualization_data")
    @patch("analytics_processor.analyze_domain_events")
    @patch("analytics_processor.fetch_firewall_events")
    def test_generate_domain_analytics_success(self, mock_fetch_events, mock_analyze_events, mock_prepare_viz):
        """Test successful domain analytics generation."""
        # Mock the chain of function calls
        mock_events = [{'domain': 'example.com'}]
        mock_fetch_events.return_value = mock_events
        
        mock_analysis = {'domain_analysis': {'example.com': {'visit_count': 1}}}
        mock_analyze_events.return_value = mock_analysis
        
        mock_viz_data = {'bar_chart': {'domains': ['example.com'], 'visits': [1]}}
        mock_prepare_viz.return_value = mock_viz_data
        
        result = generate_domain_analytics()
        
        self.assertIn('analysis', result)
        self.assertIn('visualization_data', result)
        mock_fetch_events.assert_called_once_with(days_back=15)
        mock_analyze_events.assert_called_once_with(mock_events)
        mock_prepare_viz.assert_called_once_with(mock_analysis)

    @patch("analytics_processor.fetch_firewall_events")
    def test_generate_domain_analytics_no_events(self, mock_fetch_events):
        """Test domain analytics generation with no events."""
        mock_fetch_events.return_value = []
        
        result = generate_domain_analytics()
        
        self.assertIn('analysis', result)
        self.assertIn('visualization_data', result)
        self.assertEqual(result['analysis'], {})
        self.assertEqual(result['visualization_data']['summary']['total_blocks'], 0)


if __name__ == "__main__":
    unittest.main()

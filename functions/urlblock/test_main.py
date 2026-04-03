"""Test module for the urlblock function handlers.

Validates that handlers use versioned Custom Storage methods (PutObjectByVersion,
GetVersionedObject) instead of unversioned methods (PutObject, GetObject).
"""

import importlib
import io
import json
import unittest
from unittest.mock import patch, MagicMock

from crowdstrike.foundry.function import Request

import main


def mock_handler(*_args, **_kwargs):
    """Mock handler decorator for testing."""

    def identity(func):
        return func

    return identity


class ManageCategoryTestCase(unittest.TestCase):
    """Tests for the POST /manage-category handler."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        patcher = patch("crowdstrike.foundry.function.Function.handler", new=mock_handler)
        self.addCleanup(patcher.stop)
        self.handler_patch = patcher.start()

        importlib.reload(main)

    @patch('main.CustomStorage')
    def test_manage_category_success(self, mock_custom_storage_class):
        """Test successful category creation uses PutObjectByVersion."""
        mock_api = MagicMock()
        mock_custom_storage_class.return_value = mock_api
        mock_api.PutObjectByVersion.return_value = {
            "status_code": 200,
            "body": {"success": True}
        }

        request = Request()
        request.body = {
            "categoryName": "Games",
            "urls": "steam.com,epicgames.com"
        }

        logger = MagicMock()
        response = main.manage_category(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertTrue(response.body["success"])
        self.assertEqual(response.body["categoryName"], "Games")

        # Verify VERSIONED method is called
        mock_api.PutObjectByVersion.assert_called_once()
        put_call = mock_api.PutObjectByVersion.call_args
        self.assertEqual(put_call[1]["collection_version"], "v2.0")
        self.assertEqual(put_call[1]["collection_name"], "domain")
        self.assertEqual(put_call[1]["object_key"], "Games")
        self.assertIn("category", put_call[1]["body"])
        self.assertEqual(put_call[1]["body"]["category"], "Games")

        # Verify UNVERSIONED method is NOT called
        mock_api.PutObject.assert_not_called()

    def test_manage_category_missing_name(self):
        """Test that missing category name returns 400."""
        request = Request()
        request.body = {
            "categoryName": "",
            "urls": "steam.com"
        }

        logger = MagicMock()
        response = main.manage_category(request, None, logger)

        self.assertEqual(response.code, 400)
        self.assertEqual(response.body["error"], "Category name is required")

    def test_manage_category_missing_urls(self):
        """Test that missing URLs returns 400."""
        request = Request()
        request.body = {
            "categoryName": "Games",
            "urls": ""
        }

        logger = MagicMock()
        response = main.manage_category(request, None, logger)

        self.assertEqual(response.code, 400)
        self.assertEqual(response.body["error"], "URLs are required")

    @patch('main.CustomStorage')
    def test_manage_category_api_error(self, mock_custom_storage_class):
        """Test that a non-200 API response returns 500."""
        mock_api = MagicMock()
        mock_custom_storage_class.return_value = mock_api
        mock_api.PutObjectByVersion.return_value = {
            "status_code": 500,
            "body": {"message": "Internal server error"}
        }

        request = Request()
        request.body = {
            "categoryName": "Games",
            "urls": "steam.com"
        }

        logger = MagicMock()
        response = main.manage_category(request, None, logger)

        self.assertEqual(response.code, 500)
        self.assertIn("error", response.body)


class SearchCategoriesTestCase(unittest.TestCase):
    """Tests for the GET /search-categories handler."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        patcher = patch("crowdstrike.foundry.function.Function.handler", new=mock_handler)
        self.addCleanup(patcher.stop)
        self.handler_patch = patcher.start()

        importlib.reload(main)

    @patch('main.CustomStorage')
    def test_search_categories_success(self, mock_custom_storage_class):
        """Test successful search uses GetVersionedObject."""
        mock_api = MagicMock()
        mock_custom_storage_class.return_value = mock_api
        mock_api.GetVersionedObject.return_value = json.dumps({
            "resources": [{"category": "Games", "domain": "steam.com"}]
        }).encode("utf-8")

        request = Request()
        request.body = {"category": "Games", "limit": 10}

        response = main.search_categories(request)

        self.assertEqual(response.code, 200)

        # Verify VERSIONED method is called
        mock_api.GetVersionedObject.assert_called_once()
        get_call = mock_api.GetVersionedObject.call_args
        self.assertEqual(get_call[1]["collection_version"], "v2.0")
        self.assertEqual(get_call[1]["collection_name"], "domain")

        # Verify UNVERSIONED method is NOT called
        mock_api.GetObject.assert_not_called()

    @patch('main.CustomStorage')
    def test_search_categories_error(self, mock_custom_storage_class):
        """Test search error handling returns 500."""
        mock_custom_storage_class.side_effect = Exception("Connection failed")

        request = Request()
        request.body = {}

        response = main.search_categories(request)

        self.assertEqual(response.code, 500)
        self.assertEqual(len(response.errors), 1)
        self.assertIn("Connection failed", response.errors[0].message)


class ProcessCsvRecordsTestCase(unittest.TestCase):
    """Tests for the process_csv_records helper function."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        patcher = patch("crowdstrike.foundry.function.Function.handler", new=mock_handler)
        self.addCleanup(patcher.stop)
        self.handler_patch = patcher.start()

        importlib.reload(main)

    @patch('builtins.open')
    def test_process_csv_records_uses_versioned_method(self, mock_open):
        """Test that process_csv_records calls PutObjectByVersion."""
        csv_content = "category,urls\nGames,steam.com\n"
        mock_open.return_value.__enter__ = lambda s: io.StringIO(csv_content)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        mock_api = MagicMock()

        results = main.process_csv_records(
            csv_path="/fake/path.csv",
            custom_storage=mock_api,
            collection_name="domain",
            collection_version="v2.0"
        )

        # Verify VERSIONED method is called
        mock_api.PutObjectByVersion.assert_called_once()
        put_call = mock_api.PutObjectByVersion.call_args
        self.assertEqual(put_call[1]["collection_version"], "v2.0")
        self.assertEqual(put_call[1]["collection_name"], "domain")

        # Verify UNVERSIONED method is NOT called
        mock_api.PutObject.assert_not_called()

        self.assertEqual(results["success_count"], 1)


class ManageRelationshipTestCase(unittest.TestCase):
    """Tests for the POST /manage-relationship handler."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        patcher = patch("crowdstrike.foundry.function.Function.handler", new=mock_handler)
        self.addCleanup(patcher.stop)
        self.handler_patch = patcher.start()

        importlib.reload(main)

    @patch('main.CustomStorage')
    def test_manage_relationship_success(self, mock_custom_storage_class):
        """Test successful relationship creation uses PutObjectByVersion with v5.0."""
        mock_api = MagicMock()
        mock_custom_storage_class.return_value = mock_api
        mock_api.PutObjectByVersion.return_value = {
            "status_code": 200,
            "body": {"success": True}
        }

        request = Request()
        request.body = {
            "category_name": "Games",
            "rule_group_id": "rg-123",
            "rule_group_name": "Games_RuleGroup",
            "host_group_id": "hg-456",
            "host_group_name": "Test Hosts",
            "policy_name": "Games_Policy",
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": "test-user"
        }

        logger = MagicMock()
        response = main.manage_relationship(request, None, logger)

        self.assertEqual(response.code, 200)
        self.assertTrue(response.body["success"])
        self.assertEqual(response.body["relationshipId"], "Games_rg-123_hg-456")

        # Verify VERSIONED method is called with v5.0
        mock_api.PutObjectByVersion.assert_called_once()
        put_call = mock_api.PutObjectByVersion.call_args
        self.assertEqual(put_call[1]["collection_version"], "v5.0")
        self.assertEqual(put_call[1]["collection_name"], "relationship")
        self.assertEqual(put_call[1]["object_key"], "Games_rg-123_hg-456")
        self.assertEqual(put_call[1]["body"]["category_name"], "Games")
        self.assertEqual(put_call[1]["body"]["rule_group_id"], "rg-123")
        self.assertEqual(put_call[1]["body"]["host_group_id"], "hg-456")

        # Verify UNVERSIONED method is NOT called
        mock_api.PutObject.assert_not_called()

    def test_manage_relationship_missing_fields(self):
        """Test that missing required fields returns 400."""
        request = Request()
        request.body = {
            "category_name": "Games",
            "rule_group_id": "",
            "host_group_id": ""
        }

        logger = MagicMock()
        response = main.manage_relationship(request, None, logger)

        self.assertEqual(response.code, 400)
        self.assertIn("missing_fields", response.body)
        self.assertIn("rule_group_id", response.body["missing_fields"])
        self.assertIn("host_group_id", response.body["missing_fields"])


if __name__ == "__main__":
    unittest.main()

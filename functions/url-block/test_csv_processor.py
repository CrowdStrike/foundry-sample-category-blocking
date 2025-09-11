"""Test module for CSV processing utilities."""

import unittest
from unittest.mock import patch, mock_open, MagicMock

from csv_processor import transform_csv_row, validate_record, process_csv_records, read_categories_from_csv
from exceptions import CSVProcessingError, ValidationError


class TestCSVProcessor(unittest.TestCase):
    """Test cases for CSV processing functions."""

    def test_transform_csv_row_success(self):
        """Test CSV row transformation with valid data."""
        row = ["gaming", "example.com;gaming.com"]
        result = transform_csv_row(row)

        self.assertEqual(result["category"], "gaming")
        self.assertEqual(result["domain"], "example.com;gaming.com")
        self.assertEqual(result["wildcard_domain"], "")
        self.assertIn("imported_at", result)

    def test_transform_csv_row_invalid_length(self):
        """Test CSV row transformation with insufficient columns."""
        row = ["gaming"]  # Only one column
        with self.assertRaises(ValidationError):
            transform_csv_row(row)

    def test_transform_csv_row_empty_category(self):
        """Test CSV row transformation with empty category."""
        row = ["", "example.com"]  # Empty category
        with self.assertRaises(ValidationError):
            transform_csv_row(row)

    def test_validate_record_success(self):
        """Test record validation with valid record."""
        record = {
            "category": "gaming",
            "domain": "example.com"
        }
        # Should not raise exception
        validate_record(record)

    def test_validate_record_missing_category(self):
        """Test record validation with missing category."""
        record = {
            "domain": "example.com"
        }
        with self.assertRaises(ValidationError) as context:
            validate_record(record)
        self.assertIn("Missing required field: category", str(context.exception))

    def test_validate_record_missing_domain(self):
        """Test record validation with missing domain."""
        record = {
            "category": "gaming"
        }
        with self.assertRaises(ValidationError) as context:
            validate_record(record)
        self.assertIn("Missing required field: domain", str(context.exception))

    @patch("builtins.open", new_callable=mock_open, read_data="category,domain\ngaming,example.com")
    @patch("os.path.exists")
    def test_process_csv_records_success(self, mock_exists, _mock_file):
        """Test successful CSV processing."""
        mock_exists.return_value = True
        mock_customobjects = MagicMock()
        mock_customobjects.PutObject.return_value = {"status_code": 200}

        result = process_csv_records(
            csv_path="/fake/path.csv",
            customobjects=mock_customobjects,
            collection_name="domain",
            collection_version="v2.0"
        )

        self.assertEqual(result["total_rows"], 1)
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["error_count"], 0)
        mock_customobjects.PutObject.assert_called_once()

    def test_process_csv_records_file_not_found(self):
        """Test CSV processing with non-existent file."""
        mock_customobjects = MagicMock()

        with self.assertRaises(CSVProcessingError) as context:
            process_csv_records(
                csv_path="/nonexistent/path.csv",
                customobjects=mock_customobjects
            )
        self.assertIn("CSV file not found", str(context.exception))

    @patch("builtins.open", new_callable=mock_open, read_data="category,urls\ngaming,example.com;gaming.org")
    @patch("os.path.exists")
    def test_read_categories_from_csv_success(self, mock_exists, _mock_file):
        """Test successful categories reading from CSV."""
        mock_exists.return_value = True

        result = read_categories_from_csv("/fake/path.csv")

        self.assertIn("gaming", result)
        self.assertEqual(result["gaming"], "example.com;gaming.org")

    def test_read_categories_from_csv_file_not_found(self):
        """Test categories reading with non-existent file."""
        with self.assertRaises(CSVProcessingError) as context:
            read_categories_from_csv("/nonexistent/path.csv")
        self.assertIn("CSV file not found", str(context.exception))


if __name__ == "__main__":
    unittest.main()

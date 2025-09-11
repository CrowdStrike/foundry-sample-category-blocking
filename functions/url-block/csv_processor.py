"""CSV processing utilities for URL filtering."""

import csv
import os
import time

from exceptions import CSVProcessingError, ValidationError


def transform_csv_row(row):
    """Transform a CSV row to match the Collection schema."""
    if len(row) < 2:
        raise ValidationError("CSV row must have at least 2 columns")

    category = row[0].strip()
    urls = row[1]

    if not category:
        raise ValidationError("Category cannot be empty")

    record = {
        "category": category,
        "domain": urls,  # Keep all URLs in domain field
        "wildcard_domain": "",  # Add wildcard for category
        "imported_at": int(time.time())
    }

    return record


def validate_record(record):
    """Validate that record meets schema requirements."""
    if not record.get('category'):
        raise ValidationError("Missing required field: category")
    if not record.get('domain'):
        raise ValidationError("Missing required field: domain")


def process_csv_records(csv_path, customobjects, collection_name="domain", collection_version="v2.0"):
    """Process CSV records and create collection objects."""
    success_count = 0
    error_count = 0
    total_rows = 0

    if not os.path.exists(csv_path):
        raise CSVProcessingError(f"CSV file not found: {csv_path}")

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            next(csv_reader)  # Skip header row

            for row in csv_reader:
                total_rows += 1
                try:
                    if len(row) >= 2:
                        # Transform row into record
                        record = transform_csv_row(row)

                        # Validate record
                        validate_record(record)

                        # Create collection object
                        customobjects.PutObject(
                            body=record,
                            collection_name=collection_name,
                            collection_version=collection_version,
                            object_key=record['category'],
                            limit=1000
                        )

                        success_count += 1

                except (ValidationError, CSVProcessingError) as e:
                    error_count += 1
                    print(f"Error processing row {total_rows}: {str(e)}")
                    continue

    except (OSError, IOError) as e:
        raise CSVProcessingError(f"Error reading CSV file: {str(e)}") from e

    return {
        "total_rows": total_rows,
        "success_count": success_count,
        "error_count": error_count
    }


def read_categories_from_csv(csv_file):
    """Read categories from CSV file and return as dictionary."""
    if not os.path.exists(csv_file):
        raise CSVProcessingError(f"CSV file not found at: {csv_file}")

    categories_dict = {}
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            csv_reader = csv.reader(f)
            next(csv_reader)  # Skip header row

            for row in csv_reader:
                if len(row) >= 2:  # Ensure row has at least 2 columns
                    category = row[0].strip()
                    urls = row[1].strip()

                    # Clean and format URLs
                    url_list = [url.strip() for url in urls.split(';') if url.strip()]
                    if url_list:  # Only add if there are valid URLs
                        clean_urls = ';'.join(url_list)
                        categories_dict[category] = clean_urls

    except (OSError, IOError) as e:
        raise CSVProcessingError(f"Error reading CSV file: {str(e)}") from e

    return categories_dict

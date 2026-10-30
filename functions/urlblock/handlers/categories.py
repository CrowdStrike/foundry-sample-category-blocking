"""Handlers for managing domain categories and importing them from CSV."""

# Handlers deliberately catch every exception to log it and return a 500 response.
# pylint: disable=broad-exception-caught

import csv
import io
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging import Logger

import pytz
from crowdstrike.foundry.function import APIError, Request, Response
from falconpy import CustomStorage

from app_core import FUNC, get_client, COLLECTION_DOMAIN_VER
from app_utils import (
    _sanitize_url_list, category_key, query_param,
    list_object_keys, read_all_objects, get_object, StorageError,
)

# ---------------------------------------------------------------------------
# CSV Helpers
# ---------------------------------------------------------------------------

def validate_record(record):
    """Validate that record meets schema requirements."""
    if not record.get('category'):
        raise ValueError("Missing required field: category")
    if not record.get('domain'):
        raise ValueError("Missing required field: domain")


def _existing_keys(custom_storage):
    """All object keys currently in the domain collection (empty list if it cannot be read)."""
    result = list_object_keys(custom_storage, 'domain', COLLECTION_DOMAIN_VER)
    return [] if "error" in result else result["keys"]


def _merge_domains(*domain_strings):
    """Union of ';'-separated domain strings, preserving first-seen order."""
    seen, merged = set(), []
    for value in domain_strings:
        for d in (value or '').split(';'):
            d = d.strip()
            if d and d not in seen:
                seen.add(d)
                merged.append(d)
    return merged


# pylint: disable-next=too-many-locals
def process_csv_records(csv_path=None, custom_storage=None, logger=None, collection_name="domain",
                        collection_version=COLLECTION_DOMAIN_VER, max_workers=10, csv_text=None):
    """
    Process a `category,url` CSV (one row per domain, rows may also hold ';'-separated lists)
    and write ONE collection object per category, in parallel.

    Rows are grouped by normalized category key; domains are validated, de-duplicated and
    get their *.domain wildcard. Returns row, category, domain and error counts.
    """
    error_count = 0
    total_rows = 0
    categories_map = {}  # category_key -> {"category": display name, "domains": [..]}
    # lower-cased key -> actual key: keys that differ only by case are treated as conflicts
    keys_by_lower = {k.lower(): k for k in _existing_keys(custom_storage)} if custom_storage else {}

    def _read_rows(file):
        nonlocal error_count, total_rows
        csv_reader = csv.reader(file)
        for index, row in enumerate(csv_reader):
            if index == 0 and row and row[0].strip().lower().lstrip('\ufeff') == 'category':
                continue  # header row
            total_rows += 1
            try:
                if len(row) < 2:
                    continue
                record = {"category": row[0].strip(), "domain": row[1].strip()}
                validate_record(record)
                domains = _sanitize_url_list(record["domain"], separator=';')
                if not domains:
                    raise ValueError(f"No valid domain in '{record['domain']}'")
                key = category_key(record["category"])
                existing = keys_by_lower.setdefault(key.lower(), key)
                if existing != key:
                    raise ValueError(f"Category '{record['category']}' conflicts with existing key "
                                     f"'{existing}' (differs only by case)")
                entry = categories_map.setdefault(key, {"category": record["category"], "domains": []})
                entry["domains"] = _merge_domains(';'.join(entry["domains"]), ';'.join(domains))
            except ValueError as e:
                error_count += 1
                logger.error(f"Error processing row {total_rows}: {str(e)}")

    if csv_text is not None:
        _read_rows(io.StringIO(csv_text))
    else:
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                _read_rows(file)
        except IOError as e:
            raise IOError(f"Error reading CSV file: {str(e)}") from e

    def _put(key, entry):
        resp = custom_storage.PutObjectByVersion(
            body={
                "category": entry["category"],
                "domain": ';'.join(entry["domains"]),
                "wildcard_domain": "",
                "imported_at": int(time.time())
            },
            collection_name=collection_name,
            collection_version=collection_version,
            object_key=key
        )
        if isinstance(resp, dict) and resp.get('status_code', 200) >= 400:
            raise RuntimeError(f"HTTP {resp.get('status_code')}")

    success_count = 0
    domains_imported = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [(k, e, executor.submit(_put, k, e)) for k, e in categories_map.items()]
        for _, entry, future in futures:
            try:
                future.result()
                success_count += 1
                domains_imported += len(entry["domains"])
            except Exception as e:
                error_count += 1
                logger.error(f"Error writing category {entry['category']}: {str(e)}")

    return {
        "total_rows": total_rows,
        "success_count": success_count,
        "domains_imported": domains_imported,
        "error_count": error_count
    }


# ===========================================================================
# Handlers
# ===========================================================================

@FUNC.handler(method='POST', path='/import-csv')
def import_csv_handler(request: Request, _: dict, logger: Logger) -> Response:
    """Import domain categorization CSV data (sent as text in `csv`) into a Foundry Collection."""
    logger.info("Starting /import-csv handler")
    try:
        csv_text = request.body.get('csv') if request.body else None
        if not isinstance(csv_text, str) or not csv_text.strip():
            return Response(code=400, body={"error": "CSV content is required in the 'csv' field"})

        custom_storage = get_client(CustomStorage)

        results = process_csv_records(
            csv_text=csv_text,
            custom_storage=custom_storage,
            logger=logger,
            collection_name="domain",
            collection_version=COLLECTION_DOMAIN_VER
        )
        logger.info(f"Successfully completed /import-csv: {results['success_count']} rows imported")
        return Response(
            body={
                "success": True,
                "total_rows": results["total_rows"],
                "successful_imports": results["success_count"],
                "domains_imported": results["domains_imported"],
                "failed_imports": results["error_count"],
                "collection_name": "domain",
                "source_file": "request body",
                "import_timestamp": int(time.time())
            },
            code=200
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"CSV import failed: {str(e)}")]
        )


@FUNC.handler(method='GET', path='/list-categories')
def list_categories(request: Request, _: dict, logger: Logger) -> Response:
    """List all categories from the domain collection."""
    logger.info("Starting /list-categories handler")
    try:
        custom_storage = get_client(CustomStorage)
        try:
            page_size = max(1, min(int(query_param(request, 'limit', '200')), 500))
        except ValueError:
            page_size = 200
        try:
            max_pages = max(1, int(query_param(request, 'max_pages', '50')))
        except ValueError:
            max_pages = 50

        result = read_all_objects(custom_storage, 'domain', COLLECTION_DOMAIN_VER,
                                  page_size=page_size, max_pages=max_pages, logger=logger)
        if "error" in result:
            return Response(code=500, errors=[APIError(code=500, message=f"API Error: {result['error']}")])

        resources = result['resources']
        categories = set()
        domains = []

        for item in resources:
            try:
                if item and isinstance(item, dict):
                    if item.get('category'):
                        categories.add(item['category'])
                    domains.append({
                        'category': item.get('category', ''),
                        'domain': item.get('domain', ''),
                        'wildcard_domain': item.get('wildcard_domain', '')
                    })
            except Exception:
                continue

        logger.info("Successfully completed /list-categories")
        return Response(
            body={
                "total_items": len(resources),
                "unique_categories": len(categories),
                "categories": sorted(list(categories)),
                "domains": domains,
                "metadata": {"limit": page_size, "timestamp": int(time.time())},
                "pagination": result["pagination"],
                "failed_reads": result["failed"]
            },
            code=200
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        return Response(code=500, errors=[APIError(code=500, message=f"Error querying collection: {str(e)}")])


@FUNC.handler(method='GET', path='/search-categories')
def search_categories(request: Request, _: dict, logger: Logger) -> Response:
    """Search for categories in the domain collection."""
    logger.info("Starting /search-categories handler")
    try:
        custom_storage = get_client(CustomStorage)

        category = query_param(request, 'category').strip()
        if not category:
            return Response(code=400, errors=[APIError(code=400, message="Query parameter 'category' is required")])

        try:
            result = get_object(custom_storage, "domain", COLLECTION_DOMAIN_VER, category_key(category))
        except StorageError as e:
            return Response(code=500, errors=[APIError(code=500, message=f"Error fetching category: {e}")])
        if result is None:
            return Response(code=404, errors=[APIError(code=404, message=f"Category '{category}' not found")])

        logger.info(f"Successfully completed /search-categories for {category}")
        return Response(body=result, code=200)

    except Exception as e:
        logger.error(traceback.format_exc())
        return Response(code=500, errors=[APIError(code=500, message=f"Error searching collection: {str(e)}")])


@FUNC.handler(method='POST', path='/manage-category')
# pylint: disable-next=too-many-return-statements
def manage_category(request: Request, _: dict, logger: Logger) -> Response:
    """Create or update a category with comma-separated URLs."""
    logger.info("Starting /manage-category handler")
    try:
        if not request.body:
            return Response(code=400, body={"error": "Request body is required"})

        category_name = request.body.get('categoryName', '').strip()
        urls = request.body.get('urls', '').strip()

        if not category_name:
            return Response(code=400, body={"error": "Category name is required"})
        if not urls:
            return Response(code=400, body={"error": "URLs are required"})

        custom_storage = get_client(CustomStorage)
        url_list = _sanitize_url_list(urls, separator=',')
        if not url_list:
            return Response(code=400, body={"error": "No valid URLs provided"})

        key = category_key(category_name)
        conflict = next((k for k in _existing_keys(custom_storage) if k.lower() == key.lower() and k != key), None)
        if conflict:
            return Response(code=409, body={"error": f"A category with a similar name already exists: '{conflict}'"})

        record = {
            "category": category_name,
            "domain": ';'.join(url_list),
            "imported_at": int(time.time()),
            "last_modified": datetime.now(pytz.UTC).isoformat()
        }

        response = custom_storage.PutObjectByVersion(
            body=record,
            collection_name="domain",
            collection_version=COLLECTION_DOMAIN_VER,
            object_key=key
        )

        if response.get('status_code') == 200:
            logger.info(f"Successfully completed /manage-category: Created/Updated {category_name}")
            return Response(
                code=200,
                body={
                    "success": True,
                    "message": "Category processed successfully",
                    "operation": "create",
                    "categoryName": category_name,
                    "urlCount": len(url_list)
                }
            )

        return Response(code=500, body={
            "error": "Failed to process category",
            "details": response.get('body', {}).get('message', 'Unknown error'),
        })

    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Unexpected error occurred"})

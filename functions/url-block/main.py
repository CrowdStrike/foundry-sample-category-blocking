"""Foundry URL blocking function for managing domain categories and firewall rules."""

import os
import time
from datetime import datetime
from logging import Logger

import pytz
from crowdstrike.foundry.function import Function, Request, Response, APIError, cloud
from falconpy import APIHarnessV2, CustomStorage

from analytics_processor import generate_domain_analytics
from csv_processor import process_csv_records, read_categories_from_csv
from exceptions import (
    CSVProcessingError, AnalyticsError, FirewallAPIError,
    ValidationError, CategoryNotFoundError
)
from firewall_manager import get_host_groups, create_blocking_rule, update_rule_group_with_new_urls


FUNC = Function.instance()


@FUNC.handler(method='POST', path='/import-csv')
def import_csv_handler(_request: Request) -> Response:
    """Import domain categorization CSV data into a Foundry Collection."""
    try:
        # Initialize API client
        api_client = APIHarnessV2()
        customobjects = CustomStorage(api_client, base_url=cloud())

        # Get the directory where main.py is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_file = os.path.join(current_dir, 'output.csv')

        # Process CSV records
        results = process_csv_records(
            csv_path=csv_file,
            customobjects=customobjects,
            collection_name="domain",
            collection_version="v2.0"
        )

        return Response(
            body={
                "success": True,
                "total_rows": results["total_rows"],
                "successful_imports": results["success_count"],
                "failed_imports": results["error_count"],
                "collection_name": "domain",
                "source_file": csv_file,
                "import_timestamp": int(time.time())
            },
            code=200
        )

    except CSVProcessingError as e:
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"CSV processing failed: {str(e)}")]
        )
    except OSError as e:
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"File system error: {str(e)}")]
        )


@FUNC.handler(method='GET', path='/url-block')
def on_create(_request: Request, _config, logger: Logger) -> Response:
    """Handle host groups retrieval request."""
    logger.info("Starting host groups handler")
    try:
        host_groups_list = get_host_groups()
        logger.info(f"Successfully retrieved {len(host_groups_list)} host groups")
        return Response(
            code=200,
            body={"host_groups": host_groups_list}
        )

    except FirewallAPIError as e:
        logger.error(f"Firewall API error: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Failed to retrieve host groups",
                "details": str(e)
            }
        )
    except OSError as e:
        logger.error(f"System error: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "System error occurred",
                "details": str(e)
            }
        )


@FUNC.handler(method='GET', path='/categories')
def get_categories(_request: Request, _config, logger: Logger) -> Response:
    """Handle categories retrieval from CSV file."""
    logger.info("Starting categories handler")
    try:
        # Get the directory where main.py is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_file = os.path.join(current_dir, 'output.csv')

        logger.info(f"Looking for CSV file at: {csv_file}")

        categories_dict = read_categories_from_csv(csv_file)
        logger.info(f"Number of categories found: {len(categories_dict)}")
        logger.info(f"Categories: {list(categories_dict.keys())}")

        return Response(
            code=200,
            body={'categories': categories_dict}
        )

    except CSVProcessingError as e:
        logger.error(f"CSV processing error: {str(e)}")
        return Response(
            code=404 if "not found" in str(e) else 500,
            body={
                "error": "Failed to read CSV file",
                "details": str(e)
            }
        )
    except OSError as e:
        logger.error(f"File system error reading categories: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "File system error reading categories",
                "details": str(e)
            }
        )


def validate_create_rule_request(request):
    """Validate create rule request and return validation errors if any."""
    if not request.body:
        return {"error": "Request body is required"}
    host_group_id = request.body.get('hostGroupId')
    urls = request.body.get('urls', '').strip()
    policy_name = request.body.get('policyName', '').strip()
    if not host_group_id:
        return {"error": "hostGroupId is required"}
    if not urls:
        return {"error": "urls is required"}
    if not policy_name:
        return {"error": "policyName is required"}
    return {
        "host_group_id": host_group_id,
        "urls": urls,
        "policy_name": policy_name
    }


@FUNC.handler(method='POST', path='/create-rule')
def create_rule(request: Request, _config, logger: Logger) -> Response:
    """Create firewall rule for blocking URLs."""
    logger.info("Starting create rule handler")
    try:
        # Validate request
        validation_result = validate_create_rule_request(request)
        if "error" in validation_result:
            return Response(code=400, body=validation_result)
        host_group_id = validation_result["host_group_id"]
        urls = validation_result["urls"]
        policy_name = validation_result["policy_name"]

        # Log received data
        logger.info(f"Received request - hostGroupId: {host_group_id}")
        logger.info(f"Received URLs (raw): {urls}")
        logger.info(f"Policy name: {policy_name}")

        # Create the blocking rule
        result = create_blocking_rule(host_group_id, urls, policy_name)
        logger.info(f"Successfully created blocking rule for policy: {policy_name}")

        return Response(
            code=200,
            body={
                "message": "Successfully created blocking rule",
                "policyName": result["policy_name"],
                "ruleGroupId": result["rule_group_id"],
                "policyId": result["policy_id"]
            }
        )

    except (FirewallAPIError, ValidationError) as e:
        logger.error(f"Error creating rule: {str(e)}")
        return Response(
            code=500,
            body={"error": f"Failed to create rule: {str(e)}"}
        )
    except OSError as e:
        logger.error(f"System error creating rule: {str(e)}")
        return Response(
            code=500,
            body={"error": f"System error creating rule: {str(e)}"}
        )


@FUNC.handler(method='GET', path='/domain-analytics')
def get_domain_analytics(_request: Request, _config, logger: Logger) -> Response:
    """Generate analytics for domain blocking events."""
    logger.info("Starting domain analytics handler")
    try:
        analytics = generate_domain_analytics()
        logger.info("Analytics processing completed successfully")
        return Response(
            code=200,
            body=analytics
        )

    except (AnalyticsError, FirewallAPIError) as e:
        logger.error(f"Analytics error: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Failed to generate analytics",
                "details": str(e)
            }
        )
    except OSError as e:
        logger.error(f"System error in domain analytics: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "System error generating analytics",
                "details": str(e)
            }
        )


@FUNC.handler(method='GET', path='/list-categories')
def list_categories(request: Request) -> Response:
    """List all categories from the domain collection."""
    try:
        # Initialize API client
        api_client = APIHarnessV2()
        customobjects = CustomStorage(api_client, base_url=cloud())

        # Set headers if APP_ID is available
        headers = {}
        if os.environ.get("APP_ID"):
            headers = {"X-CS-APP-ID": os.environ.get("APP_ID")}

        # Get query parameters with defaults
        try:
            limit = int(getattr(request.params, 'limit', 1000))
        except (ValueError, AttributeError):
            limit = 1000

        # Query the collection using list method
        response = customobjects.ListObjectsByVersion(
            collection_name='domain',
            limit=limit,
            collection_version="v2.0",
            headers=headers
        )

        # More detailed error checking
        if not response:
            return Response(
                code=500,
                errors=[APIError(code=500, message="No response received from API")]
            )

        if "errors" in response:
            return Response(
                code=400,
                errors=[APIError(code=400, message=f"API Error: {response['errors']}")]
            )

        return Response(
            body=response,
            code=200
        )

    except (ValueError, AttributeError) as e:
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"Parameter error: {str(e)}")]
        )


@FUNC.handler(method='GET', path='/search-categories')
def search_categories(_request: Request) -> Response:
    """Search categories based on provided criteria."""
    try:
        # Initialize API client
        api_client = APIHarnessV2()

        # Set headers if APP_ID is available
        headers = {}
        if os.environ.get("APP_ID"):
            headers = {"X-CS-APP-ID": os.environ.get("APP_ID")}

        # Get search parameters from request body
        # Note: body variable is for future use if filtering is implemented

        # Query the collection using list method with filter
        response = api_client.command("GetObject",
            collection_name="domain",
            limit=1000,
            collection_version="v2.0",
            object_key="Games",
            headers=headers
        )

        return Response(
            body=response,
            code=200
        )

    except (ValueError, AttributeError) as e:
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"Parameter error searching collection: {str(e)}")]
        )


@FUNC.handler(method='POST', path='/manage-category')
def manage_category(request: Request, _config, logger: Logger) -> Response:
    """Create or update a category with comma-separated URLs"""
    logger.info("Starting manage category handler")
    try:
        # Validate request body
        if not request.body:
            return Response(code=400, body={"error": "Request body is required"})

        category_name = request.body.get('categoryName', '').strip()
        urls = request.body.get('urls', '').strip()

        logger.info(f"Processing category: {category_name}")

        if not category_name:
            return Response(code=400, body={"error": "Category name is required"})
        if not urls:
            return Response(code=400, body={"error": "URLs are required"})

        # Initialize API client
        api_client = APIHarnessV2(debug=True)
        customobjects = CustomStorage(api_client, base_url=cloud())

        # Process comma-separated URLs and add wildcards
        url_list = []
        for url in urls.split(','):
            url = url.strip()
            if url:
                url_list.append(url)
                if not url.startswith('*'):
                    url_list.append(f"*{url}")

        logger.info(f"Processed {len(url_list)} URLs for category {category_name}")

        # Create record
        record = {
            "category": category_name,
            "domain": ';'.join(url_list),  # Join URLs with semicolon for storage
            "imported_at": int(time.time()),
            "last_modified": datetime.now(pytz.UTC).isoformat()
        }

        # Create or update collection object
        response = customobjects.PutObject(
            body=record,
            collection_name="domain",
            collection_version="v2.0",
            object_key=category_name.replace(' ', '_'),
            limit=1000
        )

        if response.get('status_code') == 200:
            logger.info(f"Successfully processed category: {category_name}")
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

        logger.error(f"Failed to process category. API Response: {response}")
        return Response(
            code=500,
            body={
                "error": "Failed to process category",
                "details": response.get('body', {}).get('message', 'Unknown error')
            }
        )

    except (ValueError, OSError) as e:
        logger.error(f"Processing error: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Processing error occurred",
                "details": str(e)
            }
        )


@FUNC.handler(method='POST', path='/manage-relationship')
def manage_relationship(request: Request, _config, logger: Logger) -> Response:
    """Create or update relationship between category, rule group, and host"""
    logger.info("Starting relationship management")
    logger.info(f"Request body: {request.body}")

    try:
        # Initialize API client
        api_client = APIHarnessV2(debug=True)
        customobjects = CustomStorage(api_client, base_url=cloud())

        # Extract data directly from request body
        relationship_record = {
            "category_name": request.body.get('category_name', ''),
            "rule_group_id": request.body.get('rule_group_id', ''),
            "rule_group_name": request.body.get('rule_group_name', ''),
            "host_group_id": request.body.get('host_group_id', ''),
            "host_group_name": request.body.get('host_group_name', ''),
            "policy_name": request.body.get('policy_name', ''),
            "created_at": request.body.get('created_at', datetime.now(pytz.UTC).isoformat()),
            "created_by": request.body.get('created_by', 'unknown')
        }

        # Validate required fields according to schema
        required_fields = ['category_name', 'rule_group_id', 'host_group_id']
        missing_fields = [field for field in required_fields if not relationship_record[field]]

        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            return Response(
                code=400,
                body={
                    "error": "Missing required fields",
                    "missing_fields": missing_fields
                }
            )

        # Generate unique key
        relationship_key = (
            f"{relationship_record['category_name']}_"
            f"{relationship_record['rule_group_id']}_"
            f"{relationship_record['host_group_id']}"
        )

        logger.info(f"Creating relationship with key: {relationship_key}")

        # Store in collection
        response = customobjects.PutObject(
            body=relationship_record,
            collection_name="relationship",
            collection_version="v5.0",
            object_key=relationship_key
        )

        if response.get('status_code') == 200:
            logger.info(f"Successfully created relationship: {relationship_key}")
            return Response(
                code=200,
                body={
                    "success": True,
                    "message": "Relationship created successfully",
                    "relationshipId": relationship_key,
                    "details": relationship_record
                }
            )

        error_msg = f"Failed to create relationship. Status: {response.get('status_code')}"
        logger.error(error_msg)
        return Response(
            code=500,
            body={
                "error": "Failed to create relationship",
                "details": error_msg
            }
        )

    except (ValueError, OSError) as e:
        logger.error(f"Processing error: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Processing error occurred",
                "details": str(e)
            }
        )


@FUNC.handler(method='GET', path='/get-relationship')
def get_relationship(_request: Request, _config, logger: Logger) -> Response:
    """Get all relationship and format for graph visualization"""
    try:
        api_client = APIHarnessV2(debug=True)
        customobjects = CustomStorage(api_client, base_url=cloud())

        response = customobjects.ListObjectsByVersion(
            collection_name="relationship",
            collection_version="v5.0",
            limit=1000
        )

        if response.get('status_code') != 200:
            raise CategoryNotFoundError("Failed to fetch relationship")

        relationships = response.get('resources', [])

        # Transform data for graph visualization
        nodes = []
        links = []
        nodes_set = set()

        for rel in relationships:
            # Add category node
            if rel['category_name'] not in nodes_set:
                nodes_set.add(rel['category_name'])
                nodes.append({
                    "id": rel['category_name'],
                    "name": rel['category_name'],
                    "type": "category"
                })

            # Add rule group node
            if rel['rule_group_id'] not in nodes_set:
                nodes_set.add(rel['rule_group_id'])
                nodes.append({
                    "id": rel['rule_group_id'],
                    "name": rel['rule_group_name'],
                    "type": "rule_group"
                })

            # Add host group node
            if rel['host_group_id'] not in nodes_set:
                nodes_set.add(rel['host_group_id'])
                nodes.append({
                    "id": rel['host_group_id'],
                    "name": rel['host_group_name'],
                    "type": "host_group"
                })

            # Add links
            links.append({
                "source": rel['category_name'],
                "target": rel['rule_group_id']
            })
            links.append({
                "source": rel['rule_group_id'],
                "target": rel['host_group_id']
            })

        return Response(
            code=200,
            body={
                "success": True,
                "relationship": relationships,
                "graphData": {
                    "nodes": nodes,
                    "links": links
                }
            }
        )

    except CategoryNotFoundError as e:
        logger.error(f"Error fetching relationship: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Failed to fetch relationship",
                "details": str(e)
            }
        )
    except (ValueError, OSError) as e:
        logger.error(f"Processing error fetching relationship: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Processing error fetching relationship",
                "details": str(e)
            }
        )


@FUNC.handler(method='POST', path='/update-rules')
def update_rules(request: Request, _config, logger: Logger) -> Response:
    """Update rules in rule groups with only newly added URLs"""
    logger.info("Starting rule update handler")
    try:
        # Validate request
        if not request.body:
            return Response(code=400, body={"error": "Request body is required"})

        category_name = request.body.get('category_name')
        new_urls = request.body.get('new_urls')
        relationships = request.body.get('relationships', [])

        logger.info(f"Updating rules for category: {category_name}")
        logger.info(f"New URLs to add: {new_urls}")

        if not category_name or not new_urls or not relationships:
            return Response(code=400, body={
                "error": "Missing required fields",
                "required": ["category_name", "new_urls", "relationships"]
            })

        # Update rules for each relationship
        update_results = []
        for relationship in relationships:
            try:
                rule_group_id = relationship['rule_group_id']
                logger.info(f"Updating rule group: {rule_group_id}")

                result = update_rule_group_with_new_urls(
                    rule_group_id, category_name, new_urls
                )
                result["rule_group_name"] = relationship['rule_group_name']
                update_results.append(result)

                logger.info(f"Rule group update successful for {rule_group_id}")

            except (ValueError, OSError) as rule_error:
                logger.error(f"Error updating rule group {rule_group_id}: {str(rule_error)}")
                update_results.append({
                    "rule_group_id": rule_group_id,
                    "rule_group_name": relationship['rule_group_name'],
                    "status": "failed",
                    "error": str(rule_error)
                })

        # Return results
        success_count = len([r for r in update_results if r['status'] == 'success'])
        return Response(
            code=200,
            body={
                "success": True,
                "message": f"Updated {success_count} of {len(update_results)} rule groups",
                "category": category_name,
                "new_urls_added": new_urls,
                "results": update_results
            }
        )

    except (ValueError, OSError) as e:
        logger.error(f"Error in update_rules: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Failed to update rules",
                "details": str(e)
            }
        )


@FUNC.handler(method='GET', path='/healthz')
def healthz(_request, _config):
    """Health check endpoint."""
    return Response(code=200)


if __name__ == '__main__':
    FUNC.run()

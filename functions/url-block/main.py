"""Foundry URL blocking function for managing domain categories and firewall rules."""

# Standard library imports
import csv
import os
import time
import traceback
from datetime import datetime, timedelta
from logging import Logger

# Third-party imports
import pytz
from crowdstrike.foundry.function import Function, Request, Response, APIError, cloud
from falconpy import APIHarnessV2, HostGroup, FirewallManagement, FirewallPolicies, CustomStorage


FUNC = Function.instance()

def transform_csv_row(row):
    """Transform a CSV row to match the Collection schema."""
    category = row[0].strip()
    urls = row[1]

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
        raise ValueError("Missing required field: category")
    if not record.get('domain'):
        raise ValueError("Missing required field: domain")

def process_csv_records(csv_path, customobjects, collection_name="domain", collection_version="v2.0"):
    """Process CSV records and create collection objects."""
    success_count = 0
    error_count = 0
    total_rows = 0

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
                        response = customobjects.PutObject(
                            body=record,
                            collection_name=collection_name,
                            collection_version=collection_version,
                            object_key=record['category'],
                            limit=1000
                        )

                        success_count += 1

                except Exception as e:
                    error_count += 1
                    print(f"Error processing row {total_rows}: {str(e)}")
                    continue

    except Exception as e:
        raise Exception(f"Error reading CSV file: {str(e)}")

    return {
        "total_rows": total_rows,
        "success_count": success_count,
        "error_count": error_count
    }

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

    except Exception as e:
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"CSV import failed: {str(e)}")]
        )

@FUNC.handler(method='GET', path='/url-block')
def on_create(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
    logger.info("Starting host groups handler")
    try:
        # Initialize Falcon client
        try:
            falcon = APIHarnessV2(debug=True)
            hostgroup = HostGroup(falcon, base_url=cloud())
            logger.info("Successfully initialized Falcon client")
        except Exception as e:
            logger.error(f"Failed to initialize Falcon client: {str(e)}")
            return Response(
                code=500,
                body={
                    "error": "Falcon client initialization failed",
                    "details": str(e)
                }
            )

        # Query host groups
        try:
            response = hostgroup.query_host_groups()
            logger.info(f"Query response status: {response.get('status_code')}")

            if response["status_code"] == 200:
                groups = response["body"]["resources"]
                groups_details = hostgroup.get_host_groups(ids=groups)

                # Format host groups data
                host_groups_list = []
                for group in groups_details["body"]["resources"]:
                    host_groups_list.append({
                        "id": group["id"],
                        "name": group["name"]
                    })

                logger.info(f"Successfully retrieved {len(host_groups_list)} host groups")
                return Response(
                    code=200,
                    body={"host_groups": host_groups_list}
                )
            else:
                error_msg = f"Failed to retrieve host groups. Status: {response['status_code']}"
                logger.error(error_msg)
                return Response(
                    code=response["status_code"],
                    body={"error": error_msg}
                )

        except Exception as e:
            logger.error(f"Error querying host groups: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                code=500,
                body={
                    "error": "Failed to query host groups",
                    "details": str(e),
                    "traceback": traceback.format_exc()
                }
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            code=500,
            body={
                "error": "Unexpected error occurred",
                "details": str(e),
                "traceback": traceback.format_exc()
            }
        )

@FUNC.handler(method='GET', path='/categories')
def get_categories(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
    logger.info("Starting categories handler")
    try:
        # Get the directory where main.py is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_file = os.path.join(current_dir, 'output.csv')

        logger.info(f"Looking for CSV file at: {csv_file}")

        # Check if file exists
        if not os.path.exists(csv_file):
            logger.error(f"CSV file not found at: {csv_file}")
            return Response(
                code=404,
                body={
                    "error": "CSV file not found",
                    "path": csv_file
                }
            )

        try:
            categories_dict = {}
            with open(csv_file, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f)
                headers = next(csv_reader)  # Skip header row
                logger.info(f"CSV headers: {headers}")

                for row in csv_reader:
                    if len(row) >= 2:  # Ensure row has at least 2 columns
                        category = row[0].strip()
                        urls = row[1].strip()

                        # Clean and format URLs
                        url_list = [url.strip() for url in urls.split(';') if url.strip()]
                        if url_list:  # Only add if there are valid URLs
                            clean_urls = ';'.join(url_list)
                            categories_dict[category] = clean_urls

            logger.info(f"Number of categories found: {len(categories_dict)}")
            logger.info(f"Categories: {list(categories_dict.keys())}")

            return Response(
                code=200,
                body={
                    'categories': categories_dict
                }
            )

        except Exception as csv_error:
            logger.error(f"Error reading CSV file: {str(csv_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                code=500,
                body={
                    "error": "Failed to read CSV file",
                    "details": str(csv_error)
                }
            )

    except Exception as e:
        logger.error(f"Error reading categories: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            code=500,
            body={
                "error": "Failed to read categories",
                "details": str(e)
            }
        )

@FUNC.handler(method='POST', path='/create-rule')
def create_rule(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
    logger.info("Starting create rule handler")
    try:
        # Validate request body
        if not request.body:
            return Response(
                code=400,
                body={"error": "Request body is required"}
            )

        # Get and validate inputs
        host_group_id = request.body.get('hostGroupId')
        urls = request.body.get('urls', '').strip()
        policy_name = request.body.get('policyName', '').strip()

        # Log received data
        logger.info(f"Received request - hostGroupId: {host_group_id}")
        logger.info(f"Received URLs (raw): {urls}")
        logger.info(f"Policy name: {policy_name}")

        # Validate required fields
        if not host_group_id:
            return Response(code=400, body={"error": "hostGroupId is required"})
        if not urls:
            return Response(code=400, body={"error": "urls is required"})
        if not policy_name:
            return Response(code=400, body={"error": "policyName is required"})

        # Clean URLs
        url_list = [url.strip() for url in urls.split(';') if url.strip()]
        if not url_list:
            return Response(code=400, body={"error": "No valid URLs provided"})

        clean_urls = ';'.join(url_list)
        logger.info(f"Cleaned URLs: {clean_urls}")

        # Initialize Falcon client
        falcon = APIHarnessV2(debug=True)
        mgmt = FirewallManagement(falcon, base_url=cloud())
        policies = FirewallPolicies(falcon, base_url=cloud())
        logger.info("Successfully initialized Falcon client")

        # Create policy
        policy_response = policies.create_policies(
            description=f"Firewall policy for {policy_name}",
            name=policy_name,
            platform_name="Windows"
        )

        logger.info(f"Policy creation response: {policy_response}")

        if "body" not in policy_response or "resources" not in policy_response["body"]:
            raise Exception("Invalid policy creation response")

        policy_id = policy_response["body"]["resources"][0]["id"]
        logger.info(f"Created policy: {policy_id}")

        # Enable policy and add host group
        enable_response = policies.perform_action(action_name="enable", ids=policy_id)
        logger.info(f"Policy enable response: {enable_response}")

        add_host_response = policies.perform_action(
            action_name="add-host-group",
            group_id=host_group_id,
            ids=policy_id
        )
        logger.info(f"Add host group response: {add_host_response}")

        # Create rule group
        rule_group_response = mgmt.create_rule_group(
            description=f"Domain blocking rule group for {policy_name}",
            enabled=True,
            name=f"{policy_name}_RuleGroup",
            platform="windows",
            rules={
                "action": "DENY",
                "address_family": "NONE",
                "description": f"Domain blocking rule for {policy_name}",
                "direction": "OUT",
                "enabled": True,
                "fields": [
                    {
                        "name": "image_name",
                        "value": "",
                        "type": "windows_path",
                        "values": []
                    }
                ],
                "fqdn_enabled": True,
                "fqdn": urls,  # Use cleaned URLs
                "icmp": {"icmp_code": "", "icmp_type": ""},
                "local_address": [{"address": "*", "netmask": 0}],
                "log": False,
                "monitor": {"count": "1", "period_ms": "1000000"},
                "name": "rule1",
                "protocol": "*",
                "remote_address": [{"address": "*", "netmask": 0}],
                "temp_id": "1"
            }
        )

        logger.info(f"Rule group creation response: {rule_group_response}")

        if "body" not in rule_group_response or "resources" not in rule_group_response["body"]:
            raise Exception("Invalid rule group creation response")

        rule_group_id = rule_group_response["body"]["resources"][0]
        logger.info(f"Created rule group: {rule_group_id}")

        # Update policy with rule group
        update_response = mgmt.update_policy_container(
            body={
                "default_inbound": "ALLOW",
                "default_outbound": "ALLOW",
                "platform_id": "windows",
                "enforce": True,
                "local_logging": True,
                "is_default_policy": False,
                "test_mode": False,
                "rule_group_ids": rule_group_id,
                "policy_id": policy_id
            }
        )

        logger.info(f"Policy update response: {update_response}")

        return Response(
            code=200,
            body={
                "message": "Successfully created blocking rule",
                "policyName": policy_name,
                "ruleGroupId": rule_group_id,
                "policyId": policy_id
            }
        )

    except Exception as e:
        logger.error(f"Error creating rule: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            code=500,
            body={
                "error": f"Failed to create rule: {str(e)}"
            }
        )


@FUNC.handler(method='GET', path='/domain-analytics')
def get_domain_analytics(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
    logger.info("Starting domain analytics handler")
    try:
        # Initialize Falcon client
        try:
            falcon = APIHarnessV2(debug=True)
            firewall_mgmt = FirewallManagement(falcon, base_url=cloud())
            logger.info("Successfully initialized Falcon client")
        except Exception as e:
            logger.error(f"Failed to initialize Falcon client: {str(e)}")
            return Response(
                code=500,
                body={
                    "error": "Falcon client initialization failed",
                    "details": str(e)
                }
            )

        # Fetch events for the last 15 days
        end_time = datetime.now(pytz.UTC)
        start_time = end_time - timedelta(days=15)
        time_filter = f"timestamp:>'{start_time.isoformat()}'"

        logger.info(f"Fetching events from {start_time} to {end_time}")

        all_events = []
        offset = 0
        limit = 500

        while True:
            try:
                query_response = firewall_mgmt.query_events(parameters={
                    'filter': time_filter,
                    'limit': limit,
                    'offset': offset,
                    'sort': 'timestamp.desc'
                })

                if query_response['status_code'] != 200 or not query_response['body']['resources']:
                    break

                event_ids = query_response['body']['resources']
                events_response = firewall_mgmt.get_events(ids=event_ids)

                if events_response['status_code'] == 200:
                    events = events_response['body']['resources']
                    for event in events:
                        if 'domain_name_list' in event:
                            all_events.append({
                                'domain': event['domain_name_list'],
                                'timestamp': event['timestamp'],
                                'remote_address': event['remote_address'],
                                'host_name': event.get('host_name', 'Unknown'),
                                'policy_name': event.get('policy_name', 'Unknown'),
                                'rule_name': event.get('rule_name', 'Unknown')
                            })

                offset += limit
                if len(event_ids) < limit:
                    break

            except Exception as e:
                logger.error(f"Error fetching events batch: {str(e)}")
                break

        logger.info(f"Total events fetched: {len(all_events)}")

        # Analyze domains
        from collections import Counter, defaultdict

        # Count domain occurrences
        domain_counter = Counter(event['domain'] for event in all_events)
        top_domains = domain_counter.most_common(20)  # Get top 20 domains

        # Initialize analysis data
        domain_analysis = {}
        daily_blocks = defaultdict(int)
        total_blocks = 0
        unique_hosts = set()

        # Analyze each domain
        for domain, count in top_domains:
            domain_events = [e for e in all_events if e['domain'] == domain]
            unique_ips = len(set(e['remote_address'] for e in domain_events))
            domain_hosts = len(set(e['host_name'] for e in domain_events))

            # Get timestamps for first and last blocks
            timestamps = [datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))
                        for e in domain_events]

            domain_analysis[domain] = {
                'visit_count': count,  # Changed from block_count to visit_count to match React component
                'unique_ips': unique_ips,
                'unique_hosts': domain_hosts,
                'first_seen': min(timestamps).isoformat(),
                'last_seen': max(timestamps).isoformat(),
                'policy_name': domain_events[0].get('policy_name', 'Unknown'),
                'rule_name': domain_events[0].get('rule_name', 'Unknown')
            }

            # Update totals
            total_blocks += count
            unique_hosts.update(e['host_name'] for e in domain_events)

            # Group by date for timeline
            for timestamp in timestamps:
                date_str = timestamp.date().isoformat()
                daily_blocks[date_str] += 1

        # Prepare visualization data to match what the React component expects
        visualization_data = {
            'bar_chart': {
                'domains': [domain for domain, _ in top_domains],
                'visits': [count for _, count in top_domains]  # Changed from 'counts' to 'visits'
            },
            'comparison_chart': {  # Changed from 'timeline' to 'comparison_chart'
                'domains': [domain for domain, _ in top_domains[:10]],
                'visits': [count for _, count in top_domains[:10]],
                'unique_ips': [domain_analysis[domain]['unique_ips'] for domain, _ in top_domains[:10]]
            },
            'summary': {
                'total_blocks': total_blocks,
                'unique_domains': len(domain_analysis),
                'unique_hosts': len(unique_hosts)
            }
        }

        logger.info("Analytics processing completed successfully")
        logger.info(f"Returning data structure: {visualization_data.keys()}")

        return Response(
            code=200,
            body={
                'analysis': domain_analysis,
                'visualization_data': visualization_data
            }
        )

    except Exception as e:
        logger.error(f"Error in domain analytics: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            code=500,
            body={
                "error": "Failed to generate analytics",
                "details": str(e),
                "traceback": traceback.format_exc()
            }
        )



@FUNC.handler(method='GET', path='/list-categories')
def list_categories(request: Request) -> Response:
    try:
        # Initialize API client
        api_client = APIHarnessV2()
        customobjects= CustomStorage(api_client, base_url=cloud())

        # Set headers if APP_ID is available
        headers = {}
        if os.environ.get("APP_ID"):
            headers = {"X-CS-APP-ID": os.environ.get("APP_ID")}

        # Get query parameters with defaults
        # Get query parameters with defaults
        try:
            limit = int(request.params.limit if hasattr(request.params, 'limit') else 1000)
        except (ValueError, AttributeError):
            limit = 1000

        print(f"Query params - limit: {limit}")  # Debug logging
        body_test={
    "category": "phishing",
    "domain": "example.com",
    "wildcard_domain": "*.example.com",
    "imported_at": 1687716282}

        # Query the collection using list method
        # response = customobjects.PutObject(
        #     body=body_test,
        #     collection_name="domain",
        #     collection_version="v2.0",
        #     object_key="Games",
        #     limit=limit
        # )
        response = customobjects.ListObjectsByVersion(collection_name='domain',limit=1000,collection_version="v2.0")

        print("Raw API Response:", response)  # Debug logging

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

        # Extract resources from response
        resources = response.get('resources', [])
        print(f"Found {len(resources)} resources")  # Debug logging

        # Extract unique categories
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
            except Exception as e:
                print(f"Error processing item: {e}")
                continue

        # Prepare response data
        response_data = {
            "total_items": len(resources),
            "unique_categories": len(categories),
            "categories": sorted(list(categories)),
            "domains": domains,
            "metadata": {
                "limit": limit,
                "timestamp": int(time.time())
            }
        }

        print(f"Processed response data: {response_data}")  # Debug logging

        return Response(
            body=response,
            code=200
        )

    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Debug logging
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"Error querying collection: {str(e)}")]
        )


@FUNC.handler(method='GET', path='/search-categories')
def search_categories(request: Request) -> Response:
    try:
        # Initialize API client
        api_client = APIHarnessV2()
        customobjects= CustomStorage(api_client, base_url=cloud())

        # Set headers if APP_ID is available
        headers = {}
        if os.environ.get("APP_ID"):
            headers = {"X-CS-APP-ID": os.environ.get("APP_ID")}

        # Get search parameters from request body
        body = request.body or {}
        limit = int(body.get('limit', 1000))
        category = body.get('category', '')

        print(f"Search params - category: {category}, limit: {limit}")  # Debug logging

        # Query the collection using list method with filter
        response = api_client.command("GetObject",
            collection_name="domain",
            limit=1000,
            collection_version="v2.0",
            object_key="Games",
            headers=headers
        )

        print("Raw Search Response:", response)  # Debug logging


        return Response(
            body=response,
            code=200
        )

    except Exception as e:
        print(f"Search error occurred: {str(e)}")  # Debug logging
        return Response(
            code=500,
            errors=[APIError(code=500, message=f"Error searching collection: {str(e)}")]
        )


@FUNC.handler(method='POST', path='/manage-category')
def manage_category(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
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
        try:
            response = customobjects.PutObject(
                body=record,
                collection_name="domain",
                collection_version="v2.0",
                object_key=category_name.replace(' ', '_'), ##removed .lower()
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
            else:
                logger.error(f"Failed to process category. API Response: {response}")
                return Response(
                    code=500,
                    body={
                        "error": "Failed to process category",
                        "details": response.get('body', {}).get('message', 'Unknown error')
                    }
                )

        except Exception as api_error:
            logger.error(f"API error: {str(api_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                code=500,
                body={
                    "error": "Failed to process category",
                    "details": str(api_error)
                }
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            code=500,
            body={
                "error": "Unexpected error occurred",
                "details": str(e)
            }
        )

@FUNC.handler(method='POST', path='/manage-relationship')
def manage_relationship(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
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
        logger.info(f"Relationship record: {relationship_record}")

        # Store in collection
        try:
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
            else:
                error_msg = f"Failed to create relationship. Status: {response.get('status_code')}"
                logger.error(error_msg)
                return Response(
                    code=500,
                    body={
                        "error": "Failed to create relationship",
                        "details": error_msg
                    }
                )

        except Exception as api_error:
            logger.error(f"API error: {str(api_error)}")
            return Response(
                code=500,
                body={
                    "error": "Failed to create relationship",
                    "details": str(api_error)
                }
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Unexpected error occurred",
                "details": str(e)
            }
        )

@FUNC.handler(method='GET', path='/get-relationship')
def get_relationship(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
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
            raise Exception("Failed to fetch relationship")

        relationship = response.get('resources', [])

        # Transform data for graph visualization
        nodes = []
        links = []
        nodes_set = set()

        for rel in relationship:
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
                "relationship": relationship,
                "graphData": {
                    "nodes": nodes,
                    "links": links
                }
            }
        )

    except Exception as e:
        logger.error(f"Error fetching relationship: {str(e)}")
        return Response(
            code=500,
            body={
                "error": "Failed to fetch relationship",
                "details": str(e)
            }
        )

#Updates rules

@FUNC.handler(method='POST', path='/update-rules')
def update_rules(request: Request, config: [dict[str, any], None], logger: Logger) -> Response:
    """Update rules in rule groups with only newly added URLs"""
    logger.info("Starting rule update handler")
    try:
        # Validate request
        if not request.body:
            return Response(code=400, body={"error": "Request body is required"})

        category_name = request.body.get('category_name')
        new_urls = request.body.get('new_urls')  # Changed from urls to new_urls
        relationships = request.body.get('relationships', [])

        logger.info(f"Updating rules for category: {category_name}")
        logger.info(f"New URLs to add: {new_urls}")
        logger.info(f"Relationships data: {relationships}")

        if not category_name or not new_urls or not relationships:
            return Response(code=400, body={
                "error": "Missing required fields",
                "required": ["category_name", "new_urls", "relationships"]
            })

        # Initialize Falcon client
        api_client = APIHarnessV2(debug=True)
        firewall_mgmt = FirewallManagement(api_client, base_url=cloud())

        # Update rules for each relationship
        update_results = []
        for relationship in relationships:
            try:
                rule_group_id = relationship['rule_group_id']
                logger.info(f"Updating rule group: {rule_group_id}")

                # Get current group details
                group_response = firewall_mgmt.get_rule_groups(ids=[rule_group_id])
                if group_response["status_code"] != 200:
                    raise Exception("Error getting group details")

                group_details = group_response["body"]["resources"][0]
                tracking_number = group_details["tracking"]
                current_rule_ids = group_details.get("rule_ids", []) or []

                # Create new rule with only the new URLs
                new_rule = {
                    "action": "DENY",
                    "address_family": "NONE",
                    "description": f"Domain blocking rule for {category_name} (Added: {datetime.now().isoformat()})",
                    "direction": "OUT",
                    "enabled": True,
                    "fields": [
                        {
                            "name": "image_name",
                            "value": "",
                            "type": "windows_path",
                            "values": []
                        }
                    ],
                    "fqdn_enabled": True,
                    "fqdn": new_urls,  # Only the new URLs
                    "icmp": {"icmp_code": "", "icmp_type": ""},
                    "local_address": [{"address": "*", "netmask": 0}],
                    "log": False,
                    "monitor": {"count": "1", "period_ms": "1000000"},
                    "name": f"{category_name}_rule_{int(time.time())}",
                    "protocol": "*",
                    "remote_address": [{"address": "*", "netmask": 0}],
                    "temp_id": str(int(time.time()))
                }

                # Prepare diff operation to add new rule
                diff_operation = [{
                    "value": new_rule,
                    "op": "add",
                    "path": f"/rules/{len(current_rule_ids)}"
                }]

                # Update rule group
                update_response = firewall_mgmt.update_rule_group(
                    id=rule_group_id,
                    diff_type="application/json-patch+json",
                    diff_operations=diff_operation,
                    rule_ids=current_rule_ids + [new_rule["temp_id"]],
                    rule_versions=[1] * (len(current_rule_ids) + 1),
                    comment=f"Adding new domains for {category_name}",
                    tracking=tracking_number
                )

                success = update_response["status_code"] == 200
                update_results.append({
                    "rule_group_id": rule_group_id,
                    "rule_group_name": relationship['rule_group_name'],
                    "status": "success" if success else "failed",
                    "details": {
                        "added_urls": new_urls,
                        "response": update_response.get("body", {})
                    }
                })

                logger.info(f"Rule group update {'successful' if success else 'failed'} for {rule_group_id}")

            except Exception as rule_error:
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

    except Exception as e:
        logger.error(f"Error in update_rules: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            code=500,
            body={
                "error": "Failed to update rules",
                "details": str(e)
            }
        )



@FUNC.handler(method='GET', path='/healthz')
def healthz(request, config):
    return Response(code=200)

if __name__ == '__main__':
    FUNC.run()

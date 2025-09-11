"""Firewall management utilities for URL filtering."""

import time
from datetime import datetime

from crowdstrike.foundry.function import cloud
from falconpy import APIHarnessV2, HostGroup, FirewallManagement, FirewallPolicies

from exceptions import FirewallAPIError, PolicyError, RuleGroupError


def initialize_falcon_client(debug=True):
    """Initialize Falcon API client with error handling."""
    try:
        falcon = APIHarnessV2(debug=debug)
        return falcon
    except Exception as e:
        raise FirewallAPIError(f"Failed to initialize Falcon client: {str(e)}") from e


def get_host_groups():
    """Retrieve host groups from CrowdStrike Falcon."""
    try:
        falcon = initialize_falcon_client()
        hostgroup = HostGroup(falcon, base_url=cloud())
        
        response = hostgroup.query_host_groups()
        
        if response["status_code"] != 200:
            raise FirewallAPIError(f"Failed to query host groups. Status: {response['status_code']}")
        
        groups = response["body"]["resources"]
        groups_details = hostgroup.get_host_groups(ids=groups)
        
        if groups_details["status_code"] != 200:
            raise FirewallAPIError(f"Failed to get host group details. Status: {groups_details['status_code']}")
        
        # Format host groups data
        host_groups_list = []
        for group in groups_details["body"]["resources"]:
            host_groups_list.append({
                "id": group["id"],
                "name": group["name"]
            })
        
        return host_groups_list
        
    except FirewallAPIError:
        raise
    except Exception as e:
        raise FirewallAPIError(f"Error retrieving host groups: {str(e)}") from e


def create_firewall_policy(policy_name, description=None):
    """Create a new firewall policy."""
    try:
        falcon = initialize_falcon_client()
        policies = FirewallPolicies(falcon, base_url=cloud())
        
        if description is None:
            description = f"Firewall policy for {policy_name}"
        
        policy_response = policies.create_policies(
            description=description,
            name=policy_name,
            platform_name="Windows"
        )
        
        if "body" not in policy_response or "resources" not in policy_response["body"]:
            raise PolicyError("Invalid policy creation response")
        
        policy_id = policy_response["body"]["resources"][0]["id"]
        return policy_id
        
    except PolicyError:
        raise
    except Exception as e:
        raise PolicyError(f"Failed to create policy: {str(e)}") from e


def enable_policy_and_add_host_group(policy_id, host_group_id):
    """Enable policy and add host group to it."""
    try:
        falcon = initialize_falcon_client()
        policies = FirewallPolicies(falcon, base_url=cloud())
        
        # Enable policy
        enable_response = policies.perform_action(action_name="enable", ids=policy_id)
        if enable_response.get("status_code") != 200:
            raise PolicyError(f"Failed to enable policy {policy_id}")
        
        # Add host group
        add_host_response = policies.perform_action(
            action_name="add-host-group",
            group_id=host_group_id,
            ids=policy_id
        )
        if add_host_response.get("status_code") != 200:
            raise PolicyError(f"Failed to add host group to policy {policy_id}")
        
        return True
        
    except PolicyError:
        raise
    except Exception as e:
        raise PolicyError(f"Failed to configure policy: {str(e)}") from e


def create_rule_group(policy_name, urls):
    """Create a rule group for domain blocking."""
    try:
        falcon = initialize_falcon_client()
        mgmt = FirewallManagement(falcon, base_url=cloud())
        
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
                "fqdn": urls,
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
        
        if "body" not in rule_group_response or "resources" not in rule_group_response["body"]:
            raise RuleGroupError("Invalid rule group creation response")
        
        rule_group_id = rule_group_response["body"]["resources"][0]
        return rule_group_id
        
    except RuleGroupError:
        raise
    except Exception as e:
        raise RuleGroupError(f"Failed to create rule group: {str(e)}") from e


def update_policy_with_rule_group(policy_id, rule_group_id):
    """Update policy container with rule group."""
    try:
        falcon = initialize_falcon_client()
        mgmt = FirewallManagement(falcon, base_url=cloud())
        
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
        
        if update_response.get("status_code") != 200:
            raise PolicyError(f"Failed to update policy container: {update_response}")
        
        return True
        
    except PolicyError:
        raise
    except Exception as e:
        raise PolicyError(f"Failed to update policy container: {str(e)}") from e


def create_blocking_rule(host_group_id, urls, policy_name):
    """Create complete firewall blocking rule for URLs."""
    try:
        # Clean URLs
        url_list = [url.strip() for url in urls.split(';') if url.strip()]
        if not url_list:
            raise RuleGroupError("No valid URLs provided")
        
        clean_urls = ';'.join(url_list)
        
        # Create policy
        policy_id = create_firewall_policy(policy_name)
        
        # Enable policy and add host group
        enable_policy_and_add_host_group(policy_id, host_group_id)
        
        # Create rule group
        rule_group_id = create_rule_group(policy_name, clean_urls)
        
        # Update policy with rule group
        update_policy_with_rule_group(policy_id, rule_group_id)
        
        return {
            "policy_id": policy_id,
            "rule_group_id": rule_group_id,
            "policy_name": policy_name
        }
        
    except (PolicyError, RuleGroupError):
        raise
    except Exception as e:
        raise FirewallAPIError(f"Failed to create blocking rule: {str(e)}") from e


def get_rule_group_details(rule_group_id):
    """Get details of a specific rule group."""
    try:
        falcon = initialize_falcon_client()
        firewall_mgmt = FirewallManagement(falcon, base_url=cloud())
        
        group_response = firewall_mgmt.get_rule_groups(ids=[rule_group_id])
        if group_response["status_code"] != 200:
            raise RuleGroupError(f"Error getting rule group details: {group_response}")
        
        return group_response["body"]["resources"][0]
        
    except RuleGroupError:
        raise
    except Exception as e:
        raise RuleGroupError(f"Failed to get rule group details: {str(e)}") from e


def update_rule_group_with_new_urls(rule_group_id, category_name, new_urls):
    """Update rule group with new URLs by adding a new rule."""
    try:
        falcon = initialize_falcon_client()
        firewall_mgmt = FirewallManagement(falcon, base_url=cloud())
        
        # Get current group details
        group_details = get_rule_group_details(rule_group_id)
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
            "fqdn": new_urls,
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
        
        if update_response["status_code"] != 200:
            raise RuleGroupError(f"Failed to update rule group: {update_response}")
        
        return {
            "rule_group_id": rule_group_id,
            "status": "success",
            "added_urls": new_urls,
            "response": update_response.get("body", {})
        }
        
    except RuleGroupError:
        raise
    except Exception as e:
        raise RuleGroupError(f"Failed to update rule group: {str(e)}") from e

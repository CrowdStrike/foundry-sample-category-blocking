"""Handlers for creating, updating, deleting, listing and simulating firewall policies."""

# Handlers deliberately catch every exception to log it and return a 500 response.
# pylint: disable=broad-exception-caught

import re
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging import Logger

import pytz
from crowdstrike.foundry.function import Request, Response
from falconpy import FirewallManagement, FirewallPolicies, CustomStorage, HostGroup

from app_core import FUNC, get_client, COLLECTION_DOMAIN_VER, COLLECTION_RELATION_VER
from app_utils import (
    _sanitize_url_list, _build_rule, read_all_objects, delete_object, query_param,
    relationship_key, validate_fqdn, _validate_falcon_response, resolve_creator,
)

PLATFORM_NAMES = {'windows': 'Windows', 'mac': 'Mac', 'linux': 'Linux'}


@FUNC.handler(method='GET', path='/urlblock')
def on_create(_: Request, __: dict, logger: Logger) -> Response:
    """Handle requests to retrieve host groups."""
    logger.info("Starting host groups handler")
    try:
        hostgroup = get_client(HostGroup)
        response = hostgroup.query_host_groups()
        ok, err = _validate_falcon_response(response, "query_host_groups", logger)
        if not ok:
            return Response(code=response.get("status_code", 500), body={"error": f"Failed to retrieve host groups: {err}"})

        groups = response["body"]["resources"]
        groups_details = hostgroup.get_host_groups(ids=groups)
        ok, err = _validate_falcon_response(groups_details, "get_host_groups", logger)
        if not ok:
            return Response(code=groups_details.get("status_code", 500),
                            body={"error": f"Failed to retrieve host groups: {err}"})

        host_groups_list = [
            {"id": group["id"], "name": group["name"]}
            for group in groups_details["body"]["resources"]
        ]
        return Response(code=200, body={"host_groups": host_groups_list})
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Unexpected error occurred"})


# pylint: disable-next=too-many-arguments,too-many-locals
def _write_relationships(categories_list, rule_group_id, host_group_id, host_group_name,
                         policy_name, platform, whitelist, username, policy_id,
                         custom_storage, logger=None, created_by_source=None, rule_group_name=None):
    """Write relationships to custom storage in parallel. Returns success/error counts."""
    def _write_single(cat):
        record = {
            "category_name": cat,
            "rule_group_id": rule_group_id,
            "rule_group_name": rule_group_name or f"{policy_name}_RuleGroup",
            "host_group_id": host_group_id,
            "host_group_name": host_group_name,
            "policy_id": policy_id,
            "policy_name": policy_name,
            "platform": platform,
            "whitelist": whitelist,
            "created_at": datetime.now(pytz.UTC).isoformat(),
            "created_by": username,
            "created_by_source": created_by_source or "none"
        }
        try:
            resp = custom_storage.PutObjectByVersion(
                body=record,
                collection_name="relationship",
                collection_version=COLLECTION_RELATION_VER,
                object_key=relationship_key(cat, rule_group_id, host_group_id)
            )
        except Exception as e:
            if logger:
                logger.error(f"Error writing relationship for {cat}: {e}")
            return False
        if resp.get('status_code') == 200:
            return True
        if logger:
            logger.error(f"Failed to write relationship for {cat}: {resp}")
        return False

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(_write_single, categories_list))

    success_count = sum(results)
    return {"success_count": success_count, "error_count": len(results) - success_count}


def _relationship_records(rule_group_id, custom_storage, logger=None):
    """Relationship records of a rule group: (records, None) or (None, error message)."""
    result = read_all_objects(custom_storage, "relationship", COLLECTION_RELATION_VER, logger=logger)
    if "error" in result:
        if logger:
            logger.error(f"Could not list relationships: {result['error']}")
        return None, "Failed to read relationships"
    return [item for item in result['resources']
            if isinstance(item, dict) and item.get('rule_group_id') == rule_group_id], None


def _delete_relationship_records(records, custom_storage, logger=None):
    """Delete the given relationship records in parallel. Returns the number actually deleted."""
    keys_to_delete = [k for k in (item.get('_key') for item in records) if k]
    if not keys_to_delete:
        return 0

    def _delete_single(key):
        try:
            if delete_object(custom_storage, "relationship", COLLECTION_RELATION_VER, key):
                return True
        except Exception as e:
            if logger:
                logger.error(f"Error deleting relationship {key}: {e}")
            return False
        if logger:
            logger.warning(f"Failed to delete relationship {key}")
        return False

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(_delete_single, keys_to_delete))

    deleted_count = sum(results)
    if logger and deleted_count < len(results):
        logger.warning(f"Relationship cleanup: {deleted_count} deleted, {len(results) - deleted_count} errors")
    return deleted_count


def _escape_fql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_policy_id_by_name(fw_policies, policy_name, logger=None):
    """
    Look up a firewall policy by name, for relationship records written before policy_id
    was stored. Returns (policy_id or None when it does not exist, error message or None).
    """
    resp = fw_policies.query_combined_policies(filter=f"name:'{_escape_fql(policy_name)}'", limit=1)
    ok, err = _validate_falcon_response(resp, "query_combined_policies", logger)
    if not ok:
        return None, err
    resources = resp.get('body', {}).get('resources') or []
    return (resources[0].get('id') if resources else None), None


NAME_LOOKUP_BATCH = 100  # policy names per FQL `name:[...]` query


def _find_policy_ids_by_names(fw_policies, policy_names, logger=None):
    """
    Batched _find_policy_id_by_name: one query per NAME_LOOKUP_BATCH names.
    Returns ({name: policy_id} for the names that exist, None) or (None, error message).
    """
    found = {}
    names = list(dict.fromkeys(policy_names))
    for i in range(0, len(names), NAME_LOOKUP_BATCH):
        chunk = names[i:i + NAME_LOOKUP_BATCH]
        name_filter = ",".join(f"'{_escape_fql(name)}'" for name in chunk)
        resp = fw_policies.query_combined_policies(filter=f"name:[{name_filter}]", limit=5000)
        ok, err = _validate_falcon_response(resp, "query_combined_policies", logger)
        if not ok:
            return None, err
        for resource in resp.get('body', {}).get('resources') or []:
            found.setdefault(resource.get('name'), resource.get('id'))
    return found, None


def _resolve_policy_id(fw_policies, records, logger=None):
    """
    Policy id of a rule group, taken only from its stored relationship records (never from
    the request), or resolved by name for records written before policy_id was stored.
    """
    policy_id = next((r.get('policy_id') for r in records if r.get('policy_id')), None)
    if policy_id:
        return policy_id, None
    policy_name = next((r.get('policy_name') for r in records if r.get('policy_name')), None)
    if not policy_name:
        return None, None
    return _find_policy_id_by_name(fw_policies, policy_name, logger)


def _policy_platform(fw_policies, policy_id, logger=None):
    """Platform key ('windows', 'mac', 'linux') of an existing Falcon policy, or None."""
    resp = fw_policies.get_policies(ids=[policy_id])
    ok, _err = _validate_falcon_response(resp, "get_policies", logger)
    resources = (resp.get('body', {}).get('resources') or []) if ok else []
    platform = (resources[0].get('platform_name') or '').lower() if resources else ''
    return platform if platform in PLATFORM_NAMES else None


def _deleted(response, operation_name, logger=None):
    """Like _validate_falcon_response, but a 404 (already gone) also counts as deleted."""
    if isinstance(response, dict) and response.get("status_code") == 404:
        return True, None
    return _validate_falcon_response(response, operation_name, logger)


def _delete_policy(fw_policies, policy_id, operation_name, logger=None, reenable_on_failure=True):
    """
    Disable, then delete a firewall policy (Falcon may refuse to delete an enabled one).
    If the delete fails after the disable succeeded, the policy is enabled again so its host
    group stays protected (`reenable_on_failure=False` leaves it disabled, for rollbacks).
    """
    disable_resp = fw_policies.perform_action(action_name="disable", ids=policy_id)
    ok, err = _deleted(disable_resp, f"{operation_name}_disable", logger)
    if not ok:
        return False, err
    ok, err = _deleted(fw_policies.delete_policies(ids=policy_id), operation_name, logger)
    if ok or not reenable_on_failure or disable_resp.get("status_code") == 404:
        return ok, err
    enabled, enable_err = _validate_falcon_response(
        fw_policies.perform_action(action_name="enable", ids=policy_id), f"{operation_name}_reenable", logger)
    if not enabled:
        return False, (f"{err}; the policy was left disabled and could not be enabled again "
                       f"({enable_err}), so it must be enabled manually in Falcon")
    return False, err


def _rollback(mgmt, fw_policies, policy_id, rg_id, logger=None):
    """
    Delete resources created during a failed operation: the policy first, then its rule group.
    Returns a message saying whether everything was actually removed.
    """
    leftovers = []
    if policy_id and not _delete_policy(fw_policies, policy_id, "rollback_delete_policy", logger,
                                        reenable_on_failure=False)[0]:
        leftovers.append(f"policy {policy_id}")
    if rg_id and not _deleted(mgmt.delete_rule_groups(ids=[rg_id]), "rollback_delete_rule_group", logger)[0]:
        leftovers.append(f"rule group {rg_id}")
    if leftovers:
        return (f"Rollback incomplete: {' and '.join(leftovers)} could not be deleted "
                "and must be removed manually in Falcon.")
    return "Rolled back."


def _build_rules_list(policy_name, categories, whitelist_raw):
    """Build the firewall rules for a policy from its whitelist and categories."""
    rules_list = []
    temp_counter = 0

    if whitelist_raw:
        wl_urls = _sanitize_url_list(whitelist_raw, separator=';')
        if wl_urls:
            rules_list.append(_build_rule("whitelist_allow", "ALLOW", ';'.join(wl_urls), str(temp_counter),
                                          f"Whitelist for {policy_name}"))
            temp_counter += 1

    for category_name, urls_raw in categories.items():
        if not urls_raw:
            continue
        clean_urls = _sanitize_url_list(urls_raw, separator=';')
        if not clean_urls:
            continue
        rules_list.append(_build_rule(f"deny_{category_name}", "DENY", ';'.join(clean_urls), str(temp_counter),
                                      f"Block {category_name}"))
        temp_counter += 1

    return rules_list


def _create_policy_with_rule_group(mgmt, fw_policies, policy_name, platform, platform_name,
                                   host_group_id, rules_list, description_prefix, logger, create_name=None):
    """
    Create policy -> enable -> assign host group -> create rule group -> attach it.

    The policy is created as `create_name` (defaults to `policy_name`), which lets an update
    create the replacement while the old policy still holds the name.
    Any failure rolls back what was created in Falcon.
    Returns (policy_id, rule_group_id, None) or (None, None, Response).
    """
    policy_id = None
    rg_id = None

    def _fail(code, message):
        outcome = _rollback(mgmt, fw_policies, policy_id, rg_id, logger)
        return None, None, Response(code=code, body={"error": f"{message}. {outcome}"})

    policy_resp = fw_policies.create_policies(
        description=f"Policy for {policy_name}", name=create_name or policy_name, platform_name=platform_name)
    ok, err = _validate_falcon_response(policy_resp, "create_policies", logger)
    if not ok:
        return None, None, Response(code=policy_resp.get("status_code", 500),
                                    body={"error": f"Failed to create policy: {err}"})
    policy_id = policy_resp["body"]["resources"][0]["id"]

    resp = fw_policies.perform_action(action_name="enable", ids=policy_id)
    ok, err = _validate_falcon_response(resp, "enable_policy", logger)
    if not ok:
        return _fail(500, f"Failed to enable policy: {err}")

    resp = fw_policies.perform_action(action_name="add-host-group", group_id=host_group_id, ids=policy_id)
    ok, err = _validate_falcon_response(resp, "add_host_group", logger)
    if not ok:
        return _fail(500, f"Failed to assign host group: {err}")

    rg_resp = mgmt.create_rule_group(
        description=f"{description_prefix} for {policy_name}", enabled=True,
        name=f"{policy_name}_RuleGroup", platform=platform, rules=rules_list)
    ok, err = _validate_falcon_response(rg_resp, "create_rule_group", logger)
    if not ok:
        return _fail(500, f"Failed to create rule group: {err}")
    rg_id = rg_resp["body"]["resources"][0]

    resp = mgmt.update_policy_container(
        default_inbound="ALLOW", default_outbound="ALLOW", platform_id=platform, enforce=True,
        local_logging=True, is_default_policy=False, test_mode=False,
        rule_group_ids=rg_id, policy_id=policy_id, body={}
    )
    ok, err = _validate_falcon_response(resp, "update_policy_container", logger)
    if not ok:
        return _fail(500, f"Failed to attach rule group: {err}")

    return policy_id, rg_id, None


@FUNC.handler(method='POST', path='/create-rule')
# pylint: disable-next=too-many-return-statements
def create_rule(request: Request, _: dict, logger: Logger) -> Response:
    """Create a firewall policy + rule group and persist the relationships."""
    logger.info("Starting create-rule handler")
    try:
        if not request.body:
            return Response(code=400, body={"error": "Request body is required"})

        host_group_id = request.body.get('hostGroupId')
        policy_name = request.body.get('policyName', '').strip()
        platform = request.body.get('platform', '').lower()
        categories = request.body.get('categories', {})
        whitelist_raw = request.body.get('whitelist', '').strip()
        host_group_name = request.body.get('hostGroupName', 'Unknown Host Group')
        username, username_source = resolve_creator(request)

        platform_name = PLATFORM_NAMES.get(platform)
        if not platform_name:
            return Response(code=400, body={"error": f"Platform must be one of: {', '.join(PLATFORM_NAMES)}"})

        if not host_group_id or not policy_name or not isinstance(categories, dict):
            return Response(code=400, body={"error": "Missing required fields"})

        rules_list = _build_rules_list(policy_name, categories, whitelist_raw)
        if not rules_list:
            return Response(code=400, body={"error": "No valid rules could be built"})

        mgmt = get_client(FirewallManagement)
        fw_policies = get_client(FirewallPolicies)
        custom_storage = get_client(CustomStorage)

        policy_id, rule_group_id, error = _create_policy_with_rule_group(
            mgmt, fw_policies, policy_name, platform, platform_name,
            host_group_id, rules_list, "Rule group", logger)
        if error:
            return error

        # Relationship write failures are logged but do not roll back Falcon resources
        write_result = _write_relationships(
            list(categories.keys()), rule_group_id, host_group_id, host_group_name,
            policy_name, platform, whitelist_raw, username, policy_id, custom_storage, logger,
            created_by_source=username_source)
        if write_result["error_count"]:
            logger.warning(f"create-rule: {write_result['error_count']} relationship writes failed")

        logger.info(f"Create-rule completed: {policy_name}, policy={policy_id}, rg={rule_group_id}")
        return Response(code=200, body={
            "success": True,
            "policyName": policy_name,
            "policyId": policy_id,
            "ruleGroupId": rule_group_id,
            "rulesCreated": len(rules_list),
            "relationsWritten": write_result["success_count"],
            "createdBy": username,
            "createdBySource": username_source,
        })

    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to create rule"})


@FUNC.handler(method='GET', path='/list-policies')
def list_policies(_: Request, __: dict, logger: Logger) -> Response:
    """List the policies created by this app with their categories and host groups."""
    try:
        custom_storage = get_client(CustomStorage)
        result = read_all_objects(custom_storage, "relationship", COLLECTION_RELATION_VER, logger=logger)
        if "error" in result:
            return Response(code=500, body={"error": "Failed to list policies"})

        grouped: dict = {}
        for item in result['resources']:
            if not isinstance(item, dict):
                continue
            rg_id = item.get('rule_group_id')
            if not rg_id:
                continue

            if rg_id not in grouped:
                grouped[rg_id] = {
                    "rule_group_id": rg_id, "policy_id": item.get('policy_id', ''),
                    "policy_name": item.get('policy_name', ''),
                    "host_group_id": item.get('host_group_id', ''), "host_group_name": item.get('host_group_name', ''),
                    "platform": item.get('platform', ''), "whitelist": item.get('whitelist', ''),
                    "created_at": item.get('created_at', ''), "created_by": item.get('created_by', ''),
                    "created_by_source": item.get('created_by_source', ''),
                    "categories": []
                }
            cat = item.get('category_name')
            if cat and cat not in grouped[rg_id]["categories"]:
                grouped[rg_id]["categories"].append(cat)

        return Response(code=200, body={"policies": list(grouped.values()), "pagination": result["pagination"]})
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to list policies"})


@FUNC.handler(method='POST', path='/delete-policy')
# pylint: disable-next=too-many-return-statements
def delete_policy(request: Request, _: dict, logger: Logger) -> Response:
    """
    Delete a policy, then its rule group, then its stored relationships.

    The policy to delete is resolved from the rule group's stored relationship records, never
    taken from the request. Relationships are removed only when both Falcon deletions succeed,
    so a failed deletion leaves the policy visible in /list-policies and can be retried.
    """
    logger.info("Starting delete-policy handler")
    try:
        body = request.body or {}
        rule_group_id = body.get('rule_group_id', '').strip()

        if not rule_group_id:
            return Response(code=400, body={"error": "rule_group_id is required"})

        mgmt = get_client(FirewallManagement)
        fw_policies = get_client(FirewallPolicies)
        custom_storage = get_client(CustomStorage)

        records, err = _relationship_records(rule_group_id, custom_storage, logger)
        if err:
            return Response(code=500, body={"error": f"{err}. Nothing was deleted."})
        if not records:
            return Response(code=404, body={"error": f"No policy managed by this app uses rule group {rule_group_id}"})

        # Records written by earlier versions have no policy_id: resolve it by name
        policy_id, err = _resolve_policy_id(fw_policies, records, logger)
        if err:
            return Response(code=500, body={"error": f"Failed to look up the policy: {err}. Nothing was deleted."})

        if policy_id:
            ok, err = _delete_policy(fw_policies, policy_id, "delete_policies", logger)
            if not ok:
                return Response(code=500, body={"error": f"Failed to delete policy: {err}. Nothing was deleted."})

        ok, err = _deleted(mgmt.delete_rule_groups(ids=[rule_group_id]), "delete_rule_groups", logger)
        if not ok:
            return Response(code=500, body={
                "error": f"Policy deleted, but the rule group could not be deleted: {err}. Please retry."})

        deleted = _delete_relationship_records(records, custom_storage, logger)

        logger.info(f"Delete-policy completed: RG={rule_group_id}, Policy={policy_id}, relations deleted={deleted}")
        return Response(code=200, body={"success": True, "relationsDeleted": deleted})
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to delete policy"})


_UPDATING_SUFFIX = re.compile(r'(?: \(updating [0-9a-f]{8}\))+$')


def _strip_updating_suffix(policy_name: str) -> str:
    """'P (updating ab12cd34)' -> 'P': the temporary name an update uses while the old policy exists."""
    return _UPDATING_SUFFIX.sub('', policy_name).strip()


@FUNC.handler(method='POST', path='/update-policy')
# pylint: disable-next=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
def update_policy(request: Request, _: dict, logger: Logger) -> Response:
    """
    Replace a policy without leaving the host group unprotected:
      1. create the new policy + rule group and attach them (under a temporary name while
         the old policy still holds the name; rolled back on failure, old policy untouched)
      2. delete the old policy (on failure the new one is rolled back)
      3. rename the new policy and delete the old rule group
      4. write the new relationships, then remove the old ones

    The policy being replaced, its host group, name and platform are taken from the stored
    relationship records; the request is only used for legacy records that lack them.
    """
    logger.info("Starting update-policy handler")
    try:
        body = request.body or {}
        old_rg_id = body.get('ruleGroupId', '').strip()
        categories = body.get('categories', {})
        whitelist_raw = body.get('whitelist', '').strip()
        username, username_source = resolve_creator(request)

        if not old_rg_id or not isinstance(categories, dict):
            return Response(code=400, body={"error": "Missing required fields"})

        mgmt = get_client(FirewallManagement)
        fw_policies = get_client(FirewallPolicies)
        custom_storage = get_client(CustomStorage)

        old_records, err = _relationship_records(old_rg_id, custom_storage, logger)
        if err:
            return Response(code=500, body={"error": f"{err}. Nothing was changed."})
        if not old_records:
            return Response(code=404, body={"error": f"No policy managed by this app uses rule group {old_rg_id}"})

        def _stored(field):
            return next((r.get(field) for r in old_records if r.get(field)), None)

        host_group_id = _stored('host_group_id') or body.get('hostGroupId', '').strip()
        host_group_name = _stored('host_group_name') or body.get('hostGroupName', 'Unknown')
        # A failed rename leaves the temporary suffix in the stored name: drop it so it does not nest
        policy_name = _strip_updating_suffix(_stored('policy_name') or body.get('policyName', '').strip())
        if not policy_name or not host_group_id:
            return Response(code=400, body={"error": "Missing required fields"})

        rules_list = _build_rules_list(policy_name, categories, whitelist_raw)
        if not rules_list:
            return Response(code=400, body={"error": "No valid rules could be built"})

        # Records written by earlier versions have no policy_id: resolve it by name
        old_policy_id, err = _resolve_policy_id(fw_policies, old_records, logger)
        if err:
            return Response(code=500, body={"error": f"Failed to look up the current policy: {err}. Nothing was changed."})

        # Records written by earlier versions have no platform either: read it from the Falcon
        # policy, and only when there is none fall back to the request
        platform = _stored('platform')
        if platform not in PLATFORM_NAMES and old_policy_id:
            platform = _policy_platform(fw_policies, old_policy_id, logger)
        if platform not in PLATFORM_NAMES and not old_policy_id:
            platform = body.get('platform', '').strip().lower()
        if platform not in PLATFORM_NAMES:
            return Response(code=400, body={
                "error": f"Could not determine the platform; it must be one of: {', '.join(PLATFORM_NAMES)}"})
        platform_name = PLATFORM_NAMES[platform]

        # Phase 1: create and attach the replacement while the old policy keeps enforcing
        create_name = f"{policy_name} (updating {uuid.uuid4().hex[:8]})" if old_policy_id else policy_name
        new_policy_id, new_rg_id, error = _create_policy_with_rule_group(
            mgmt, fw_policies, policy_name, platform, platform_name,
            host_group_id, rules_list, "Group", logger, create_name=create_name)
        if error:
            return error

        # Phase 2: remove the old policy only now that the new one is in place
        if old_policy_id:
            ok, err = _delete_policy(fw_policies, old_policy_id, "delete_old_policy", logger)
            if not ok:
                outcome = _rollback(mgmt, fw_policies, new_policy_id, new_rg_id, logger)
                return Response(code=500, body={
                    "error": f"Failed to delete the current policy: {err}. The update was not applied. {outcome}"})

        # Phase 3: give the new policy its final name and delete the old rule group
        warnings = []
        final_name = policy_name
        if create_name != policy_name:
            # firewall_policy_payload drops `id`, so the body is passed explicitly
            ok, err = _validate_falcon_response(
                fw_policies.update_policies(body={"resources": [{"id": new_policy_id, "name": policy_name}]}),
                "rename_policy", logger)
            if not ok:
                final_name = create_name
                warnings.append(f"The policy is active but kept the name '{create_name}': {err}")
        ok, err = _deleted(mgmt.delete_rule_groups(ids=[old_rg_id]), "delete_old_rule_group", logger)
        if not ok:
            warnings.append(f"The previous rule group {old_rg_id} could not be deleted: {err}")

        # Phase 4: write the new relationships before removing the old ones
        write_result = _write_relationships(
            list(categories.keys()), new_rg_id, host_group_id, host_group_name,
            final_name, platform, whitelist_raw, username, new_policy_id, custom_storage, logger,
            created_by_source=username_source, rule_group_name=f"{policy_name}_RuleGroup")
        if write_result["error_count"]:
            warnings.append(f"{write_result['error_count']} relationship records could not be written")
        deleted_count = _delete_relationship_records(old_records, custom_storage, logger)
        logger.info(f"Deleted {deleted_count} old relationships")

        for warning in warnings:
            logger.warning(f"update-policy: {warning}")
        logger.info(f"Update-policy completed: {final_name}, new RG: {new_rg_id}")
        return Response(code=200, body={
            "success": True,
            "newRuleGroupId": new_rg_id,
            "newPolicyId": new_policy_id,
            "relationsWritten": write_result["success_count"],
            "warnings": warnings,
        })
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to update policy"})


def _blocking_candidates(fqdn: str) -> list:
    """
    Rule entries that would block `fqdn`, most specific first: the exact name, its own
    wildcard and the wildcard of every parent domain (never a bare TLD wildcard like *.com).
    e.g. mail.google.com -> [mail.google.com, *.mail.google.com, *.google.com]
    """
    labels = fqdn.split('.')
    return [fqdn] + ['*.' + '.'.join(labels[i:]) for i in range(len(labels) - 1)]


@FUNC.handler(method='GET', path='/simulate-policy')
# pylint: disable-next=too-many-return-statements
def simulate_policy(request: Request, _: dict, logger: Logger) -> Response:
    """Report whether a given FQDN would be blocked by any stored category."""
    try:
        fqdn = query_param(request, 'fqdn').strip().lower()
        if not fqdn:
            return Response(code=400, body={"error": "fqdn required"})
        if not validate_fqdn(fqdn):
            return Response(code=400, body={"error": "Invalid fqdn"})

        custom_storage = get_client(CustomStorage)
        candidates = _blocking_candidates(fqdn)

        def _domains(item):
            return {d.strip().lower() for d in item.get('domain', '').split(';') if d.strip()}

        def _matching_entry(item):
            return next((c for c in candidates if c in _domains(item)), None)

        def _legacy_matching_entry(item):
            # Categories stored by earlier versions use wildcards without a dot (*example.com),
            # which Falcon matches against any name ending in "example.com"
            return next((d for d in sorted(_domains(item))
                         if d.startswith('*') and not d.startswith('*.') and len(d) > 1 and fqdn.endswith(d[1:])),
                        None)

        # Early return: stop paging as soon as the domain is found
        result = read_all_objects(custom_storage, 'domain', COLLECTION_DOMAIN_VER,
                                  stop_when=lambda item: _matching_entry(item) is not None, logger=logger)
        if "error" in result:
            return Response(code=500, body={"error": "Failed to simulate"})

        def _blocked(item, rule):
            return Response(code=200, body={"found": True, "category": item.get('category'), "rule": rule,
                                            "message": f"Blocked by {item.get('category')}",
                                            "pagination": result["pagination"]})

        item = result["match"]
        if item:
            return _blocked(item, _matching_entry(item))

        # _sanitize_url_list drops dotless wildcards, so they only block in policies deployed by
        # earlier versions (relationship records without policy_id) that were never re-saved
        legacy_matches = [(i, _legacy_matching_entry(i)) for i in result["resources"] if _legacy_matching_entry(i)]
        if legacy_matches:
            relationships = read_all_objects(custom_storage, "relationship", COLLECTION_RELATION_VER, logger=logger)
            if "error" in relationships:
                return Response(code=500, body={"error": "Failed to simulate"})
            legacy_categories = {r.get('category_name') for r in relationships["resources"]
                                 if isinstance(r, dict) and not r.get('policy_id')}
            for legacy_item, rule in legacy_matches:
                if legacy_item.get('category') in legacy_categories:
                    return _blocked(legacy_item, rule)

        return Response(code=200, body={"found": False, "category": None, "message": "Not blocked",
                                        "pagination": result["pagination"]})
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to simulate"})


@FUNC.handler(method='GET', path='/check-enforcement')
def check_enforcement(request: Request, _: dict, logger: Logger) -> Response:
    """Check the enforcement status of a specific policy."""
    logger.info("Starting /check-enforcement handler")
    try:
        policy_id = query_param(request, 'policy_id').strip()
        if not policy_id:
            return Response(code=400, body={"error": "policy_id is required"})

        mgmt = get_client(FirewallManagement)
        resp = mgmt.get_policy_containers(ids=policy_id)

        if resp.get('status_code') != 404:
            ok, err = _validate_falcon_response(resp, "get_policy_containers", logger)
            if not ok:
                return Response(code=502, body={"error": f"Failed to read the policy container from Falcon: {err}"})
        if not (resp.get('body') or {}).get('resources'):
            return Response(code=404, body={"error": "Policy container not found"})

        container = resp['body']['resources'][0]

        result = {
            "policy_id": container.get("policy_id"),
            "enforce": container.get("enforce"),
            "default_inbound": container.get("default_inbound"),
            "default_outbound": container.get("default_outbound"),
            "local_logging": container.get("local_logging"),
            "test_mode": container.get("test_mode"),
            "rule_group_ids": container.get("rule_group_ids", [])
        }

        logger.info(f"Successfully completed /check-enforcement for policy {policy_id}")
        return Response(code=200, body=result)
    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to check enforcement"})



GET_BY_IDS_BATCH = 100  # ids per Falcon "get by ids" request


def _get_by_ids(get_fn, ids, id_field, operation_name, logger=None):
    """
    Fetch resources by id in batches. Returns ({id: resource}, None) or (None, error message).
    A 404 only means some ids do not exist, so the resources that were found are kept.
    """
    found = {}
    for i in range(0, len(ids), GET_BY_IDS_BATCH):
        resp = get_fn(ids=ids[i:i + GET_BY_IDS_BATCH])
        status = resp.get('status_code') if isinstance(resp, dict) else None
        if status != 404:
            ok, err = _validate_falcon_response(resp, operation_name, logger)
            if not ok:
                return None, err
        for resource in (resp.get('body') or {}).get('resources') or []:
            found[resource.get(id_field)] = resource
    return found, None


@FUNC.handler(method='GET', path='/health-check')
# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def health_check(_request: Request, _: dict, logger: Logger) -> Response:
    """Validate all policies created by the app (batched Falcon calls)."""
    logger.info("Starting /health-check handler")
    try:
        custom_storage = get_client(CustomStorage)
        fw_policies = get_client(FirewallPolicies)
        mgmt = get_client(FirewallManagement)

        result = read_all_objects(custom_storage, "relationship", COLLECTION_RELATION_VER, logger=logger)
        if "error" in result:
            return Response(code=500, body={"error": "Failed to read relationships"})

        # One entry per policy: keyed by policy_id, or by name for legacy records without it
        unique_policies = {}
        for item in result['resources']:
            if not isinstance(item, dict):
                continue
            policy_name = item.get('policy_name')
            if not policy_name:
                continue
            unique_policies.setdefault(item.get('policy_id') or f"name:{policy_name}", item)

        # Legacy records (no policy_id): resolve by name in batches, with the values escaped for FQL
        legacy_names = [item['policy_name'] for key, item in unique_policies.items() if key.startswith("name:")]
        ids_by_name, err = _find_policy_ids_by_names(fw_policies, legacy_names, logger)
        if err:
            return Response(code=502, body={"error": f"Failed to look up policies in Falcon: {err}"})
        resolved = {  # key -> policy_id
            key: ids_by_name.get(item['policy_name']) if key.startswith("name:") else key
            for key, item in unique_policies.items()
        }

        policy_ids = list(dict.fromkeys(pid for pid in resolved.values() if pid))
        policies_by_id, err = _get_by_ids(fw_policies.get_policies, policy_ids, 'id', "get_policies", logger)
        if err:
            return Response(code=502, body={"error": f"Failed to read policies from Falcon: {err}"})
        containers_by_id, err = _get_by_ids(mgmt.get_policy_containers, policy_ids, 'policy_id',
                                            "get_policy_containers", logger)
        if err:
            return Response(code=502, body={"error": f"Failed to read policy containers from Falcon: {err}"})

        results = []
        healthy_count = 0
        issues_count = 0

        for key, rel_item in unique_policies.items():
            policy_id = resolved[key]
            pol_info = {"policy_name": rel_item['policy_name'], "policy_id": policy_id, "status": "error", "issues": []}

            pol = policies_by_id.get(policy_id) if policy_id else None
            if not pol:
                pol_info["issues"].append("Policy not found in Falcon")
                issues_count += 1
                results.append(pol_info)
                continue

            pol_info['enabled'] = pol.get('enabled', False)
            if not pol.get('enabled'):
                pol_info["issues"].append("Policy DISABLED")

            groups = pol.get('groups', [])
            pol_info['host_groups'] = len(groups)
            if not groups:
                pol_info["issues"].append("No host groups assigned")

            container = containers_by_id.get(policy_id)
            if container:
                pol_info['enforce'] = container.get('enforce', False)
                if not container.get('enforce'):
                    pol_info["issues"].append("Enforcement OFF - filtering NOT active")
                rule_groups = container.get('rule_group_ids', [])
                pol_info['rule_groups'] = len(rule_groups)
                if not rule_groups:
                    pol_info["issues"].append("No rule groups attached")
            else:
                pol_info["issues"].append("Could not fetch policy container")

            if not pol_info["issues"]:
                pol_info["status"] = "healthy"
                del pol_info["issues"]
                healthy_count += 1
            else:
                issues_count += 1
            results.append(pol_info)

        summary = {
            "healthy": issues_count == 0 and len(unique_policies) > 0,
            "total_policies_checked": len(unique_policies),
            "healthy_count": healthy_count,
            "issues_count": issues_count,
            "policies": results,
            "pagination": result["pagination"]
        }

        logger.info("Successfully completed /health-check")
        return Response(code=200, body=summary)

    except Exception:
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to run health check"})

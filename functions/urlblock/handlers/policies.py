"""Handlers for creating, updating, deleting, listing and simulating firewall policies."""

# Handlers deliberately catch every exception to log it and return a 500 response.
# pylint: disable=broad-exception-caught,too-many-lines

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
    _sanitize_url_list, _build_rule, read_all_objects, read_objects, list_object_keys, delete_object,
    query_param, category_key, relationship_key, validate_fqdn, _validate_falcon_response, resolve_creator,
    plural,
)

PLATFORM_NAMES = {'windows': 'Windows', 'mac': 'Mac', 'linux': 'Linux'}

# Records written with a policy whose rule was built through _sanitize_url_list. Records without
# it come from earlier versions, whose rules hold the raw category entries.
RULE_FORMAT_SANITIZED = "sanitized"

# Relationship keys are listed (one call per page) before reading only the records needed. The cap
# keeps the listing well within the function's 300 s limit (max_exec_duration_seconds).
RELATIONSHIP_PAGE_SIZE = 200
RELATIONSHIP_MAX_PAGES = 100  # 20,000 keys


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
            "created_by_source": created_by_source or "none",
            # only written once the policy exists, with its rule built by _build_rules_list
            "rule_format": RULE_FORMAT_SANITIZED,
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


def _relationship_key_parts(key):
    """
    (category, rule group id, host group id) of a relationship key, or None for a key of another
    shape. Keys are <category>_<rule group id>_<host group id>: relationship_key() here, and the
    raw category name in earlier versions. Falcon ids contain no '_', so the split is unambiguous.
    """
    parts = key.rsplit('_', 2)
    return tuple(parts) if len(parts) == 3 and all(parts) else None


def _list_relationship_keys(custom_storage, logger=None):
    """
    Every relationship key: (keys, None) or (None, error message). A truncated listing is an
    error, since a missing key cannot be ruled out.
    """
    listing = list_object_keys(custom_storage, "relationship", COLLECTION_RELATION_VER,
                               page_size=RELATIONSHIP_PAGE_SIZE, max_pages=RELATIONSHIP_MAX_PAGES)
    if "error" in listing:
        if logger:
            logger.error(f"Could not list relationships: {listing['error']}")
        return None, "Failed to read relationships"
    if listing["pagination"]["truncated"]:
        limit = RELATIONSHIP_PAGE_SIZE * RELATIONSHIP_MAX_PAGES
        return None, f"There are more than {limit} relationships, so they could not all be listed"
    return listing["keys"], None


def _read_relationships(custom_storage, keys, wanted, logger=None):
    """
    The relationship records whose key, among the listed `keys`, `wanted(_relationship_key_parts(key))`
    selects: only those are read. Returns (records, None) or (None, error message): a failed
    read of a selected key is an error, since the missing record cannot be ruled out.
    """
    keys = [k for k in keys if wanted(_relationship_key_parts(k))]
    records, failed = read_objects(custom_storage, "relationship", COLLECTION_RELATION_VER, keys, logger=logger)
    if failed:
        if logger:
            logger.error(f"Could not read relationships {failed}")
        return None, "Some relationships could not be read"
    return records, None


def _tracked_rule_groups(keys, records=()):
    """
    The rule groups this app has relationship records of: those named by the keys, and those
    of `records` (read records, which covers keys of another shape).
    """
    named = {parts[1] for parts in map(_relationship_key_parts, keys) if parts}
    return named | {r.get('rule_group_id') for r in records if r.get('rule_group_id')}


def _relationship_records(rule_group_id, custom_storage, logger=None):
    """
    Relationship records of a rule group, and every rule group the app tracks (see
    _tracked_rule_groups): (records, tracked rule groups, None) or (None, None, error message).
    Only keys that name this rule group (or have another shape) are read, so an unreadable
    record of another rule group never blocks the operation; a failed read of one of these keys
    is an error, since acting on some of a rule group's records would leave the others behind.
    """
    keys, err = _list_relationship_keys(custom_storage, logger)
    if err:
        return None, None, err
    records, err = _read_relationships(
        custom_storage, keys, lambda parts: parts is None or parts[1] == rule_group_id, logger)
    if err:
        return None, None, err
    return ([r for r in records if r.get('rule_group_id') == rule_group_id],
            _tracked_rule_groups(keys, records), None)


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


def _update_records(records, changes, custom_storage, logger=None):
    """
    Apply `changes` ({field: value}, None removes the field) to the given relationship records,
    in storage and in place. Returns True when every record that needed it was written.
    """
    all_written = True
    for record in records:
        key = record.get('_key')
        body = {k: v for k, v in record.items() if k != '_key'}
        for field, value in changes.items():
            if value is None:
                body.pop(field, None)
            else:
                body[field] = value
        if not key or body == {k: v for k, v in record.items() if k != '_key'}:
            continue
        try:
            resp = custom_storage.PutObjectByVersion(body=body, collection_name="relationship",
                                                     collection_version=COLLECTION_RELATION_VER, object_key=key)
            if resp.get('status_code') == 200:
                record.clear()
                record.update(body, _key=key)
                continue
        except Exception as e:
            resp = e
        all_written = False
        if logger:
            logger.error(f"Could not update relationship {key} with {changes}: {resp}")
    return all_written


STALE_MARKER_WARNING = ("The policy's records still say this app disabled it (disabled_by_app could not be cleared), "
                        "so a later failed delete could enable it again even if it has been disabled in Falcon.")


def _untracked_policy_warning(policy_id):
    """Warning for a policy whose relationship records could not be written at all."""
    return (f"No relationship record could be written: policy {policy_id} is in Falcon, but this app does not "
            "track it, so it is not listed in Firewall Rules. Manage or delete it in Falcon.")


def _set_disabled_by_app(records, value, custom_storage, logger=None):
    """
    Store on a rule group's relationship records whether this app left its policy disabled,
    so a retried delete still knows the policy must be enforcing again if it fails.
    Returns True when every record was written.
    """
    return _update_records(records, {'disabled_by_app': True if value else None}, custom_storage, logger)


def _store_policy_ref(records, policy, custom_storage, logger=None):
    """
    Record the policy resolved by name on legacy records (policy_id, and platform when missing),
    so a retry or a leftover record never resolves the name again to another policy.
    Returns True when the records were updated, or already had it.
    """
    if not policy or any(r.get('policy_id') for r in records):
        return True
    changes = {'policy_id': policy['id']}
    platform = (policy.get('platform_name') or '').lower()
    if platform in PLATFORM_NAMES and not any(r.get('platform') for r in records):
        changes['platform'] = platform
    return _update_records(records, changes, custom_storage, logger)


def _escape_fql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


NAME_LOOKUP_BATCH = 20  # policy names per FQL `name:[...]` query (kept short for the GET URL)


def _find_policies_by_names(fw_policies, policy_names, logger=None):
    """
    Look up firewall policies by exact name, for relationship records written before
    policy_id was stored: one query per NAME_LOOKUP_BATCH names.
    Returns ({name: [policy, ...]} for the names that exist, None) or (None, error message).
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
            if resource.get('name') in chunk:
                found.setdefault(resource['name'], []).append(resource)
    return found, None


def _group_ids(policy):
    """Ids of the host groups a Falcon policy is assigned to."""
    return {g.get('id') if isinstance(g, dict) else g for g in policy.get('groups') or []}


# pylint: disable-next=too-many-arguments,too-many-return-statements
def _match_legacy_policy(candidates, containers_by_id, rule_group_id, platform=None, host_group_id=None,
                         tracked_rule_groups=frozenset()):
    """
    The policy a legacy record refers to, among the Falcon policies with its name:
    (policy or None when none of them is it, error message or None). Only stored data decides:
    policies on another platform than the stored one are ignored, and the policy should hold the
    record's rule group in its Falcon container (`containers_by_id`), so an unrelated policy
    that shares the name, or a replacement renamed to it, is never matched. Several such
    policies are narrowed by the stored host group; any remaining ambiguity is an error.

    Earlier versions did not check that the rule group was attached, so a legacy policy may
    hold none. When no policy holds it, the policy is the only one with the name on the stored
    host group, but only if its container is empty: one that holds a rule group this app tracks
    (`tracked_rule_groups`, e.g. a replacement created by update-policy) is never it, and one
    that holds untracked rule groups (e.g. a replacement whose records could not be written),
    has no container in Falcon's answer, or shares that host group with another candidate
    cannot be confirmed, which is an error. Without a stored host group there is no fallback.

    Residual risk: a policy created by this version, with the same name on the same host group,
    whose rule group was detached by hand in Falcon has an empty container and holds no tracked
    rule group, so it would be taken for the legacy policy. Ruling it out needs the policy_id of
    every record, which is not read here.
    """
    def _rule_groups(policy):
        return (containers_by_id.get(policy.get('id')) or {}).get('rule_group_ids') or []

    if platform in PLATFORM_NAMES:
        candidates = [p for p in candidates if (p.get('platform_name') or '').lower() == platform]
    holding = [p for p in candidates if rule_group_id in _rule_groups(p)]
    if len(holding) > 1:
        holding = [p for p in holding if host_group_id in _group_ids(p)] or holding
    if len(holding) > 1:
        return None, f"{len(holding)} Falcon policies named '{holding[0].get('name')}' hold rule group {rule_group_id}"
    if holding:
        return holding[0], None

    if not host_group_id:
        return None, None
    on_host_group = [p for p in candidates if host_group_id in _group_ids(p)
                     and not set(_rule_groups(p)) & set(tracked_rule_groups)]
    if not on_host_group:
        return None, None
    name = on_host_group[0].get('name')
    if len(on_host_group) > 1:
        return None, (f"{len(on_host_group)} Falcon policies named '{name}' are on host group {host_group_id} "
                      f"and none holds rule group {rule_group_id}")
    policy = on_host_group[0]
    if policy.get('id') not in containers_by_id:
        return None, (f"Falcon returned no policy container for policy {policy.get('id')} named '{name}', "
                      f"so it cannot be confirmed as the policy of rule group {rule_group_id}")
    if _rule_groups(policy):
        return None, (f"Policy {policy.get('id')} named '{name}' does not hold rule group {rule_group_id} but holds "
                      "rule groups this app does not track, so it cannot be confirmed as its policy")
    return policy, None


def _read_policy(fw_policies, policy_id, operation_name, logger=None):
    """
    A Falcon policy by id: (policy, None), (None, None) when Falcon reports it does not exist
    (404), or (None, error message). A 200 without the policy proves nothing (e.g. eventual
    consistency right after a change), so it is an error rather than "gone".
    """
    resp = fw_policies.get_policies(ids=[policy_id])
    if resp.get("status_code") == 404:
        return None, None
    ok, err = _validate_falcon_response(resp, operation_name, logger)
    if not ok:
        return None, err
    resources = resp.get('body', {}).get('resources') or []
    if not resources:
        return None, f"Falcon returned no data for policy {policy_id}"
    return dict(resources[0], id=policy_id), None


def _current_policy(fw_policies, mgmt, records, tracked_rule_groups, logger=None):
    """
    The Falcon policy of a rule group, taken only from its stored relationship records (never
    from the request), or resolved by name for records written before policy_id was stored:
    the policy with that name whose Falcon container holds the stored rule group, or else the
    only one on the stored host group with an empty container (see _match_legacy_policy).
    Returns (policy or None when it does not exist, None) or (None, (HTTP status, error message)).
    """
    def _stored(field):
        return next((r.get(field) for r in records if r.get(field)), None)

    policy_id = _stored('policy_id')
    if policy_id:
        policy, err = _read_policy(fw_policies, policy_id, "get_policies", logger)
        return (None, (502, err)) if err else (policy, None)
    policy_name = _stored('policy_name')
    if not policy_name:
        return None, None
    found, err = _find_policies_by_names(fw_policies, [policy_name], logger)
    if err:
        return None, (502, err)
    candidates = found.get(policy_name, [])
    containers_by_id = {}
    if candidates:
        containers_by_id, err = _get_by_ids(mgmt.get_policy_containers, [p.get('id') for p in candidates],
                                            'policy_id', "get_policy_containers", logger)
        if err:
            return None, (502, err)
    policy, err = _match_legacy_policy(candidates, containers_by_id, _stored('rule_group_id'),
                                       _stored('platform'), _stored('host_group_id'), tracked_rule_groups)
    if err:
        return None, (409, err)
    return policy, None


def _deleted(response, operation_name, logger=None):
    """Like _validate_falcon_response, but a 404 (already gone) also counts as deleted."""
    if isinstance(response, dict) and response.get("status_code") == 404:
        return True, None
    return _validate_falcon_response(response, operation_name, logger)


# pylint: disable-next=too-many-arguments
def _delete_policy(fw_policies, policy_id, operation_name, logger=None, reenable_on_failure=True,
                   policy=None, disabled_by_app=False):
    """
    Disable, then delete a firewall policy (Falcon may refuse to delete an enabled one).

    If the delete fails, a policy that was enforcing is enabled again so its host group stays
    protected: one that was enabled, or one this app disabled earlier (`disabled_by_app`, from
    a previous attempt that could not enable it again). A policy disabled by someone else is
    neither disabled nor enabled. `policy` is the policy as read from Falcon (its `enabled`
    state); when it is not given, it is read first. `reenable_on_failure=False` ignores the
    state and never enables the policy again, for rollbacks of a policy that was just created.

    Returns (deleted, error message, left_disabled): left_disabled is True when the policy was
    enforcing and is left disabled.
    """
    if reenable_on_failure and policy is None:
        policy, err = _read_policy(fw_policies, policy_id, f"{operation_name}_read_state", logger)
        if err:
            return False, err, False
        if policy is None:
            return True, None, False
    enabled_now = bool(policy.get('enabled')) if reenable_on_failure else True
    restore = reenable_on_failure and (enabled_now or disabled_by_app)

    disable_resp = None
    if enabled_now:
        disable_resp = fw_policies.perform_action(action_name="disable", ids=policy_id)
        ok, err = _deleted(disable_resp, f"{operation_name}_disable", logger)
        if not ok:
            return False, err, False
    ok, err = _deleted(fw_policies.delete_policies(ids=policy_id), operation_name, logger)
    if ok or not restore or (disable_resp and disable_resp.get("status_code") == 404):
        return ok, err, False
    enabled, enable_err = _validate_falcon_response(
        fw_policies.perform_action(action_name="enable", ids=policy_id), f"{operation_name}_reenable", logger)
    if not enabled:
        return False, f"{err}; the policy was left disabled and could not be enabled again ({enable_err})", True
    return False, err, False


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


# pylint: disable-next=too-many-arguments
def _create_policy_with_rule_group(mgmt, fw_policies, policy_name, platform, platform_name,
                                   host_group_id, rules_list, description_prefix, logger, create_name=None,
                                   enabled=True):
    """
    Create policy -> enable -> assign host group -> create rule group -> attach it.

    The policy is created as `create_name` (defaults to `policy_name`), which lets an update
    create the replacement while the old policy still holds the name. `enabled=False` leaves
    it disabled, for the replacement of a policy that was disabled in Falcon.
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

    if enabled:
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

        # Relationship write failures do not roll back Falcon resources, but are reported
        write_result = _write_relationships(
            list(categories.keys()), rule_group_id, host_group_id, host_group_name,
            policy_name, platform, whitelist_raw, username, policy_id, custom_storage, logger,
            created_by_source=username_source)
        warnings = []
        if write_result["error_count"] and not write_result["success_count"]:
            warnings.append(_untracked_policy_warning(policy_id))
        elif write_result["error_count"]:
            warnings.append(f"{write_result['error_count']} of {plural(len(categories), 'relationship record')} "
                            "could not be written: those categories are blocked but not listed for this policy "
                            "in Firewall Rules.")
        for warning in warnings:
            logger.warning(f"create-rule: {warning}")

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
            "warnings": warnings,
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
# pylint: disable-next=too-many-return-statements,too-many-locals
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

        records, tracked_rule_groups, err = _relationship_records(rule_group_id, custom_storage, logger)
        if err:
            return Response(code=500, body={"error": f"{err}. Nothing was deleted."})
        if not records:
            return Response(code=404, body={"error": f"No policy managed by this app uses rule group {rule_group_id}"})

        # Records written by earlier versions have no policy_id: resolve it by name
        policy, lookup_error = _current_policy(fw_policies, mgmt, records, tracked_rule_groups, logger)
        if lookup_error:
            code, err = lookup_error
            return Response(code=code, body={"error": f"Failed to look up the policy: {err}. Nothing was deleted."})
        if not _store_policy_ref(records, policy, custom_storage, logger):
            return Response(code=500, body={"error": "Failed to record the policy id. Nothing was deleted."})

        policy_id = policy['id'] if policy else None
        if policy_id:
            disabled_by_app = any(r.get('disabled_by_app') for r in records)
            ok, err, left_disabled = _delete_policy(fw_policies, policy_id, "delete_policies", logger,
                                                    policy=policy, disabled_by_app=disabled_by_app)
            if not ok:
                # Remember a policy left disabled, so a retry enables it again if the delete fails again.
                # Without that marker a retry would not enable it: then only a manual enable helps.
                marked = _set_disabled_by_app(records, left_disabled, custom_storage, logger)
                if not left_disabled:
                    outcome = "Nothing was deleted." if marked else f"Nothing was deleted. {STALE_MARKER_WARNING}"
                elif marked:
                    outcome = "It must be enabled again manually in Falcon, or the delete retried."
                else:
                    outcome = "It must be enabled again manually in Falcon."
                return Response(code=500, body={"error": f"Failed to delete policy: {err}. {outcome}"})

        ok, err = _deleted(mgmt.delete_rule_groups(ids=[rule_group_id]), "delete_rule_groups", logger)
        if not ok:
            if policy_id:
                message = f"Policy deleted, but the rule group could not be deleted: {err}. Please retry."
            else:
                message = (f"No policy for this rule group was found in Falcon, and the rule group could not be "
                           f"deleted: {err}. Nothing was deleted; please retry.")
            return Response(code=500, body={"error": message})

        deleted = _delete_relationship_records(records, custom_storage, logger)
        # (c) a retry removes what is left: the policy and rule group are gone (404)
        warnings = []
        if deleted < len(records):
            warnings.append(f"{plural(len(records) - deleted, 'relationship record')} could not be removed, so this "
                            "rule group is still listed in Firewall Rules: delete it again to finish the cleanup.")

        logger.info(f"Delete-policy completed: RG={rule_group_id}, Policy={policy_id}, relations deleted={deleted}")
        return Response(code=200, body={"success": True, "relationsDeleted": deleted, "warnings": warnings})
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
      2. delete the old policy (on failure the new one is rolled back, unless the old one was
         left disabled: then the new one is kept and the old one stays listed for deletion)
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

        old_records, tracked_rule_groups, err = _relationship_records(old_rg_id, custom_storage, logger)
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

        # Read the current policy once: records written by earlier versions have no policy_id
        # (resolved by name) and no platform (read from the policy)
        old_policy, lookup_error = _current_policy(fw_policies, mgmt, old_records, tracked_rule_groups, logger)
        if lookup_error:
            code, err = lookup_error
            return Response(code=code, body={"error": f"Failed to look up the current policy: {err}. Nothing was changed."})
        if not _store_policy_ref(old_records, old_policy, custom_storage, logger):
            return Response(code=500, body={"error": "Failed to record the current policy id. Nothing was changed."})
        old_policy_id = old_policy['id'] if old_policy else None

        platform = _stored('platform')
        if platform not in PLATFORM_NAMES and old_policy:
            platform = (old_policy.get('platform_name') or '').lower()
        if platform not in PLATFORM_NAMES and not old_policy:
            # Nothing to replace: the request only chooses the platform of the policy to create
            platform = body.get('platform', '').strip().lower()
        if platform not in PLATFORM_NAMES:
            return Response(code=400, body={
                "error": f"Could not determine the platform; it must be one of: {', '.join(PLATFORM_NAMES)}"})
        platform_name = PLATFORM_NAMES[platform]

        # A policy disabled in Falcon (other than by this app) stays disabled: so does its replacement
        disabled_by_app = bool(_stored('disabled_by_app'))
        enforcing = not old_policy or bool(old_policy.get('enabled')) or disabled_by_app
        warnings = []
        if not enforcing:
            warnings.append("The current policy is disabled in Falcon, so its replacement was created disabled.")

        # Phase 1: create and attach the replacement while the old policy keeps enforcing
        create_name = f"{policy_name} (updating {uuid.uuid4().hex[:8]})" if old_policy_id else policy_name
        new_policy_id, new_rg_id, error = _create_policy_with_rule_group(
            mgmt, fw_policies, policy_name, platform, platform_name,
            host_group_id, rules_list, "Group", logger, create_name=create_name, enabled=enforcing)
        if error:
            return error

        # Phase 2: remove the old policy only now that the new one is in place
        old_policy_kept = False
        if old_policy_id:
            ok, err, left_disabled = _delete_policy(fw_policies, old_policy_id, "delete_old_policy", logger,
                                                    policy=old_policy, disabled_by_app=disabled_by_app)
            marker_cleared = True
            if not ok:
                # Either it is enforcing again, or the replacement enforces for it: never enable it later
                marker_cleared = _set_disabled_by_app(old_records, False, custom_storage, logger)
            if not ok and not left_disabled:
                outcome = _rollback(mgmt, fw_policies, new_policy_id, new_rg_id, logger)
                if not marker_cleared:
                    outcome = f"{outcome} {STALE_MARKER_WARNING}"
                return Response(code=500, body={
                    "error": f"Failed to delete the current policy: {err}. The update was not applied. {outcome}"})
            if not ok:
                # Rolling back now would leave the host group with only a disabled policy: keep the
                # replacement enforcing, and keep the old policy's records so it can be deleted later
                old_policy_kept = True
                warnings.append(f"The previous policy {old_policy_id} could not be deleted: {err}. "
                                "The new policy is enforcing; delete the previous one from Firewall Rules.")
                if not marker_cleared:
                    warnings.append(STALE_MARKER_WARNING)

        # Phase 3: give the new policy its final name and delete the old rule group
        # (both stay with the old policy while it still exists)
        final_name = policy_name
        if old_policy_kept:
            final_name = create_name
        elif create_name != policy_name:
            # firewall_policy_payload drops `id`, so the body is passed explicitly
            ok, err = _validate_falcon_response(
                fw_policies.update_policies(body={"resources": [{"id": new_policy_id, "name": policy_name}]}),
                "rename_policy", logger)
            if not ok:
                final_name = create_name
                warnings.append(f"The policy is active but kept the name '{create_name}': {err}")
        if not old_policy_kept:
            ok, err = _deleted(mgmt.delete_rule_groups(ids=[old_rg_id]), "delete_old_rule_group", logger)
            if not ok:
                warnings.append(f"The previous rule group {old_rg_id} could not be deleted: {err}")

        # Phase 4: write the new relationships before removing the old ones
        write_result = _write_relationships(
            list(categories.keys()), new_rg_id, host_group_id, host_group_name,
            final_name, platform, whitelist_raw, username, new_policy_id, custom_storage, logger,
            created_by_source=username_source, rule_group_name=f"{policy_name}_RuleGroup")
        if write_result["error_count"] and not write_result["success_count"]:
            warnings.append(_untracked_policy_warning(new_policy_id))
        elif write_result["error_count"]:
            warnings.append(f"{plural(write_result['error_count'], 'relationship record')} could not be written")
        if not old_policy_kept:
            deleted_count = _delete_relationship_records(old_records, custom_storage, logger)
            logger.info(f"Deleted {deleted_count} old relationships")
            if deleted_count < len(old_records):
                warnings.append(f"{plural(len(old_records) - deleted_count, 'record')} of the previous rule group {old_rg_id} "
                                "could not be removed; delete it from Firewall Rules")

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
# pylint: disable-next=too-many-return-statements,too-many-locals,too-many-branches
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

        def _current_entry(item):
            # As this version deploys it: _sanitize_url_list adds *.domain for every plain domain
            # and drops dotless wildcards
            deployed = set(_sanitize_url_list(item.get('domain', ''), separator=';'))
            return next((c for c in candidates if c in deployed), None)

        def _legacy_entry(item):
            # As earlier versions deployed it: the raw entries, including wildcards without a dot
            # (*example.com), which Falcon matches against any name ending in "example.com"
            stored = {d.strip().lower() for d in item.get('domain', '').split(';') if d.strip()}
            return next((c for c in candidates if c in stored), None) or next(
                (d for d in sorted(stored)
                 if d.startswith('*') and not d.startswith('*.') and len(d) > 1 and fqdn.endswith(d[1:])), None)

        def _same_either_way(item):
            entry = _current_entry(item)
            return entry is not None and entry == _legacy_entry(item)

        # Early return: stop paging at a category that blocks the name however it was deployed.
        # The domain collection is read with read_all_objects' default limits.
        result = read_all_objects(custom_storage, 'domain', COLLECTION_DOMAIN_VER,
                                  stop_when=_same_either_way, logger=logger)
        if "error" in result:
            return Response(code=500, body={"error": "Failed to simulate"})

        def _blocked(item, rule):
            return Response(code=200, body={"found": True, "category": item.get('category'), "rule": rule,
                                            "message": f"Blocked by {item.get('category')}",
                                            "pagination": result["pagination"]})

        if result["match"]:
            return _blocked(result["match"], _current_entry(result["match"]))

        # Categories whose raw and sanitized entries match differently: the rules deployed for
        # them decide, so only their relationship records are read
        pending = []
        for item in result["resources"]:
            current, legacy = _current_entry(item), _legacy_entry(item)
            if item.get('category') and current != legacy:
                pending.append((item, current, legacy))
        if pending:
            names = {item['category'] for item, _, _ in pending}
            key_names = names | {category_key(name) for name in names}
            keys, err = _list_relationship_keys(custom_storage, logger)
            records, err = (None, err) if err else _read_relationships(
                custom_storage, keys, lambda parts: parts is None or parts[0] in key_names, logger)
            if err:
                return Response(code=500, body={"error": f"Failed to simulate: {err}"})
            formats = {}  # category -> formats of the rules deployed for it
            for record in records:
                if record.get('category_name') in names:
                    formats.setdefault(record['category_name'], set()).add(
                        'sanitized' if record.get('rule_format') == RULE_FORMAT_SANITIZED else 'raw')
            for item, current, legacy in pending:
                deployed = formats.get(item['category'], set())
                # A category not deployed yet is checked as this version would deploy it
                rule = current if not deployed or 'sanitized' in deployed else None
                if rule is None and 'raw' in deployed:
                    rule = legacy
                if rule:
                    return _blocked(item, rule)

        # "Not blocked" would be wrong if one of the unread categories blocks the name
        if result["failed"]:
            unread = plural(result['failed'], 'category', 'categories')
            return Response(code=500, body={"error": f"Failed to simulate: {unread} could not be read"})
        if result["pagination"]["truncated"]:
            read = plural(result['pagination']['returned'], 'category', 'categories')
            return Response(code=500, body={"error": f"Failed to simulate: only the first {read} could be read"})
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
# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
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
        # A policy whose records could not be read would be missing from the report
        if result["failed"]:
            return Response(code=500, body={
                "error": f"Failed to read relationships: {plural(result['failed'], 'record')} could not be read"})

        # One entry per policy: keyed by policy_id, or by name for legacy records without it
        unique_policies = {}
        for item in result['resources']:
            if not isinstance(item, dict):
                continue
            policy_name = item.get('policy_name')
            if not policy_name:
                continue
            unique_policies.setdefault(item.get('policy_id') or f"name:{policy_name}", item)

        # Legacy records (no policy_id): resolve by name in batches, with the same matching rule
        # as update-policy and delete-policy
        legacy_names = [item['policy_name'] for key, item in unique_policies.items() if key.startswith("name:")]
        found_by_name, err = _find_policies_by_names(fw_policies, legacy_names, logger)
        if err:
            return Response(code=502, body={"error": f"Failed to look up policies in Falcon: {err}"})
        candidate_ids = list(dict.fromkeys(p.get('id') for found in found_by_name.values() for p in found))
        legacy_containers, err = _get_by_ids(mgmt.get_policy_containers, candidate_ids, 'policy_id',
                                             "get_policy_containers", logger)
        if err:
            return Response(code=502, body={"error": f"Failed to read policy containers from Falcon: {err}"})
        records = [item for item in result['resources'] if isinstance(item, dict)]
        tracked_rule_groups = _tracked_rule_groups([r['_key'] for r in records if r.get('_key')], records)
        resolved, unresolved = {}, {}  # key -> policy_id, key -> why it could not be resolved
        for key, item in unique_policies.items():
            if key.startswith("name:"):
                policy, unresolved[key] = _match_legacy_policy(
                    found_by_name.get(item['policy_name'], []), legacy_containers, item.get('rule_group_id'),
                    item.get('platform'), item.get('host_group_id'), tracked_rule_groups)
                resolved[key] = policy.get('id') if policy else None
            else:
                resolved[key] = key

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
                pol_info["issues"].append(unresolved.get(key) or "Policy not found in Falcon")
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

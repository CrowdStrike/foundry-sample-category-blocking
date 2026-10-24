"""Helpers for Custom Storage access, request parsing, validation and firewall rule building."""

# Handlers deliberately catch every exception to log it and return a 500 response.
# pylint: disable=broad-exception-caught

import json
import re
from concurrent.futures import ThreadPoolExecutor

def category_key(category_name: str) -> str:
    """
    Deterministic Custom Storage key for a category. Case is preserved so keys created by
    earlier versions (e.g. 'AI_Applications') keep working; only characters other than
    letters, digits and '_' (spaces included) become '_'.
    """
    return re.sub(r'[^A-Za-z0-9_]', '_', category_name.strip())


def relationship_key(category_name: str, rule_group_id: str, host_group_id: str) -> str:
    """Generate deterministic Custom Storage key for a relationship."""
    return f"{category_key(category_name)}_{rule_group_id}_{host_group_id}"


def validate_fqdn(fqdn: str) -> bool:
    """Validate that a string looks like a valid FQDN or wildcard FQDN."""
    pattern = r'^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, fqdn.strip()))


def _validate_falcon_response(response, operation_name: str, logger=None):
    """Validate a FalconPy response. Returns (success: bool, error_message: str | None)."""
    status = response.get("status_code", 0) if isinstance(response, dict) else 0
    if status in (200, 201, 202, 204):
        return True, None

    body = response.get("body") if isinstance(response, dict) else None
    errors = (body.get("errors") if isinstance(body, dict) else None) or []
    if errors and isinstance(errors[0], dict):
        error_msg = errors[0].get("message", "Unknown error from CrowdStrike")
    else:
        error_msg = f"CrowdStrike API returned status {status}"

    if logger:
        if 400 <= status < 500:
            logger.warning(f"{operation_name} failed ({status}): {error_msg}")
        else:
            logger.error(f"{operation_name} failed ({status}): {error_msg}")

    return False, error_msg


def query_param(request, name: str, default: str = '') -> str:
    """
    Read a query-string parameter. The Foundry SDK delivers them as
    request.params.query = {"name": ["value", ...]}; the first value is returned.
    """
    params = getattr(request, 'params', None)
    query = params.get('query') if isinstance(params, dict) else getattr(params, 'query', None)
    if not isinstance(query, dict):
        return default
    value = query.get(name)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return default if value is None else str(value)


_USERNAME_FIELDS = ('username', 'user_name', 'email', 'user_email', 'user_id', 'user_uuid', 'uuid')


def _get_username(request) -> str:
    """
    Authenticated user from the Foundry request context (never from the request body).
    The handler's second argument is the static app config and never carries the user.
    """
    context = getattr(request, 'context', None)
    if not isinstance(context, dict):
        return 'unknown'
    for container in (context.get('user'), context.get('user_info'), context):
        if isinstance(container, dict):
            for field in _USERNAME_FIELDS:
                value = container.get(field)
                if value:
                    return str(value)
    return 'unknown'


def resolve_creator(request, body_field: str = 'username'):
    """
    Who performed the action, as (name, source):
      - ("<user>", "context") when the Foundry request context identifies the user;
      - ("<user>", "ui") otherwise, from the username the UI sends (Falcon session user;
        not verified server-side, hence the recorded source);
      - ("unknown", "none") when neither is available.
    """
    name = _get_username(request)
    if name != 'unknown':
        return name, 'context'
    body = getattr(request, 'body', None)
    value = body.get(body_field) if isinstance(body, dict) else None
    if isinstance(value, str) and value.strip() and value.strip().lower() != 'unknown':
        return value.strip(), 'ui'
    return 'unknown', 'none'


def _sanitize_url(url: str) -> str:
    """Strip whitespace, http(s):// protocol prefixes and trailing slashes."""
    url = url.strip().lower()
    url = re.sub(r'^https?://', '', url)
    url = url.rstrip('/')
    return url

def _sanitize_url_list(raw: str, separator: str = ';') -> list:
    """
    Split a separator-delimited URL string, sanitize each entry, drop entries
    that are not valid FQDNs and auto-generate *.domain wildcard variants.
    """
    seen: set = set()
    result: list = []
    for part in raw.split(separator):
        clean = _sanitize_url(part)
        if not clean or not validate_fqdn(clean):
            continue
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
        # Auto-add wildcard only for non-wildcard entries (*.domain.com)
        if not clean.startswith('*'):
            wildcard = f'*.{clean}'
            if wildcard not in seen:
                seen.add(wildcard)
                result.append(wildcard)
    return result

def _build_rule(name: str, action: str, fqdn: str, temp_id: str,
                description: str = "") -> dict:
    """Build a single firewall rule dict for use in create_rule_group."""
    return {
        "action": action,
        "address_family": "NONE",
        "description": description or f"Rule: {name}",
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
        "fqdn": fqdn,
        "icmp": {"icmp_code": "", "icmp_type": ""},
        "local_address": [{"address": "*", "netmask": 0}],
        "log": False,
        "monitor": {"count": "1", "period_ms": "1000000"},
        "name": name,
        "protocol": "*",
        "remote_address": [{"address": "*", "netmask": 0}],
        "temp_id": temp_id
    }


# ---------------------------------------------------------------------------
# Custom Storage access
#
# SearchObjects/SearchObjectsByVersion only return object METADATA (and require
# an FQL filter), so collections are read by listing keys with
# ListObjectsByVersion (paged with the `start` key cursor) and fetching each
# object with GetVersionedObject. FalconPy wraps JSON responses as
# {"status_code", "headers", "body": {...}}.
# ---------------------------------------------------------------------------

class StorageError(Exception):
    """A Custom Storage call returned an error."""


def _iter_key_pages(custom_storage, collection_name, collection_version, page_size, max_pages, state):
    """Yield pages of object keys. Fills `state` with pagination info (or 'error')."""
    seen: set = set()
    start = None
    state.update(pages_fetched=0, returned=0, has_more=False)
    while state["pages_fetched"] < max_pages:
        kwargs = {"collection_name": collection_name, "collection_version": collection_version,
                  "limit": page_size}
        if start:
            kwargs["start"] = start
        resp = custom_storage.ListObjectsByVersion(**kwargs)
        if not isinstance(resp, dict) or resp.get("status_code") != 200:
            state["error"] = resp
            return
        state["pages_fetched"] += 1

        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        raw = []
        for item in body.get("resources") or []:
            key = item if isinstance(item, str) else (
                item.get("key") or item.get("object_key") if isinstance(item, dict) else None)
            if key:
                raw.append(key)

        # `start` may be inclusive (or ignored): only keys not seen before count
        new = [k for k in raw if k not in seen]
        seen.update(new)
        state["returned"] += len(new)
        state["has_more"] = len(raw) >= page_size and bool(new)
        if new:
            yield new
        if not state["has_more"]:
            return
        start = raw[-1]


def _pagination(state, page_size):
    return {
        "page_size": page_size,
        "pages_fetched": state["pages_fetched"],
        "returned": state["returned"],
        "has_more": state["has_more"],
        "truncated": state["has_more"],
    }


def list_object_keys(custom_storage, collection_name: str, collection_version: str,
                     page_size: int = 200, max_pages: int = 50) -> dict:
    """All object keys of a collection: {"keys", "pagination"} or {"error"}."""
    state: dict = {}
    keys = [k for page in _iter_key_pages(custom_storage, collection_name, collection_version,
                                          page_size, max_pages, state) for k in page]
    if "error" in state:
        return {"error": state["error"]}
    return {"keys": keys, "pagination": _pagination(state, page_size)}


def parse_object_response(resp):
    """
    Decode a GetVersionedObject response: raw bytes, or a FalconPy dict whose body is
    the object (JSON content type) or bytes. Returns the object, None when it does
    not exist (404), or raises StorageError.
    """
    if isinstance(resp, (bytes, bytearray)):
        return json.loads(resp.decode("utf-8"))
    if isinstance(resp, dict):
        status = resp.get("status_code")
        if status == 404:
            return None
        if status != 200:
            raise StorageError(f"HTTP {status}: {resp.get('body')}")
        body = resp.get("body")
        if isinstance(body, (bytes, bytearray)):
            return json.loads(body.decode("utf-8"))
        if isinstance(body, dict):
            return body
    raise StorageError(f"Unexpected response type: {type(resp).__name__}")


def get_object(custom_storage, collection_name: str, collection_version: str, object_key: str):
    """Fetch one object (dict), or None if it does not exist. Raises StorageError."""
    resp = custom_storage.GetVersionedObject(collection_name=collection_name,
                                             collection_version=collection_version,
                                             object_key=object_key)
    return parse_object_response(resp)


def delete_object(custom_storage, collection_name: str, collection_version: str, object_key: str) -> bool:
    """Delete one object; True on success."""
    resp = custom_storage.DeleteVersionedObject(collection_name=collection_name,
                                                collection_version=collection_version,
                                                object_key=object_key)
    return isinstance(resp, dict) and resp.get("status_code") in (200, 204)


# pylint: disable-next=too-many-locals
def read_all_objects(custom_storage, collection_name: str, collection_version: str,
                     page_size: int = 200, max_pages: int = 50, max_workers: int = 10,
                     stop_when=None, logger=None) -> dict:
    """
    Read every object of a collection (each gets its key in `_key`).

    `stop_when(item)` (optional) ends the scan at the first matching item, returned in `match`.
    Returns {"resources", "match", "failed", "pagination"} or {"error"}.
    """
    state: dict = {}
    resources: list = []
    match = None
    failed = 0

    def _fetch(key):
        obj = get_object(custom_storage, collection_name, collection_version, key)
        if isinstance(obj, dict):
            obj = dict(obj)
            obj["_key"] = key
        return obj

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for keys in _iter_key_pages(custom_storage, collection_name, collection_version,
                                    page_size, max_pages, state):
            futures = [(k, executor.submit(_fetch, k)) for k in keys]
            page = []
            for key, future in futures:
                try:
                    obj = future.result()
                except Exception as e:
                    failed += 1
                    if logger:
                        logger.warning(f"Could not read {collection_name}/{key}: {e}")
                    continue
                if isinstance(obj, dict):
                    page.append(obj)
            resources.extend(page)
            if stop_when:
                match = next((r for r in page if stop_when(r)), None)
                if match is not None:
                    break

    if "error" in state:
        return {"error": state["error"]}
    pagination = _pagination(state, page_size)
    if match is not None:
        pagination["has_more"] = pagination["truncated"] = False
    return {"resources": resources, "match": match, "failed": failed, "pagination": pagination}

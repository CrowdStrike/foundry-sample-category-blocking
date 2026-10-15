"""Pytest bootstrap: stub the Foundry runtime and FalconPy so tests run without a tenant.

- The request/response models are the REAL ones from crowdstrike-foundry-function when it
  is installed (so query params arrive as request.params.query = {"name": ["value"]}, etc.).
  A faithful copy is used otherwise. Only `Function` is replaced, so `FUNC.handler(...)`
  decorators are identity functions and handlers stay directly callable.
- `FakeStorage` emulates the FalconPy CustomStorage versioned methods with the real
  response shapes: {"status_code", "headers", "body": {...}} and raw bytes for objects.
"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name

import json
import os
import sys
import types
from dataclasses import dataclass, field
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from crowdstrike.foundry.function.model import APIError, Request, RequestParams, Response
except ImportError:
    @dataclass
    class RequestParams:
        header: Dict[str, List[str]] = field(default_factory=dict)
        query: Dict[str, List[str]] = field(default_factory=dict)

    @dataclass
    class APIError:
        code: int = 0
        message: str = ''

    @dataclass
    class Request:
        access_token: str = ''
        body: dict = field(default_factory=dict)
        context: dict = field(default_factory=dict)
        fn_id: str = ''
        fn_version: int = 0
        method: str = ''
        params: RequestParams = field(default_factory=RequestParams)
        trace_id: str = ''
        url: str = ''

    @dataclass
    class Response:
        body: dict = field(default_factory=dict)
        code: int = 0
        errors: List[APIError] = field(default_factory=list)
        header: Dict[str, List[str]] = field(default_factory=dict)


class _Function:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def handler(self, *_args, **_kwargs):
        return lambda func: func

    def run(self):
        pass


def _install_stubs():
    foundry = types.ModuleType("crowdstrike.foundry.function")
    foundry.Function = _Function
    foundry.Request = Request
    foundry.RequestParams = RequestParams
    foundry.Response = Response
    foundry.APIError = APIError

    sys.modules.setdefault("crowdstrike", types.ModuleType("crowdstrike"))
    sys.modules.setdefault("crowdstrike.foundry", types.ModuleType("crowdstrike.foundry"))
    sys.modules["crowdstrike.foundry.function"] = foundry

    falconpy = types.ModuleType("falconpy")
    for name in ("CustomStorage", "FirewallManagement", "FirewallPolicies", "HostGroup"):
        setattr(falconpy, name, type(name, (), {"__init__": lambda self, **kw: None}))
    sys.modules["falconpy"] = falconpy


_install_stubs()


def falcon_response(status_code=200, resources=None, errors=None, body=None):
    """A FalconPy-shaped JSON response."""
    if body is None:
        body = {"meta": {}, "resources": resources or [], "errors": errors or []}
    return {"status_code": status_code, "headers": {}, "body": body}


class FakeStorage:
    """
    In-memory Custom Storage with FalconPy's versioned API.

    ListObjectsByVersion lists keys alphabetically with an INCLUSIVE `start` cursor;
    GetVersionedObject returns raw bytes (or the JSON-wrapped dict if json_objects=True).
    Failures can be injected per key.
    """

    def __init__(self, data=None, json_objects=False):
        # {(collection, version): {key: obj}}
        self.data = {}
        for (collection, version), objects in (data or {}).items():
            self.data[(collection, version)] = {k: dict(v) for k, v in objects.items()}
        self.json_objects = json_objects
        self.fail_get, self.fail_put, self.fail_delete = set(), set(), set()
        self.list_status = 200
        self.calls = []

    def objects(self, collection, version):
        return self.data.setdefault((collection, version), {})

    def ListObjectsByVersion(self, collection_name, collection_version, limit=50, start=None, **_):
        self.calls.append(("list", collection_name, start))
        if self.list_status != 200:
            return falcon_response(self.list_status, errors=[{"message": "boom"}])
        keys = sorted(self.objects(collection_name, collection_version))
        if start:
            keys = [k for k in keys if k >= start]
        return falcon_response(resources=keys[:limit])

    def GetVersionedObject(self, collection_name, collection_version, object_key, **_):
        self.calls.append(("get", collection_name, object_key))
        if object_key in self.fail_get:
            return falcon_response(500, errors=[{"message": "boom"}])
        obj = self.objects(collection_name, collection_version).get(object_key)
        if obj is None:
            return falcon_response(404, errors=[{"message": "not found"}])
        if self.json_objects:
            return falcon_response(body=dict(obj))
        return json.dumps(obj).encode("utf-8")

    def PutObjectByVersion(self, body, collection_name, collection_version, object_key, **_):
        self.calls.append(("put", collection_name, object_key))
        if object_key in self.fail_put:
            return falcon_response(500, errors=[{"message": "boom"}])
        self.objects(collection_name, collection_version)[object_key] = dict(body)
        return falcon_response()

    def DeleteVersionedObject(self, collection_name, collection_version, object_key, **_):
        self.calls.append(("delete", collection_name, object_key))
        if object_key in self.fail_delete:
            return falcon_response(500, errors=[{"message": "boom"}])
        self.objects(collection_name, collection_version).pop(object_key, None)
        return falcon_response()

    def __getattr__(self, name):
        # Unversioned or metadata-only APIs must not be used by the handlers
        if name in ("SearchObjects", "SearchObjectsByVersion", "GetObject", "PutObject", "DeleteObject", "ListObjects"):
            raise AssertionError(f"Handlers must not call CustomStorage.{name}")
        raise AttributeError(name)

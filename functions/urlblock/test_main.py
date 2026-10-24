"""Tests for storage helpers, category/CSV handlers and the policy simulator.

Requests use the real Foundry request model (see conftest.py) and Custom Storage is the
in-memory FakeStorage, which answers with FalconPy's real response shapes.
"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name

import threading
import unittest
from unittest.mock import MagicMock, patch

from crowdstrike.foundry.function import Request, RequestParams

import main  # noqa: F401  # pylint: disable=unused-import  # registers all handlers
from app_utils import (
    list_object_keys, read_all_objects, parse_object_response, query_param, StorageError,
    _get_username, resolve_creator,
)
from conftest import FakeStorage, falcon_response
from handlers import categories, policies

DOMAIN = ("domain", "v2.0")
REL = ("relationship", "v5.0")


def req(body=None, query=None, context=None):
    return Request(body=body or {}, params=RequestParams(query={k: [v] for k, v in (query or {}).items()}),
                   context=context or {})


class HandlerTestCase(unittest.TestCase):
    module = None
    data = {}

    def setUp(self):
        self.logger = MagicMock()
        self.store = FakeStorage(self.data)
        p = patch.object(self.module, "get_client", return_value=self.store)
        p.start()
        self.addCleanup(p.stop)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class QueryParamTestCase(unittest.TestCase):
    def test_reads_first_value_of_sdk_query_lists(self):
        self.assertEqual(query_param(req(query={"fqdn": "a.com"}), "fqdn"), "a.com")

    def test_missing_param_returns_default(self):
        self.assertEqual(query_param(req(), "fqdn", "x"), "x")

    def test_accepts_dict_params(self):
        request = Request()
        request.params = {"query": {"limit": ["5"]}}
        self.assertEqual(query_param(request, "limit"), "5")


class UsernameTestCase(unittest.TestCase):
    def test_reads_user_from_request_context(self):
        self.assertEqual(_get_username(req(context={"user": {"username": "ana"}})), "ana")
        self.assertEqual(_get_username(req(context={"user_id": "u-1"})), "u-1")

    def test_unknown_without_context(self):
        self.assertEqual(_get_username(req()), "unknown")

    def test_resolve_creator_order(self):
        self.assertEqual(resolve_creator(req({"username": "x"}, context={"user_id": "u"})), ("u", "context"))
        self.assertEqual(resolve_creator(req({"username": " ana@x.com "})), ("ana@x.com", "ui"))
        self.assertEqual(resolve_creator(req({"username": "unknown"})), ("unknown", "none"))
        self.assertEqual(resolve_creator(req()), ("unknown", "none"))


class StorageHelpersTestCase(unittest.TestCase):
    def test_list_keys_pages_with_inclusive_start_cursor(self):
        store = FakeStorage({DOMAIN: {f"k{i:02d}": {} for i in range(5)}})
        result = list_object_keys(store, *DOMAIN, page_size=2)
        self.assertEqual(result["keys"], ["k00", "k01", "k02", "k03", "k04"])
        self.assertFalse(result["pagination"]["truncated"])

    def test_list_keys_truncated_at_max_pages(self):
        store = FakeStorage({DOMAIN: {f"k{i}": {} for i in range(10)}})
        result = list_object_keys(store, *DOMAIN, page_size=2, max_pages=2)
        self.assertTrue(result["pagination"]["truncated"])
        self.assertEqual(len(result["keys"]), 3)  # 2 + 1 new (cursor key repeated)

    def test_list_error(self):
        store = FakeStorage()
        store.list_status = 403
        self.assertIn("error", list_object_keys(store, *DOMAIN))

    def test_read_all_objects_returns_full_records_with_key(self):
        for json_objects in (False, True):
            store = FakeStorage({DOMAIN: {"Games": {"category": "Games", "domain": "a.com"}}},
                                json_objects=json_objects)
            result = read_all_objects(store, *DOMAIN)
            self.assertEqual(result["resources"], [{"category": "Games", "domain": "a.com", "_key": "Games"}])

    def test_read_all_counts_unreadable_objects(self):
        store = FakeStorage({DOMAIN: {"a": {"x": 1}, "b": {"x": 2}}})
        store.fail_get.add("b")
        result = read_all_objects(store, *DOMAIN)
        self.assertEqual(len(result["resources"]), 1)
        self.assertEqual(result["failed"], 1)

    def test_parse_object_response_shapes(self):
        self.assertEqual(parse_object_response(b'{"a": 1}'), {"a": 1})
        self.assertEqual(parse_object_response(falcon_response(body={"a": 1})), {"a": 1})
        self.assertIsNone(parse_object_response(falcon_response(404)))
        with self.assertRaises(StorageError):
            parse_object_response(falcon_response(500))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class ManageCategoryTestCase(HandlerTestCase):
    module = categories

    def test_success_writes_versioned_object(self):
        resp = categories.manage_category(req({"categoryName": "Games", "urls": "steam.com,epicgames.com"}), None, self.logger)
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.body["urlCount"], 4)
        obj = self.store.objects(*DOMAIN)["Games"]
        self.assertEqual(obj["domain"], "steam.com;*.steam.com;epicgames.com;*.epicgames.com")

    def test_missing_name_and_urls(self):
        self.assertEqual(categories.manage_category(req({"categoryName": "", "urls": "a.com"}), None, self.logger).code, 400)
        self.assertEqual(categories.manage_category(req({"categoryName": "G", "urls": ""}), None, self.logger).code, 400)

    def test_all_invalid_urls(self):
        self.assertEqual(categories.manage_category(req({"categoryName": "X", "urls": "nope"}), None, self.logger).code, 400)

    def test_put_error_returns_500(self):
        self.store.fail_put.add("Games")
        resp = categories.manage_category(req({"categoryName": "Games", "urls": "a.com"}), None, self.logger)
        self.assertEqual(resp.code, 500)


class CategoryCaseConflictTestCase(HandlerTestCase):
    module = categories
    data = {DOMAIN: {"AI_Apps": {"category": "AI Apps", "domain": "a.com"}}}

    def test_rejects_key_differing_only_by_case(self):
        resp = categories.manage_category(req({"categoryName": "ai apps", "urls": "b.com"}), None, self.logger)
        self.assertEqual(resp.code, 409)
        self.assertIn("AI_Apps", resp.body["error"])
        self.assertNotIn("ai_apps", self.store.objects(*DOMAIN))

    def test_updates_existing_exact_key(self):
        resp = categories.manage_category(req({"categoryName": "AI Apps", "urls": "b.com"}), None, self.logger)
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.store.objects(*DOMAIN)["AI_Apps"]["domain"], "b.com;*.b.com")


class ListCategoriesTestCase(HandlerTestCase):
    module = categories
    data = {DOMAIN: {
        "Games": {"category": "Games", "domain": "steam.com"},
        "AI_Apps": {"category": "AI Apps", "domain": "openai.com"},
    }}

    def test_returns_names_domains_and_pagination(self):
        resp = categories.list_categories(req(), None, self.logger)
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.body["categories"], ["AI Apps", "Games"])
        self.assertEqual(resp.body["total_items"], 2)
        self.assertEqual(resp.body["pagination"]["returned"], 2)
        self.assertFalse(resp.body["pagination"]["truncated"])

    def test_limit_query_param_is_used_and_capped(self):
        resp = categories.list_categories(req(query={"limit": "9999"}), None, self.logger)
        self.assertEqual(resp.body["pagination"]["page_size"], 500)
        resp = categories.list_categories(req(query={"limit": "1"}), None, self.logger)
        self.assertEqual(resp.body["pagination"]["page_size"], 1)
        self.assertEqual(resp.body["metadata"]["limit"], 1)

    def test_api_error_returns_500(self):
        self.store.list_status = 403
        resp = categories.list_categories(req(), None, self.logger)
        self.assertEqual(resp.code, 500)


class SearchCategoriesTestCase(HandlerTestCase):
    module = categories
    data = {DOMAIN: {"AI_Apps": {"category": "AI Apps", "domain": "openai.com"}}}

    def test_finds_by_name_from_query(self):
        resp = categories.search_categories(req(query={"category": "AI Apps"}), None, self.logger)
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.body["domain"], "openai.com")

    def test_not_found_and_missing_param(self):
        self.assertEqual(categories.search_categories(req(query={"category": "Nope"}), None, self.logger).code, 404)
        self.assertEqual(categories.search_categories(req(), None, self.logger).code, 400)


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

class ImportCsvTestCase(HandlerTestCase):
    module = categories
    data = {DOMAIN: {"AI_Applications": {"category": "AI Applications", "domain": "x.com"}}}

    def run_csv(self, text):
        return categories.import_csv_handler(req({"csv": text}), None, self.logger)

    def test_requires_csv(self):
        self.assertEqual(categories.import_csv_handler(req({}), None, self.logger).code, 400)

    def test_one_row_per_domain_is_merged_per_category(self):
        resp = self.run_csv("category,url\nGames,steam.com\nGames,epicgames.com\nNews,bbc.com\nGames,steam.com\n")
        self.assertEqual(resp.code, 200)
        self.assertEqual((resp.body["total_rows"], resp.body["successful_imports"], resp.body["failed_imports"]), (4, 2, 0))
        self.assertEqual(self.store.objects(*DOMAIN)["Games"]["domain"].split(";"),
                         ["steam.com", "*.steam.com", "epicgames.com", "*.epicgames.com"])
        self.assertEqual(resp.body["domains_imported"], 6)

    def test_invalid_rows_and_case_conflicts_are_counted(self):
        resp = self.run_csv("Games,steam.com\nGames,not a domain\n,x.com\nShort\n"
                            "ai applications,b.com\nAI_Applications,c.com\n")
        self.assertEqual(resp.body["successful_imports"], 2)   # Games + AI_Applications
        self.assertEqual(resp.body["failed_imports"], 3)       # bad domain, empty category, case conflict
        self.assertNotIn("ai_applications", self.store.objects(*DOMAIN))
        self.assertEqual(self.store.objects(*DOMAIN)["AI_Applications"]["domain"], "c.com;*.c.com")

    def test_write_failures_are_counted(self):
        self.store.fail_put.add("News")
        resp = self.run_csv("category,url\nGames,steam.com\nNews,bbc.com\n")
        self.assertEqual((resp.body["successful_imports"], resp.body["failed_imports"]), (1, 1))
        self.assertTrue(any("News" in str(c) for c in self.logger.error.call_args_list))

    def test_writes_run_concurrently(self):
        barrier = threading.Barrier(2, timeout=5)
        original_put = self.store.PutObjectByVersion

        def put(**kw):
            barrier.wait()  # only completes if two writes run at the same time
            return original_put(**kw)

        self.store.PutObjectByVersion = put
        resp = self.run_csv("category,url\nGames,steam.com\nNews,bbc.com\n")
        self.assertEqual(resp.body["successful_imports"], 2)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class SimulatePolicyTestCase(HandlerTestCase):
    module = policies
    data = {DOMAIN: {
        "Search": {"category": "Search", "domain": "google.com;*.google.com"},
        "Games": {"category": "Games", "domain": "steam.com"},
        "Trading": {"category": "Trading", "domain": "tradingview.com;*tradingview.com"},
    }}

    def simulate(self, fqdn):
        return policies.simulate_policy(req(query={"fqdn": fqdn}), None, self.logger)

    def test_reads_fqdn_from_query(self):
        resp = self.simulate("google.com")
        self.assertEqual(resp.code, 200)
        self.assertTrue(resp.body["found"])
        self.assertEqual(resp.body["category"], "Search")

    def test_subdomain_matches_parent_wildcard(self):
        resp = self.simulate("Mail.Google.com")
        self.assertTrue(resp.body["found"])
        self.assertEqual(resp.body["rule"], "*.google.com")

    def test_subdomain_matches_wildcard_added_at_deployment(self):
        # deployment runs "steam.com" through _sanitize_url_list, which adds "*.steam.com"
        resp = self.simulate("store.steam.com")
        self.assertTrue(resp.body["found"])
        self.assertEqual((resp.body["category"], resp.body["rule"]), ("Games", "*.steam.com"))
        self.assertFalse(self.simulate("notsteam.com").body["found"])

    def deploy_trading(self, policy_id):
        """A relationship record for Trading, as written by this version (policy_id) or an earlier one."""
        record = {"category_name": "Trading", "rule_group_id": "rg"}
        if policy_id:
            record["policy_id"] = policy_id
        self.store.objects(*REL)["Trading_rg_hg"] = record

    def test_legacy_wildcard_without_dot_matches_names_in_legacy_policies(self):
        self.deploy_trading(policy_id=None)
        resp = self.simulate("evil-tradingview.com")
        self.assertTrue(resp.body["found"])
        self.assertEqual((resp.body["category"], resp.body["rule"]), ("Trading", "*tradingview.com"))
        self.assertEqual(self.simulate("tradingview.com").body["rule"], "tradingview.com")  # exact entry wins

    def test_legacy_wildcard_is_ignored_when_deployed_by_this_version(self):
        # _sanitize_url_list drops "*tradingview.com" and adds "*.tradingview.com" for the plain domain
        self.deploy_trading(policy_id="pol-1")
        self.assertFalse(self.simulate("evil-tradingview.com").body["found"])
        self.assertEqual(self.simulate("www.tradingview.com").body["rule"], "*.tradingview.com")

    def test_category_deployed_only_by_legacy_policy_uses_raw_entries(self):
        # earlier versions deployed "steam.com" as is, without the "*.steam.com" this version adds
        self.store.objects(*REL)["Games_rg_hg"] = {"category_name": "Games", "rule_group_id": "rg"}
        self.assertFalse(self.simulate("store.steam.com").body["found"])
        self.assertEqual(self.simulate("steam.com").body["rule"], "steam.com")

        self.store.objects(*REL)["Games_rg2_hg"] = {"category_name": "Games", "rule_group_id": "rg2",
                                                    "policy_id": "pol-1"}
        self.assertEqual(self.simulate("store.steam.com").body["rule"], "*.steam.com")

    def test_relationship_read_error(self):
        self.store.list_status_by_collection["relationship"] = 500
        self.assertEqual(self.simulate("evil-tradingview.com").code, 500)

    def test_unrelated_and_invalid(self):
        self.assertFalse(self.simulate("example.org").body["found"])
        self.assertEqual(self.simulate("not a domain").code, 400)
        self.assertEqual(policies.simulate_policy(req(), None, self.logger).code, 400)

    def test_candidates_never_include_bare_tld(self):
        self.assertEqual(policies._blocking_candidates(  # pylint: disable=protected-access
            "a.b.com"), ["a.b.com", "*.a.b.com", "*.b.com"])


if __name__ == "__main__":
    unittest.main()

"""Tests for storage helpers, category/CSV handlers and the policy simulator.

Requests use the real Foundry request model (see conftest.py) and Custom Storage is the
in-memory FakeStorage, which answers with FalconPy's real response shapes.
"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name,too-many-public-methods

import threading
import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from crowdstrike.foundry.function import Request, RequestParams

import main  # noqa: F401  # pylint: disable=unused-import  # registers all handlers
import app_utils
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

    def test_read_all_objects_reads_each_page_with_read_objects(self):
        store = FakeStorage({DOMAIN: {"a": {"x": 1}, "b": {"x": 2}, "c": {"x": 3}}})
        store.fail_get.add("b")
        with patch.object(app_utils, "read_objects", wraps=app_utils.read_objects) as read:
            result = read_all_objects(store, *DOMAIN, page_size=2)  # pages [a, b] and [c]
        self.assertEqual([c.args[3] for c in read.call_args_list], [["a", "b"], ["c"]])
        self.assertEqual(([r["_key"] for r in result["resources"]], result["failed"]), (["a", "c"], 1))

    def test_read_all_objects_uses_one_thread_pool_for_every_page(self):
        store = FakeStorage({DOMAIN: {k: {"x": k} for k in "abcde"}})
        with patch.object(app_utils, "ThreadPoolExecutor", wraps=app_utils.ThreadPoolExecutor) as pool, \
                patch.object(app_utils, "read_objects", wraps=app_utils.read_objects) as read:
            result = read_all_objects(store, *DOMAIN, page_size=2)  # the start cursor is inclusive:
        self.assertEqual(len(result["resources"]), 5)              # new keys [a, b], [c], [d], [e]
        self.assertEqual(read.call_count, 4)
        pool.assert_called_once_with(max_workers=10)
        executors = {id(c.kwargs["executor"]) for c in read.call_args_list}
        self.assertEqual(len(executors), 1)  # the same pool for every page

    def test_read_objects_creates_its_own_thread_pool_when_not_given_one(self):
        store = FakeStorage({DOMAIN: {"a": {"x": 1}, "b": {"x": 2}}})
        with patch.object(app_utils, "ThreadPoolExecutor", wraps=app_utils.ThreadPoolExecutor) as pool:
            objects, failed = app_utils.read_objects(store, *DOMAIN, ["a", "b"], max_workers=3)
        self.assertEqual(([o["_key"] for o in objects], failed), (["a", "b"], []))
        pool.assert_called_once_with(max_workers=3)

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

    def setUp(self):
        super().setUp()
        # Falcon: every rule group is held by a policy, unless self.rule_group_changes says otherwise.
        # get_rule_groups keeps returning a deleted rule group, with deleted: true
        self.rule_group_changes = {}
        self.mgmt = MagicMock()
        self.mgmt.get_rule_groups.side_effect = lambda ids: falcon_response(resources=[
            dict({"id": i, "enabled": True, "deleted": False, "platform": "windows", "policy_ids": ["pol-1"]},
                 **self.rule_group_changes.get(i, {})) for i in ids])
        clients = {"CustomStorage": self.store, "FirewallManagement": self.mgmt}
        p = patch.object(policies, "get_client", side_effect=lambda cls: clients[cls.__name__])
        self.get_client = p.start()
        self.addCleanup(p.stop)

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

    def deploy(self, category, sanitized, rule_group="rg"):
        """A relationship record, as written by this version (rule_format) or an earlier one."""
        record = {"category_name": category, "rule_group_id": rule_group, "host_group_id": "hg",
                  "policy_id": "pol-1"}  # a legacy record gets a policy_id once resolved by name
        if sanitized:
            record["rule_format"] = "sanitized"
        key = f"{category.replace(' ', '_')}_{rule_group}_hg"
        self.store.objects(*REL)[key] = record
        return key

    def deploy_trading(self, policy_id):
        self.deploy("Trading", sanitized=bool(policy_id))

    def relationship_listed(self):
        return any(c[:2] == ("list", "relationship") for c in self.store.calls)

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
        self.deploy("Games", sanitized=False)
        self.assertFalse(self.simulate("store.steam.com").body["found"])
        self.assertEqual(self.simulate("steam.com").body["rule"], "steam.com")

        self.deploy("Games", sanitized=True, rule_group="rg2")
        self.assertEqual(self.simulate("store.steam.com").body["rule"], "*.steam.com")

    def test_keys_of_another_shape_are_read_once_per_simulation(self):
        # both Facebook (deployed raw) and "Fb Mirror" need their format: the key that cannot be
        # attributed by name is read for the first one only
        self.store.objects(*DOMAIN)["Facebook"] = {"category": "Facebook", "domain": "facebook.com"}
        self.store.objects(*DOMAIN)["Fb_Mirror"] = {"category": "Fb Mirror", "domain": "facebook.com"}
        fb_key = self.deploy("Facebook", sanitized=False)
        self.store.objects(*REL)["unshaped"] = {"category_name": "Other", "rule_group_id": "rg2"}
        resp = self.simulate_by_pages_of_two("www.facebook.com")
        self.assertEqual(resp.body["category"], "Fb Mirror")
        self.assertEqual(sorted(c[2] for c in self.calls("get", "relationship")), [fb_key, "unshaped"])

    def assert_checked_as_this_version_deploys_it(self):
        resp = self.simulate("store.steam.com")
        self.assertEqual((resp.body["found"], resp.body["message"], resp.body["rule"]),
                         (True, "Blocked by Games", "*.steam.com"))
        self.mgmt.get_rule_groups.assert_called_once_with(ids=["rg-gone"])

    def test_records_of_a_deleted_rule_group_do_not_count_as_deployed(self):
        # delete-policy deleted the legacy rule group, then one of its records could not be removed:
        # Games is no longer deployed, so it is checked as this version would deploy it
        self.deploy("Games", sanitized=False, rule_group="rg-gone")
        # as Falcon returns it once deleted (soft delete), and with its policy_ids still listed
        for changes in ({"enabled": False, "deleted": True, "policy_ids": []}, {"deleted": True}):
            with self.subTest(changes=changes):
                self.rule_group_changes["rg-gone"] = changes
                self.mgmt.get_rule_groups.reset_mock()
                self.assert_checked_as_this_version_deploys_it()

    def test_records_of_a_rule_group_whose_policy_was_deleted_do_not_count_as_deployed(self):
        # delete-policy deleted the policy but not its rule group, which no policy holds any more
        self.deploy("Games", sanitized=False, rule_group="rg-gone")
        self.rule_group_changes["rg-gone"] = {"policy_ids": []}
        self.assert_checked_as_this_version_deploys_it()

    def test_records_of_a_rule_group_that_is_gone_do_not_count_as_deployed(self):
        self.deploy("Games", sanitized=False, rule_group="rg-gone")
        self.mgmt.get_rule_groups.side_effect = lambda ids: falcon_response(404, errors=[{"message": "not found"}])
        self.assert_checked_as_this_version_deploys_it()

    def test_records_of_a_rule_group_held_by_a_policy_count_as_deployed(self):
        self.deploy("Games", sanitized=False, rule_group="rg-live")
        resp = self.simulate("store.steam.com")
        self.assertEqual((resp.body["found"], resp.body["message"]), (False, "Not blocked"))
        self.mgmt.get_rule_groups.assert_called_once_with(ids=["rg-live"])

    def test_only_records_of_deployed_rule_groups_count(self):
        self.deploy("Games", sanitized=True, rule_group="rg-gone")
        self.deploy("Games", sanitized=False, rule_group="rg-live")
        self.rule_group_changes["rg-gone"] = {"enabled": False, "deleted": True, "policy_ids": []}
        self.assertFalse(self.simulate("store.steam.com").body["found"])  # only the raw "steam.com" is deployed
        self.mgmt.get_rule_groups.assert_called_once()
        self.assertEqual(sorted(self.mgmt.get_rule_groups.call_args.kwargs["ids"]), ["rg-gone", "rg-live"])

    def test_rule_group_read_error_leaves_the_result_incomplete(self):
        self.deploy("Games", sanitized=False)
        self.mgmt.get_rule_groups.side_effect = lambda ids: falcon_response(429, errors=[{"message": "slow"}])
        self.assert_not_confirmed(self.simulate("store.steam.com"), "whether Games blocks it could not be "
                                                                   "determined (Failed to read rule groups from Falcon: slow)")

    def test_relationships_are_not_read_when_the_format_cannot_matter(self):
        self.assertTrue(self.simulate("google.com").body["found"])  # same entry raw and sanitized
        self.assertFalse(self.simulate("example.org").body["found"])  # no entry either way
        self.assertFalse(self.relationship_listed())
        self.simulate("store.steam.com")  # only *.steam.com, added at deployment, matches
        self.assertTrue(self.relationship_listed())

    def calls(self, kind, collection):
        return [c for c in self.store.calls if c[:2] == (kind, collection)]

    def simulate_by_pages_of_two(self, fqdn):
        with patch.object(policies, "read_all_objects", partial(read_all_objects, page_size=2)):
            return self.simulate(fqdn)

    def test_scan_stops_at_the_first_category_that_blocks_with_its_deployed_format(self):
        # www.facebook.com only matches "*.facebook.com", which this version adds at deployment: the
        # format of Facebook decides, and is resolved as soon as Facebook is read
        self.store.objects(*DOMAIN)["Facebook"] = {"category": "Facebook", "domain": "facebook.com"}
        fb_key = self.deploy("Facebook", sanitized=True)
        self.deploy("Search", sanitized=False)
        resp = self.simulate_by_pages_of_two("www.facebook.com")
        self.assertEqual((resp.body["category"], resp.body["rule"]), ("Facebook", "*.facebook.com"))
        self.assertEqual(len(self.calls("list", "domain")), 1)  # first page: Facebook, Games
        self.assertEqual([c[2] for c in self.calls("get", "domain")], ["Facebook", "Games"])
        self.assertEqual(len(self.calls("list", "relationship")), 1)
        self.assertEqual([c[2] for c in self.calls("get", "relationship")], [fb_key])
        self.mgmt.get_rule_groups.assert_called_once_with(ids=["rg"])

    def test_relationships_are_listed_once_per_simulation(self):
        # Facebook only deployed raw ("facebook.com" alone): the scan goes on to "Fb Mirror", not deployed
        self.store.objects(*DOMAIN)["Facebook"] = {"category": "Facebook", "domain": "facebook.com"}
        self.store.objects(*DOMAIN)["Fb_Mirror"] = {"category": "Fb Mirror", "domain": "facebook.com"}
        fb_key = self.deploy("Facebook", sanitized=False)
        resp = self.simulate_by_pages_of_two("www.facebook.com")
        self.assertEqual((resp.body["category"], resp.body["rule"]), ("Fb Mirror", "*.facebook.com"))
        self.assertEqual(len(self.calls("list", "relationship")), 1)
        self.assertEqual([c[2] for c in self.calls("get", "relationship")], [fb_key])

    def test_format_of_a_category_is_resolved_once_per_simulation(self):
        # two domain objects of Facebook, deployed raw only: neither blocks www.facebook.com, so
        # the scan reaches both, and the second reuses the format resolved for the first
        for key in ("Facebook", "Facebook_old"):
            self.store.objects(*DOMAIN)[key] = {"category": "Facebook", "domain": "facebook.com"}
        fb_key = self.deploy("Facebook", sanitized=False)
        resp = self.simulate("www.facebook.com")
        self.assertEqual((resp.body["found"], resp.body["message"]), (False, "Not blocked"))
        self.assertEqual([c[2] for c in self.calls("get", "relationship")], [fb_key])
        self.mgmt.get_rule_groups.assert_called_once_with(ids=["rg"])
        self.assertEqual([c.args[0].__name__ for c in self.get_client.call_args_list].count("FirewallManagement"), 1)

    def assert_not_confirmed(self, resp, warning):
        """Nothing that could be checked blocks the name, but something could not be checked."""
        self.assertEqual((resp.code, resp.body["found"], resp.body["incomplete"]), (200, False, True))
        self.assertEqual(resp.body["warnings"], [warning])
        self.assertEqual(resp.body["message"], f"Not blocked by the categories that could be checked, but {warning}")

    def test_failed_read_of_a_relevant_relationship_leaves_the_result_incomplete(self):
        self.store.fail_get.add(self.deploy("Games", sanitized=False))
        self.assert_not_confirmed(self.simulate("store.steam.com"),
                                  "whether Games blocks it could not be determined (Some relationships could not be read)")

    def test_a_category_that_blocks_wins_over_an_undetermined_one(self):
        self.store.objects(*DOMAIN)["Mirror"] = {"category": "Mirror", "domain": "*.steam.com"}
        self.store.fail_get.add(self.deploy("Games", sanitized=False))
        resp = self.simulate("store.steam.com")  # Games is read first, and its format is unknown
        self.assertEqual((resp.code, resp.body["category"], resp.body["incomplete"]), (200, "Mirror", False))

    def test_failed_read_of_another_category_relationship_is_ignored(self):
        self.store.fail_get.add(self.deploy("Search", sanitized=False))
        resp = self.simulate("store.steam.com")  # Games is not deployed: checked as this version deploys it
        self.assertEqual((resp.code, resp.body["found"], resp.body["rule"]), (200, True, "*.steam.com"))
        self.assertNotIn(("get", "relationship", "Search_rg_hg"), self.store.calls)

    def test_category_names_that_prefix_each_other(self):
        # "Trading_rg_hg" belongs to Trading; "Trading_Tools_rg2_hg" to "Trading Tools", although it
        # also starts with "Trading_": its record is never read, and a failure to read it is ignored
        self.deploy("Trading", sanitized=True)
        tools_key = self.deploy("Trading Tools", sanitized=False, rule_group="rg2")
        self.assertFalse(self.simulate("evil-tradingview.com").body["found"])
        self.assertNotIn(("get", "relationship", tools_key), self.store.calls)

        self.store.fail_get.add(tools_key)
        resp = self.simulate("evil-tradingview.com")
        self.assertEqual((resp.code, resp.body["found"]), (200, False))

    def test_relationship_records_are_filtered_by_category(self):
        # a key of another shape cannot be attributed by name: it is read, and its record's
        # category decides whether it counts
        self.deploy("Trading", sanitized=True)
        self.store.objects(*REL)["unshaped"] = {"category_name": "Trading Tools", "rule_group_id": "rg2"}
        self.assertFalse(self.simulate("evil-tradingview.com").body["found"])
        self.assertIn(("get", "relationship", "unshaped"), self.store.calls)

    def test_failed_read_of_an_unattributable_key_leaves_the_result_incomplete(self):
        self.store.objects(*REL)["unshaped"] = {"category_name": "Search", "rule_group_id": "rg2"}
        self.store.fail_get.add("unshaped")
        self.assert_not_confirmed(self.simulate("store.steam.com"),
                                  "whether Games blocks it could not be determined (Some relationships could not be read)")

    def test_truncated_relationship_listing_leaves_the_result_incomplete(self):
        for category in ("Search", "Games", "Trading"):
            self.deploy(category, sanitized=True)
        with patch.object(policies, "RELATIONSHIP_PAGE_SIZE", 2), patch.object(policies, "RELATIONSHIP_MAX_PAGES", 1):
            resp = self.simulate("store.steam.com")
        self.assert_not_confirmed(resp, "whether Games blocks it could not be determined "
                                        "(There are more than 2 relationships, so they could not all be listed)")

    def test_relationship_listing_error_leaves_the_result_incomplete(self):
        self.store.list_status_by_collection["relationship"] = 500
        self.assert_not_confirmed(self.simulate("evil-tradingview.com"),
                                  "whether Trading blocks it could not be determined (Failed to read relationships)")

    def test_failed_category_read_leaves_the_result_incomplete(self):
        self.store.fail_get.add("Games")
        self.assert_not_confirmed(self.simulate("example.org"), "1 category could not be read")
        # a category that blocks the name is still reported, whatever could not be read
        resp = self.simulate("google.com")
        self.assertEqual((resp.body["category"], resp.body["incomplete"], resp.body["warnings"]), ("Search", False, []))
        self.store.fail_get.add("Trading")
        self.assert_not_confirmed(self.simulate("example.org"), "2 categories could not be read")

    def test_domain_listing_error_is_an_error(self):
        # no category could be read at all: there is no subset to report
        self.store.list_status_by_collection["domain"] = 500
        resp = self.simulate("google.com")
        self.assertEqual((resp.code, resp.body["error"]), (500, "Failed to simulate"))

    def simulate_first_category_only(self, fqdn):
        """
        Domain keys are listed alphabetically: with one key per page and one page, only Games is read.
        The simulator uses read_all_objects' default limits, which these arguments replace.
        """
        with patch.object(policies, "read_all_objects", partial(read_all_objects, page_size=1, max_pages=1)):
            return self.simulate(fqdn)

    def test_truncated_category_read_leaves_the_result_incomplete(self):
        self.assert_not_confirmed(self.simulate_first_category_only("example.org"),
                                  "only the first 1 category could be read")

    def test_truncated_category_read_still_reports_a_blocking_category(self):
        for fqdn, rule in (("steam.com", "steam.com"), ("store.steam.com", "*.steam.com")):
            resp = self.simulate_first_category_only(fqdn)
            self.assertEqual((resp.code, resp.body["category"], resp.body["rule"]), (200, "Games", rule))

    def test_unrelated_and_invalid(self):
        resp = self.simulate("example.org")
        self.assertEqual((resp.body["found"], resp.body["incomplete"], resp.body["message"]), (False, False, "Not blocked"))
        self.assertEqual(self.simulate("not a domain").code, 400)
        self.assertEqual(policies.simulate_policy(req(), None, self.logger).code, 400)

    def test_candidates_never_include_bare_tld(self):
        self.assertEqual(policies._blocking_candidates(  # pylint: disable=protected-access
            "a.b.com"), ["a.b.com", "*.a.b.com", "*.b.com"])


if __name__ == "__main__":
    unittest.main()

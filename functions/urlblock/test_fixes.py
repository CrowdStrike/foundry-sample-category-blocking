"""Tests for policy lifecycle (create/update/delete/list/health), helpers and analytics."""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name

import unittest
from unittest.mock import MagicMock, patch

from crowdstrike.foundry.function import Request, RequestParams

import main  # noqa: F401  # pylint: disable=unused-import
from app_utils import (
    category_key, relationship_key, validate_fqdn, _validate_falcon_response, _sanitize_url_list,
)
from conftest import FakeStorage
from handlers import analytics, policies

OK = {"status_code": 200}
REL = ("relationship", "v5.0")


def req(body=None, query=None, context=None):
    return Request(body=body or {}, params=RequestParams(query={k: [v] for k, v in (query or {}).items()}),
                   context=context or {})


def falcon_ok(resources):
    return {"status_code": 200, "body": {"resources": resources}}


class KeyHelpersTestCase(unittest.TestCase):
    def test_category_key_preserves_case(self):
        self.assertEqual(category_key(" Social Media "), "Social_Media")
        self.assertEqual(category_key("AI_Applications"), "AI_Applications")
        self.assertNotEqual(category_key("Games"), category_key("games"))

    def test_relationship_key(self):
        self.assertEqual(relationship_key("Social Media", "rg", "hg"), "Social_Media_rg_hg")

    def test_validate_fqdn(self):
        for good in ("a.com", "*.a.com", "sub-d.example.co.uk"):
            self.assertTrue(validate_fqdn(good), good)
        for bad in ("a", "-a.com", "a..com", "http://a.com"):
            self.assertFalse(validate_fqdn(bad), bad)

    def test_validate_falcon_response(self):
        self.assertEqual(_validate_falcon_response({"status_code": 201}, "op"), (True, None))
        ok, err = _validate_falcon_response(
            {"status_code": 409, "body": {"errors": [{"message": "duplicate name"}]}}, "op")
        self.assertEqual((ok, err), (False, "duplicate name"))
        self.assertIn("429", _validate_falcon_response({"status_code": 429}, "op")[1])

    def test_sanitize_url_list(self):
        self.assertEqual(_sanitize_url_list("https://A.com/; bad entry ;b.org;*.c.net;a.COM", separator=';'),
                         ["a.com", "*.a.com", "b.org", "*.b.org", "*.c.net"])
        self.assertEqual(_sanitize_url_list("nope;1.2.3.4", separator=';'), [])


class PolicyBase(unittest.TestCase):
    """Shared Falcon/Custom Storage fakes for the policy handler tests."""

    def setUp(self):
        self.logger = MagicMock()
        self.mgmt, self.pol = MagicMock(), MagicMock()
        self.store = FakeStorage({REL: {
            "old1": {"category_name": "Games", "rule_group_id": "rg-old", "host_group_id": "hg1", "policy_name": "P",
                     "policy_id": "pol-old", "platform": "windows"},
            "old2": {"category_name": "News", "rule_group_id": "rg-old", "host_group_id": "hg1", "policy_name": "P",
                     "policy_id": "pol-old", "platform": "windows"},
            "other": {"category_name": "Games", "rule_group_id": "rg-other", "host_group_id": "hg2", "policy_name": "Q"},
        }})
        clients = {"FirewallManagement": self.mgmt, "FirewallPolicies": self.pol, "CustomStorage": self.store}
        p = patch.object(policies, "get_client", side_effect=lambda cls: clients[cls.__name__])
        p.start()
        self.addCleanup(p.stop)

        self.pol.create_policies.return_value = falcon_ok([{"id": "pol-new"}])
        self.pol.perform_action.return_value = OK
        self.mgmt.create_rule_group.return_value = falcon_ok(["rg-new"])
        self.mgmt.update_policy_container.return_value = OK
        self.mgmt.delete_rule_groups.return_value = OK
        self.pol.delete_policies.return_value = OK
        self.pol.update_policies.return_value = OK

    def rel(self):
        return self.store.objects(*REL)

    create_body = {
        "hostGroupId": "hg1", "hostGroupName": "Hosts", "policyName": "P", "platform": "windows",
        "categories": {"Games": "steam.com"}, "whitelist": "ok.com", "username": "spoofed",
    }

    def create(self, context=None):
        return policies.create_rule(req(dict(self.create_body), context=context), None, self.logger)

    update_body = {
        "ruleGroupId": "rg-old", "policyName": "P", "hostGroupId": "hg1",
        "platform": "windows", "categories": {"Games": "steam.com"},
    }

    def update(self, body=None):
        return policies.update_policy(req(dict(body or self.update_body)), None, self.logger)

    def make_legacy(self):
        """Records as written by the previous release: no policy_id and no platform."""
        for key in ("old1", "old2"):
            self.rel()[key].pop("policy_id")
            self.rel()[key].pop("platform")

    def record_calls(self):
        order = []

        def perform_action(**k):
            if k["action_name"] == "disable":
                order.append(("disable", k["ids"]))
            return OK

        def rename(**k):
            resource = k["body"]["resources"][0]  # FalconPy drops `id` from keyword arguments
            order.append(("rename", resource["id"], resource["name"]))
            return OK

        self.pol.create_policies.side_effect = lambda **k: (order.append(("create", k["name"])),
                                                            falcon_ok([{"id": "pol-new"}]))[1]
        self.pol.perform_action.side_effect = perform_action
        self.pol.delete_policies.side_effect = lambda **k: (order.append(("delete_pol", k["ids"])), OK)[1]
        self.pol.update_policies.side_effect = rename
        self.mgmt.delete_rule_groups.side_effect = lambda **k: (order.append(("delete_rg", k["ids"])), OK)[1]
        return order


class PolicyTestCase(PolicyBase):
    # --- create-rule -------------------------------------------------------

    def test_create_rule_success_prefers_context_user(self):
        resp = self.create(context={"user": {"username": "ana"}})
        self.assertEqual(resp.code, 200)
        self.assertEqual((resp.body["policyId"], resp.body["ruleGroupId"]), ("pol-new", "rg-new"))
        self.assertEqual((resp.body["rulesCreated"], resp.body["relationsWritten"]), (2, 1))
        self.assertEqual((resp.body["createdBy"], resp.body["createdBySource"]), ("ana", "context"))
        record = self.rel()["Games_rg-new_hg1"]
        self.assertEqual((record["policy_id"], record["created_by"], record["created_by_source"]),
                         ("pol-new", "ana", "context"))

    def test_create_rule_falls_back_to_ui_user_without_exposing_context(self):
        resp = self.create(context={"cid": "c1", "access_token": "secret"})
        self.assertEqual((resp.body["createdBy"], resp.body["createdBySource"]), ("spoofed", "ui"))
        self.assertNotIn("debugContext", resp.body)
        self.assertNotIn("secret", str(self.logger.mock_calls))
        self.assertEqual(self.rel()["Games_rg-new_hg1"]["created_by_source"], "ui")

    def test_list_policies_exposes_created_by_source(self):
        self.create()
        policy = next(p for p in policies.list_policies(req(), None, self.logger).body["policies"]
                      if p["rule_group_id"] == "rg-new")
        self.assertEqual((policy["created_by"], policy["created_by_source"]), ("spoofed", "ui"))

    def test_create_rule_policy_conflict_returns_falcon_error(self):
        self.pol.create_policies.return_value = {"status_code": 409, "body": {"errors": [{"message": "name exists"}]}}
        resp = self.create()
        self.assertEqual(resp.code, 409)
        self.assertIn("name exists", resp.body["error"])
        self.pol.delete_policies.assert_not_called()

    def test_create_rule_rolls_back_policy_when_rule_group_fails(self):
        self.mgmt.create_rule_group.return_value = {"status_code": 400, "body": {"errors": [{"message": "bad"}]}}
        self.assertEqual(self.create().code, 500)
        self.pol.delete_policies.assert_called_once_with(ids="pol-new")
        self.assertNotIn("Games_rg-new_hg1", self.rel())

    def test_create_rule_rolls_back_both_when_attach_fails(self):
        order = []
        self.mgmt.update_policy_container.return_value = {"status_code": 500}
        self.pol.delete_policies.side_effect = lambda **k: (order.append(("pol", k["ids"])), OK)[1]
        self.mgmt.delete_rule_groups.side_effect = lambda **k: (order.append(("rg", k["ids"])), OK)[1]
        self.assertEqual(self.create().code, 500)
        self.assertEqual(order, [("pol", "pol-new"), ("rg", ["rg-new"])])

    def test_create_rule_partial_relationship_failure_does_not_roll_back(self):
        self.store.fail_put.add("Games_rg-new_hg1")
        resp = self.create()
        self.assertEqual((resp.code, resp.body["relationsWritten"]), (200, 0))
        self.pol.delete_policies.assert_not_called()



class PolicyUpdateDeleteTestCase(PolicyBase):
    # --- update-policy -----------------------------------------------------
    def test_update_creates_new_policy_before_removing_old_one(self):
        order = self.record_calls()

        resp = self.update()

        self.assertEqual(resp.code, 200)
        self.assertEqual([step[0] for step in order], ["create", "disable", "delete_pol", "rename", "delete_rg"])
        self.assertTrue(order[0][1].startswith("P (updating "))  # old policy still holds the name
        self.assertEqual(order[1:], [("disable", "pol-old"), ("delete_pol", "pol-old"),
                                     ("rename", "pol-new", "P"), ("delete_rg", ["rg-old"])])
        self.assertEqual(set(self.rel()), {"other", "Games_rg-new_hg1"})  # old relations replaced
        self.assertEqual(self.rel()["Games_rg-new_hg1"]["policy_name"], "P")
        self.assertEqual(resp.body["warnings"], [])

    def test_update_ignores_policy_id_from_request(self):
        order = self.record_calls()
        self.assertEqual(self.update(dict(self.update_body, policyId="someone-elses-policy")).code, 200)
        self.assertIn(("delete_pol", "pol-old"), order)
        self.assertNotIn(("delete_pol", "someone-elses-policy"), order)

    def test_update_unknown_rule_group_changes_nothing(self):
        resp = self.update(dict(self.update_body, ruleGroupId="rg-unknown"))
        self.assertEqual(resp.code, 404)
        self.pol.create_policies.assert_not_called()
        self.pol.delete_policies.assert_not_called()

    def test_update_create_failure_leaves_old_policy_untouched(self):
        self.pol.create_policies.return_value = {"status_code": 409, "body": {"errors": [{"message": "dup"}]}}
        self.assertEqual(self.update().code, 409)
        self.pol.delete_policies.assert_not_called()
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertIn("old1", self.rel())

    def test_update_attach_failure_rolls_back_only_new_resources(self):
        self.mgmt.update_policy_container.return_value = {"status_code": 500}
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertTrue(resp.body["error"].endswith("Rolled back."))
        self.pol.delete_policies.assert_called_once_with(ids="pol-new")
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-new"])
        self.assertIn("old1", self.rel())

    def test_update_reports_incomplete_rollback(self):
        self.mgmt.update_policy_container.return_value = {"status_code": 500}
        self.pol.delete_policies.return_value = {"status_code": 500}
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertNotIn("Rolled back.", resp.body["error"])
        self.assertIn("Rollback incomplete: policy pol-new", resp.body["error"])

    def test_update_rolls_back_new_policy_if_old_cannot_be_deleted(self):
        def delete(**k):
            if k["ids"] == "pol-old":
                return {"status_code": 403, "body": {"errors": [{"message": "forbidden"}]}}
            return OK
        self.pol.delete_policies.side_effect = delete
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertIn("The update was not applied. Rolled back.", resp.body["error"])
        self.assertEqual([c.kwargs["ids"] for c in self.pol.delete_policies.call_args_list], ["pol-old", "pol-new"])
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-new"])
        self.pol.update_policies.assert_not_called()
        self.assertIn("old1", self.rel())

    def test_update_reports_rename_and_cleanup_failures_as_warnings(self):
        self.pol.update_policies.return_value = {"status_code": 500}
        self.mgmt.delete_rule_groups.return_value = {"status_code": 500}
        resp = self.update()
        self.assertEqual(resp.code, 200)
        self.assertEqual(len(resp.body["warnings"]), 2)
        record = self.rel()["Games_rg-new_hg1"]
        self.assertTrue(record["policy_name"].startswith("P (updating "))  # matches the real name in Falcon
        self.assertEqual(record["rule_group_name"], "P_RuleGroup")

    def test_update_legacy_record_resolves_policy_and_platform_from_falcon(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy"}])
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-legacy", "platform_name": "Windows"}])
        order = self.record_calls()

        resp = self.update(dict(self.update_body, platform=""))  # /list-policies returns '' for legacy records

        self.assertEqual(resp.code, 200)
        self.assertEqual(self.pol.query_combined_policies.call_args.kwargs["filter"], "name:'P'")
        self.pol.get_policies.assert_called_once_with(ids=["pol-legacy"])
        self.assertEqual(self.pol.create_policies.call_args.kwargs["platform_name"], "Windows")
        self.assertEqual(self.mgmt.create_rule_group.call_args.kwargs["platform"], "windows")
        self.assertIn(("delete_pol", "pol-legacy"), order)

    def test_update_legacy_without_platform_or_policy_is_rejected(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([])
        resp = self.update(dict(self.update_body, platform=""))
        self.assertEqual(resp.code, 400)
        self.pol.create_policies.assert_not_called()

    def test_update_without_existing_policy_uses_final_name(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([])
        order = self.record_calls()
        self.assertEqual(self.update().code, 200)
        self.assertEqual(order[0], ("create", "P"))
        self.pol.delete_policies.assert_not_called()
        self.pol.update_policies.assert_not_called()

    def test_update_aborts_if_legacy_lookup_fails(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = {"status_code": 500}
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertIn("Nothing was changed", resp.body["error"])
        self.pol.create_policies.assert_not_called()

    # --- delete-policy -----------------------------------------------------
    def delete(self, body):
        return policies.delete_policy(req(body), None, self.logger)

    def test_delete_policy_disables_then_deletes_policy_then_rule_group(self):
        order = self.record_calls()
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual((resp.code, resp.body["relationsDeleted"]), (200, 2))
        self.assertEqual(order, [("disable", "pol-old"), ("delete_pol", "pol-old"), ("delete_rg", ["rg-old"])])
        self.assertEqual(set(self.rel()), {"other"})

    def test_delete_ignores_policy_id_from_request(self):
        order = self.record_calls()
        self.assertEqual(self.delete({"rule_group_id": "rg-old", "policy_id": "someone-elses-policy"}).code, 200)
        self.assertNotIn(("delete_pol", "someone-elses-policy"), order)
        self.assertIn(("delete_pol", "pol-old"), order)

    def test_delete_unknown_rule_group_deletes_nothing(self):
        resp = self.delete({"rule_group_id": "rg-unknown", "policy_id": "someone-elses-policy"})
        self.assertEqual(resp.code, 404)
        self.pol.delete_policies.assert_not_called()
        self.mgmt.delete_rule_groups.assert_not_called()

    def test_delete_policy_failure_keeps_rule_group_and_relations(self):
        self.pol.delete_policies.return_value = {"status_code": 403, "body": {"errors": [{"message": "forbidden"}]}}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertIn("forbidden", resp.body["error"])
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertIn("old1", self.rel())

    def test_delete_disable_failure_deletes_nothing(self):
        self.pol.perform_action.return_value = {"status_code": 500}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 500)
        self.pol.delete_policies.assert_not_called()
        self.assertIn("old1", self.rel())

    def test_delete_rule_group_failure_keeps_relations_for_retry(self):
        self.mgmt.delete_rule_groups.return_value = {"status_code": 500}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 500)
        self.assertIn("old1", self.rel())

    def test_delete_retry_treats_already_deleted_policy_as_gone(self):
        self.pol.perform_action.return_value = {"status_code": 404}
        self.pol.delete_policies.return_value = {"status_code": 404}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.assertEqual(set(self.rel()), {"other"})

    def test_delete_legacy_record_resolves_policy_by_name(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy"}])
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-legacy")

    def test_delete_counts_only_successful_deletes(self):
        self.store.fail_delete.add("old2")
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).body["relationsDeleted"], 1)

    def test_delete_policy_requires_rule_group(self):
        self.assertEqual(self.delete({}).code, 400)


class PolicyQueryTestCase(PolicyBase):
    # --- list-policies -------------------------------------------------------

    def test_list_policies_groups_full_records(self):
        self.rel()["old1"]["policy_id"] = "pol-old"
        resp = policies.list_policies(req(), None, self.logger)
        self.assertEqual(resp.code, 200)
        by_rg = {p["rule_group_id"]: p for p in resp.body["policies"]}
        self.assertEqual(set(by_rg), {"rg-old", "rg-other"})
        self.assertEqual(sorted(by_rg["rg-old"]["categories"]), ["Games", "News"])
        self.assertEqual(by_rg["rg-old"]["policy_id"], "pol-old")

    def test_list_policies_storage_error(self):
        self.store.list_status = 500
        self.assertEqual(policies.list_policies(req(), None, self.logger).code, 500)

    # --- health-check / check-enforcement ----------------------------------
    def test_health_check_batches_by_policy_id(self):
        self.store.data[REL] = {
            "a": {"policy_id": "p1", "policy_name": "A"}, "b": {"policy_id": "p1", "policy_name": "A"},
            "c": {"policy_id": "p2", "policy_name": "B"},
        }
        self.pol.get_policies.return_value = falcon_ok([
            {"id": "p1", "enabled": True, "groups": [{"id": "g"}]}, {"id": "p2", "enabled": False, "groups": []}])
        self.mgmt.get_policy_containers.return_value = falcon_ok([
            {"policy_id": "p1", "enforce": True, "rule_group_ids": ["rg"]},
            {"policy_id": "p2", "enforce": True, "rule_group_ids": ["rg"]}])

        resp = policies.health_check(req(), None, self.logger)

        self.assertEqual((resp.body["healthy_count"], resp.body["issues_count"]), (1, 1))
        self.pol.get_policies.assert_called_once()
        self.pol.query_combined_policies.assert_not_called()

    def test_health_check_legacy_name_lookup_escapes_quotes(self):
        self.store.data[REL] = {"a": {"policy_name": "o'brien' OR name:*"}}
        self.pol.query_combined_policies.return_value = falcon_ok([])
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(self.pol.query_combined_policies.call_args.kwargs["filter"], "name:'o\\'brien\\' OR name:*'")
        self.assertEqual(resp.body["policies"][0]["issues"], ["Policy not found in Falcon"])

    def test_health_check_reports_falcon_errors_instead_of_missing_policies(self):
        self.store.data[REL] = {"a": {"policy_id": "p1", "policy_name": "A"}}
        self.pol.get_policies.return_value = {"status_code": 429, "body": {"errors": [{"message": "throttled"}]}}
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.code, 502)
        self.assertIn("throttled", resp.body["error"])

        self.pol.get_policies.return_value = falcon_ok([{"id": "p1", "enabled": True}])
        self.mgmt.get_policy_containers.return_value = {"status_code": 500}
        self.assertEqual(policies.health_check(req(), None, self.logger).code, 502)

    def test_health_check_batches_policy_ids(self):
        self.store.data[REL] = {f"r{i:03d}": {"policy_id": f"p{i:03d}", "policy_name": f"N{i}"} for i in range(150)}
        self.pol.get_policies.side_effect = lambda ids: falcon_ok([{"id": i, "enabled": True, "groups": [1]} for i in ids])
        self.mgmt.get_policy_containers.side_effect = lambda ids: falcon_ok(
            [{"policy_id": i, "enforce": True, "rule_group_ids": ["rg"]} for i in ids])

        resp = policies.health_check(req(), None, self.logger)

        self.assertEqual([len(c.kwargs["ids"]) for c in self.pol.get_policies.call_args_list], [100, 50])
        self.assertEqual(self.mgmt.get_policy_containers.call_count, 2)
        self.assertEqual(resp.body["healthy_count"], 150)

    def test_health_check_keeps_found_policies_on_partial_404(self):
        self.store.data[REL] = {"a": {"policy_id": "p1", "policy_name": "A"}, "b": {"policy_id": "gone", "policy_name": "B"}}
        self.pol.get_policies.return_value = {"status_code": 404, "body": {"resources": [
            {"id": "p1", "enabled": True, "groups": [1]}]}}
        self.mgmt.get_policy_containers.return_value = falcon_ok(
            [{"policy_id": "p1", "enforce": True, "rule_group_ids": ["r"]}])
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual((resp.code, resp.body["healthy_count"], resp.body["issues_count"]), (200, 1, 1))

    def test_check_enforcement_reads_policy_id_from_query(self):
        self.mgmt.get_policy_containers.return_value = falcon_ok([{"policy_id": "p1", "enforce": True}])
        resp = policies.check_enforcement(req(query={"policy_id": "p1"}), None, self.logger)
        self.assertEqual((resp.code, resp.body["enforce"]), (200, True))
        self.mgmt.get_policy_containers.assert_called_once_with(ids="p1")
        self.assertEqual(policies.check_enforcement(req(), None, self.logger).code, 400)


class AnalyticsTruncatedTestCase(unittest.TestCase):
    def run_handler(self, mgmt):
        with patch.object(analytics, "get_client", return_value=mgmt):
            return analytics.get_domain_analytics(req(), None, MagicMock())

    event = {"domain_name_list": "a.com", "host_name": "h", "timestamp": "2026-01-01T00:00:00Z"}

    def test_not_truncated_when_all_pages_read(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok(["e1"])
        mgmt.get_events.return_value = falcon_ok([self.event])
        resp = self.run_handler(mgmt)
        self.assertFalse(resp.body["truncated"])
        self.assertEqual(resp.body["visualization_data"]["summary"]["total_blocks"], 1)

    def test_truncated_when_page_cap_reached(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok([f"e{i}" for i in range(500)])
        mgmt.get_events.return_value = falcon_ok([self.event])
        resp = self.run_handler(mgmt)
        self.assertTrue(resp.body["truncated"])
        self.assertEqual(mgmt.query_events.call_count, 20)

    def test_truncated_on_api_error(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = {"status_code": 500}
        self.assertTrue(self.run_handler(mgmt).body["truncated"])


if __name__ == "__main__":
    unittest.main()

"""Tests for policy lifecycle (create/update/delete/list/health), helpers and analytics."""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name,too-many-lines

import unittest
from datetime import datetime, timezone
from functools import partial
from unittest.mock import MagicMock, call, patch

from crowdstrike.foundry.function import Request, RequestParams

import main  # noqa: F401  # pylint: disable=unused-import
from app_utils import (
    read_all_objects,
    category_key, relationship_key, validate_fqdn, _validate_falcon_response, _sanitize_url_list, plural,
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

    def test_plural(self):
        self.assertEqual([plural(n, "record") for n in (0, 1, 2)], ["0 records", "1 record", "2 records"])
        self.assertEqual([plural(n, "category", "categories") for n in (1, 3)], ["1 category", "3 categories"])

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
        # get_rule_groups: the platform of each rule group, which it keeps once deleted (deleted: true).
        # A rule group not listed here is not returned (a 200 without it)
        self.rule_group_platforms = {"rg-old": "windows"}
        self.deleted_rule_groups = set()
        self.mgmt.get_rule_groups.side_effect = lambda ids: falcon_ok([
            {"id": i, "platform": self.rule_group_platforms[i], "deleted": i in self.deleted_rule_groups}
            for i in ids if i in self.rule_group_platforms])

    def rel(self):
        return self.store.objects(*REL)

    # the legacy policy "P", as Falcon returns it from query_combined_policies
    legacy_policy = {"id": "pol-legacy", "name": "P", "platform_name": "Windows", "enabled": True}

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
        self.assertEqual(record["rule_format"], "sanitized")

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
        self.assertEqual(resp.body["warnings"], [
            "No relationship record could be written: policy pol-new is in Falcon, but this app does not "
            "track it, so it is not listed in Firewall Rules. Manage or delete it in Falcon."])

    def test_create_rule_reports_categories_left_untracked(self):
        body = dict(self.create_body, categories={"Games": "steam.com", "News": "bbc.com"})
        self.store.fail_put.add("News_rg-new_hg1")
        resp = policies.create_rule(req(body), None, self.logger)
        self.assertEqual((resp.code, resp.body["relationsWritten"]), (200, 1))
        self.assertEqual(resp.body["warnings"], [
            "1 of 2 relationship records could not be written: those categories are blocked "
            "but not listed for this policy in Firewall Rules."])
        self.assertEqual(self.create().body["warnings"], [])



    def test_create_rule_without_categories_is_rejected(self):
        # a whitelist alone would create a policy with no relationship record, which the app never lists
        for categories in ({}, None):
            body = dict(self.create_body, categories=categories)
            if categories is None:
                del body["categories"]
            resp = policies.create_rule(req(body), None, self.logger)
            self.assertEqual((resp.code, resp.body["error"]), (400, "At least one category is required"))
        self.pol.create_policies.assert_not_called()
        self.mgmt.create_rule_group.assert_not_called()
        self.assertEqual(self.store.calls, [])


    def test_create_rule_with_a_category_without_valid_domains_is_rejected(self):
        # its record would list the category as blocked, but its rule would block nothing
        for categories, error in (({"Games": "steam.com", "News": "not a domain;1.2.3.4"}, "category 'News'"),
                                  ({"Games": "", "News": "  "}, "categories 'Games', 'News'")):
            resp = policies.create_rule(req(dict(self.create_body, categories=categories)), None, self.logger)
            self.assertEqual((resp.code, resp.body["error"]), (400, f"No valid domain in {error}"))
        self.pol.create_policies.assert_not_called()
        self.mgmt.create_rule_group.assert_not_called()
        self.assertEqual(self.store.calls, [])


class PolicyChangeBase(PolicyBase):
    """update-policy and delete-policy: both go through _delete_policy."""

    def setUp(self):
        super().setUp()
        # _delete_policy reads the policy's state first: an enabled Windows policy by default
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": True, "platform_name": "Windows"}])
        # a legacy policy is identified by the stored rule group in its Falcon container
        self.containers({})

    def containers(self, rule_groups_by_policy, default=("rg-old",)):
        """get_policy_containers: the rule groups of each policy (`default` for the others)."""
        self.mgmt.get_policy_containers.side_effect = lambda ids: falcon_ok(
            [{"policy_id": i, "rule_group_ids": list(rule_groups_by_policy.get(i, default))} for i in ids])

    def fail_old_delete(self):
        self.pol.delete_policies.side_effect = lambda **k: (
            {"status_code": 403, "body": {"errors": [{"message": "forbidden"}]}} if k["ids"] == "pol-old" else OK)

    def delete(self, body):
        return policies.delete_policy(req(body), None, self.logger)

    def touched_policies(self):
        """Policy ids that were disabled, enabled or deleted."""
        acted = [c.kwargs["ids"] for c in self.pol.perform_action.call_args_list
                 if c.kwargs["action_name"] in ("disable", "enable")]
        return set(acted) | {c.kwargs["ids"] for c in self.pol.delete_policies.call_args_list}


class PolicyUpdateTestCase(PolicyChangeBase):
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
        self.fail_old_delete()
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertIn("The update was not applied. Rolled back.", resp.body["error"])
        self.assertEqual([c.kwargs["ids"] for c in self.pol.delete_policies.call_args_list], ["pol-old", "pol-new"])
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-new"])
        self.pol.update_policies.assert_not_called()
        self.assertIn("old1", self.rel())
        # the old policy was disabled before the failed delete: it must be enforcing again
        self.assertIn(call(action_name="enable", ids="pol-old"), self.pol.perform_action.call_args_list)
        # the rolled-back new policy is not re-enabled
        self.assertNotIn(call(action_name="enable", ids="pol-new"), self.pol.perform_action.call_args_list[1:])

    def test_update_keeps_new_policy_when_old_is_left_disabled(self):
        # disable OK, delete 403, enable 500: rolling back would leave nothing enforced
        self.fail_old_delete()
        self.pol.perform_action.side_effect = lambda **k: (
            {"status_code": 500} if (k["action_name"], k["ids"]) == ("enable", "pol-old") else OK)
        resp = self.update()
        self.assertEqual(resp.code, 200)
        self.assertEqual([c.kwargs["ids"] for c in self.pol.delete_policies.call_args_list], ["pol-old"])
        self.mgmt.delete_rule_groups.assert_not_called()  # neither the new nor the old one
        self.pol.update_policies.assert_not_called()  # the old policy still holds the name
        self.assertEqual(len(resp.body["warnings"]), 1)
        self.assertIn("left disabled", resp.body["warnings"][0])
        self.assertIn("pol-old", resp.body["warnings"][0])
        # the new policy is tracked, and the old one stays listed so it can be deleted later
        self.assertEqual(set(self.rel()), {"old1", "old2", "other", "Games_rg-new_hg1"})
        self.assertTrue(self.rel()["Games_rg-new_hg1"]["policy_name"].startswith("P (updating "))

    def test_update_does_not_enable_policy_disabled_by_admin(self):
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        self.fail_old_delete()
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertIn("Rolled back.", resp.body["error"])
        self.assertNotIn("pol-old", [c.kwargs["ids"] for c in self.pol.perform_action.call_args_list
                                     if c.kwargs["action_name"] in ("disable", "enable")])

    def test_update_old_policy_state_read_error_changes_nothing(self):
        for unreadable in ({"status_code": 429, "body": {"errors": [{"message": "slow"}]}},
                           falcon_ok([])):  # a 200 without the policy does not mean it is gone
            self.pol.get_policies.return_value = unreadable
            resp = self.update()
            self.assertEqual(resp.code, 502)
            self.assertIn("Nothing was changed", resp.body["error"])
        self.pol.create_policies.assert_not_called()
        self.pol.delete_policies.assert_not_called()

    def test_update_replaces_policy_disabled_by_admin_with_a_disabled_one(self):
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        resp = self.update()
        self.assertEqual(resp.code, 200)
        self.assertNotIn(call(action_name="enable", ids="pol-new"), self.pol.perform_action.call_args_list)
        self.assertIn(call(action_name="add-host-group", group_id="hg1", ids="pol-new"),
                      self.pol.perform_action.call_args_list)
        self.assertIn("created disabled", resp.body["warnings"][0])

    def test_update_of_policy_disabled_by_this_app_stays_enforcing(self):
        for key in ("old1", "old2"):
            self.rel()[key]["disabled_by_app"] = True
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        resp = self.update()
        self.assertEqual(resp.code, 200)
        self.assertIn(call(action_name="enable", ids="pol-new"), self.pol.perform_action.call_args_list)
        self.assertEqual(resp.body["warnings"], [])

    def test_update_failure_enables_again_a_policy_this_app_left_disabled(self):
        for key in ("old1", "old2"):
            self.rel()[key]["disabled_by_app"] = True
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        self.fail_old_delete()
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertIn("Rolled back.", resp.body["error"])
        self.assertIn(call(action_name="enable", ids="pol-old"), self.pol.perform_action.call_args_list)
        self.assertNotIn("disabled_by_app", self.rel()["old1"])

    def assert_legacy_update_changes_nothing(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([dict(self.legacy_policy)])
        resp = self.update(dict(self.update_body, platform=""))
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.body["error"], "Failed to record the current policy id. Nothing was changed.")
        self.pol.create_policies.assert_not_called()
        self.mgmt.create_rule_group.assert_not_called()
        self.pol.perform_action.assert_not_called()
        self.pol.delete_policies.assert_not_called()
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertEqual(set(self.rel()), {"old1", "old2", "other"})
        self.assertNotIn("policy_id", self.rel()["old2"])
        self.assertIn("old2", str(self.logger.error.call_args_list))

    def test_update_legacy_policy_id_write_failure_changes_nothing(self):
        self.store.fail_put.add("old2")
        self.assert_legacy_update_changes_nothing()

    def test_update_legacy_policy_id_write_exception_changes_nothing(self):
        put = self.store.PutObjectByVersion

        def failing_put(**kwargs):
            if kwargs["object_key"] == "old2":
                raise RuntimeError("connection reset")
            return put(**kwargs)

        self.store.PutObjectByVersion = failing_put
        self.assert_legacy_update_changes_nothing()
        self.assertIn("connection reset", str(self.logger.error.call_args_list))

    def test_update_reports_new_policy_left_untracked(self):
        self.store.fail_put.add("Games_rg-new_hg1")
        resp = self.update()
        self.assertEqual(resp.code, 200)
        self.assertIn("No relationship record could be written: policy pol-new is in Falcon, but this app does not "
                      "track it, so it is not listed in Firewall Rules. Manage or delete it in Falcon.",
                      resp.body["warnings"])
        self.assertEqual(set(self.rel()), {"other"})

    def test_update_missing_name_or_host_group_is_rejected(self):
        for field_name, body_key in (("policy_name", "policyName"), ("host_group_id", "hostGroupId")):
            stored = {key: self.rel()[key].pop(field_name) for key in ("old1", "old2")}
            resp = self.update(dict(self.update_body, **{body_key: ""}))
            self.assertEqual(resp.code, 400, field_name)
            for key, value in stored.items():
                self.rel()[key][field_name] = value
        self.pol.create_policies.assert_not_called()

    def test_update_without_categories_is_rejected(self):
        # the old records would be deleted and the new policy written with none: the app would lose it
        records = {k: dict(v) for k, v in self.rel().items()}
        for categories in ({}, None):
            body = dict(self.update_body, categories=categories, whitelist="ok.com")
            if categories is None:
                del body["categories"]
            resp = self.update(body)
            self.assertEqual((resp.code, resp.body["error"]), (400, "At least one category is required"))
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.assertEqual(self.store.calls, [])
        self.assertEqual(self.rel(), records)

    def test_update_with_a_category_without_valid_domains_is_rejected(self):
        records = {k: dict(v) for k, v in self.rel().items()}
        resp = self.update(dict(self.update_body, categories={"Games": "steam.com", "News": "http://"}))
        self.assertEqual((resp.code, resp.body["error"]), (400, "No valid domain in category 'News'"))
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.assertEqual(self.store.calls, [])
        self.assertEqual(self.rel(), records)

    def test_update_uses_stored_host_group_and_platform(self):
        resp = self.update(dict(self.update_body, hostGroupId="hg-other", platform="mac", hostGroupName="X"))
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.pol.perform_action.call_args_list[1],
                         call(action_name="add-host-group", group_id="hg1", ids="pol-new"))
        self.assertEqual(self.pol.create_policies.call_args.kwargs["platform_name"], "Windows")
        self.assertEqual(self.mgmt.create_rule_group.call_args.kwargs["platform"], "windows")
        self.assertEqual(set(self.rel()), {"other", "Games_rg-new_hg1"})

    def test_update_legacy_record_without_host_group_uses_request(self):
        for key in ("old1", "old2"):
            self.rel()[key].pop("host_group_id")
        self.assertEqual(self.update(dict(self.update_body, hostGroupId="hg9")).code, 200)
        self.assertIn("Games_rg-new_hg9", self.rel())
        self.assertEqual(self.update(dict(self.update_body, ruleGroupId="rg-new", hostGroupId="")).code, 200)

    def test_update_strips_temporary_name_left_by_failed_rename(self):
        for key in ("old1", "old2"):
            self.rel()[key]["policy_name"] = "P (updating ab12cd34) (updating 0123abcd)"
        order = self.record_calls()
        resp = self.update(dict(self.update_body, policyName="P (updating ab12cd34) (updating 0123abcd)"))
        self.assertEqual(resp.code, 200)
        self.assertRegex(order[0][1], r"^P \(updating [0-9a-f]{8}\)$")
        self.assertIn(("rename", "pol-new", "P"), order)
        self.assertEqual(self.rel()["Games_rg-new_hg1"]["policy_name"], "P")

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
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-legacy", "name": "P", "enabled": True, "platform_name": "Windows"}])
        order = self.record_calls()

        resp = self.update(dict(self.update_body, platform=""))  # /list-policies returns '' for legacy records

        self.assertEqual(resp.code, 200)
        self.assertEqual(self.pol.query_combined_policies.call_args.kwargs["filter"], "name:['P']")
        self.pol.get_policies.assert_not_called()  # platform and state come from the name lookup
        self.assertIn(("disable", "pol-legacy"), order)
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
        self.assertEqual(resp.code, 502)
        self.assertIn("Nothing was changed", resp.body["error"])
        self.pol.create_policies.assert_not_called()

    def test_update_legacy_policy_without_platform_is_rejected(self):
        # neither the records, the policy nor Falcon's answer for the rule group give the platform
        self.make_legacy()
        self.rule_group_platforms.clear()
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy", "name": "P"}])
        resp = self.update(dict(self.update_body, platform="windows"))
        self.assertEqual(resp.code, 400)
        self.pol.create_policies.assert_not_called()

class PolicyUpdateMarkerTestCase(PolicyChangeBase):
    # --- update-policy: the disabled_by_app marker of the previous policy -------
    def test_update_reports_partial_relationship_writes(self):
        self.store.fail_put.add("News_rg-new_hg1")
        resp = self.update(dict(self.update_body, categories={"Games": "steam.com", "News": "bbc.com"}))
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.body["warnings"], ["1 relationship record could not be written"])

    def mark_disabled_by_app(self):
        """The policy is disabled because an earlier delete of this app could not enable it again."""
        for key in ("old1", "old2"):
            self.rel()[key]["disabled_by_app"] = True
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])

    stale_marker = ("The policy's records still say this app disabled it (disabled_by_app could not be cleared), "
            "so a later failed delete could enable it again even if it has been disabled in Falcon.")

    def test_update_rollback_reports_marker_that_could_not_be_cleared(self):
        self.mark_disabled_by_app()
        self.fail_old_delete()
        self.store.fail_put.add("old1")
        resp = self.update()
        self.assertEqual(resp.code, 500)
        self.assertTrue(resp.body["error"].endswith("Rolled back. " + self.stale_marker), resp.body["error"])
        self.assertIn(call(action_name="enable", ids="pol-old"), self.pol.perform_action.call_args_list)
        self.assertTrue(self.rel()["old1"]["disabled_by_app"])
        self.assertNotIn("disabled_by_app", self.rel()["old2"])

    def test_update_kept_old_policy_reports_marker_that_could_not_be_cleared(self):
        self.mark_disabled_by_app()
        self.fail_old_delete()
        self.pol.perform_action.side_effect = lambda **k: (
            {"status_code": 500} if (k["action_name"], k["ids"]) == ("enable", "pol-old") else OK)
        self.store.fail_put.add("old1")
        resp = self.update()
        self.assertEqual(resp.code, 200)
        self.assertIn(self.stale_marker, resp.body["warnings"])
        self.assertTrue(self.rel()["old1"]["disabled_by_app"])

    def test_update_does_not_warn_when_the_marker_is_cleared(self):
        self.mark_disabled_by_app()
        self.fail_old_delete()
        resp = self.update()
        self.assertNotIn("disabled_by_app", resp.body["error"])
        self.assertNotIn("disabled_by_app", self.rel()["old1"])


class PolicyLegacyMatchTestCase(PolicyChangeBase):
    # --- legacy records: resolving the policy by name ------------------------
    def test_legacy_name_matching_several_policies_touches_nothing(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "pol-a", "name": "P", "platform_name": "Windows"},
            {"id": "pol-b", "name": "P", "platform_name": "Windows"}])
        resp = self.update()
        self.assertEqual(resp.code, 409)
        self.pol.create_policies.assert_not_called()
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 409)
        self.pol.perform_action.assert_not_called()
        self.pol.delete_policies.assert_not_called()

    def same_name_policies(self, mac_host_group):
        """The app's Windows "P" on hg1 holding rg-old, and an unrelated Mac "P" holding rg-mac."""
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "pol-win", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]},
            {"id": "pol-mac", "name": "P", "platform_name": "Mac", "enabled": True,
             "groups": [{"id": mac_host_group}]}])
        self.containers({"pol-win": ["rg-old"], "pol-mac": ["rg-mac"]})

    def test_legacy_request_platform_never_selects_the_policy(self):
        self.same_name_policies(mac_host_group="hg-mac")
        resp = self.delete({"rule_group_id": "rg-old", "platform": "mac"})
        self.assertEqual(resp.code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-win")
        self.assertNotIn("pol-mac", self.touched_policies())

    def test_legacy_same_name_on_same_host_group_resolved_by_rule_group(self):
        # both are on hg1: only the one whose container holds rg-old is the app's policy,
        # whatever platform the request names
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "pol-win", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]},
            {"id": "pol-mac", "name": "P", "platform_name": "Mac", "enabled": True, "groups": [{"id": "hg1"}]}])
        self.containers({"pol-win": ["rg-win"], "pol-mac": ["rg-old"]})
        self.rule_group_platforms["rg-old"] = "mac"
        resp = self.delete({"rule_group_id": "rg-old", "platform": "windows"})
        self.assertEqual(resp.code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-mac")
        self.assertNotIn("pol-win", self.touched_policies())

    def test_ui_update_request_manages_same_name_legacy_policies(self):
        # /list-policies returns '' as the platform of legacy rows, and the UI sends it back
        self.same_name_policies(mac_host_group="hg-mac")
        resp = self.update(dict(self.update_body, platform=""))
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.pol.create_policies.call_args.kwargs["platform_name"], "Windows")
        self.pol.delete_policies.assert_called_once_with(ids="pol-win")
        self.assertNotIn("pol-mac", self.touched_policies())

    def test_ui_delete_request_manages_same_name_legacy_policies(self):
        # the UI sends only the rule group to /delete-policy
        self.same_name_policies(mac_host_group="hg1")  # host group alone cannot tell them apart
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-win")
        self.assertNotIn("pol-mac", self.touched_policies())

    def test_legacy_container_read_error_changes_nothing(self):
        self.same_name_policies(mac_host_group="hg-mac")
        self.mgmt.get_policy_containers.side_effect = lambda ids: {
            "status_code": 429, "body": {"errors": [{"message": "slow"}]}}
        for resp in (self.update(dict(self.update_body, platform="")), self.delete({"rule_group_id": "rg-old"})):
            self.assertEqual(resp.code, 502)
            self.assertIn("slow", resp.body["error"])
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.assertNotIn("policy_id", self.rel()["old1"])

    def test_legacy_wrong_request_platform_does_not_hide_the_policy(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-win", "name": "P", "platform_name": "Windows", "enabled": True}])
        self.assertEqual(self.delete({"rule_group_id": "rg-old", "platform": "mac"}).code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-win")

    def test_legacy_same_name_on_two_platforms_uses_stored_host_group(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "pol-win", "name": "P", "platform_name": "Windows", "groups": [{"id": "hg1"}]},
            {"id": "pol-mac", "name": "P", "platform_name": "Mac", "groups": [{"id": "hg-mac"}]}])
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-win")

    def same_name_health_check(self, mac_rule_groups):
        """Legacy "P" records of rg-a and rg-b on hg1: a Windows "P" holds rg-a, a disabled Mac "P" on hg1."""
        self.store.data[REL] = {"a": {"policy_name": "P", "host_group_id": "hg1", "rule_group_id": "rg-a"},
                                "b": {"policy_name": "P", "host_group_id": "hg1", "rule_group_id": "rg-b"}}
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "p-win", "name": "P", "platform_name": "Windows", "groups": [{"id": "hg1"}]},
            {"id": "p-mac", "name": "P", "platform_name": "Mac", "groups": [{"id": "hg1"}]}])
        self.pol.get_policies.side_effect = lambda ids: falcon_ok(
            [{"id": i, "enabled": i == "p-win", "groups": [{"id": "hg1"}]} for i in ids])
        self.containers({"p-win": ["rg-a"], "p-mac": mac_rule_groups})
        self.rule_group_platforms.update({"rg-a": "windows", "rg-b": "mac"})
        self.mgmt.get_policy_containers.side_effect = lambda ids, f=self.mgmt.get_policy_containers.side_effect: (
            falcon_ok([dict(c, enforce=True) for c in f(ids)["body"]["resources"]]))
        resp = policies.health_check(req(), None, self.logger)
        return {p["rule_group_id"]: p for p in resp.body["policies"]}

    def test_health_check_resolves_same_name_legacy_policies_by_rule_group(self):
        # one entry per name and rule group, resolved as delete-policy and update-policy do
        entries = self.same_name_health_check(mac_rule_groups=["rg-b"])
        self.assertEqual(set(entries), {"rg-a", "rg-b"})
        self.assertEqual((entries["rg-a"]["policy_id"], entries["rg-a"]["status"]), ("p-win", "healthy"))
        self.assertEqual((entries["rg-b"]["policy_id"], entries["rg-b"]["issues"]), ("p-mac", ["Policy DISABLED"]))

    def test_health_check_finds_legacy_policies_whose_rule_group_was_never_attached(self):
        entries = self.same_name_health_check(mac_rule_groups=[])
        self.assertEqual(entries["rg-a"]["policy_id"], "p-win")
        self.assertEqual((entries["rg-b"]["policy_id"], entries["rg-b"]["issues"]),
                         ("p-mac", ["Policy DISABLED", "No rule groups attached"]))

    def test_legacy_name_lookup_uses_exact_name_and_stored_platform(self):
        self.make_legacy()
        for key in ("old1", "old2"):
            self.rel()[key]["platform"] = "windows"
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "pol-mac", "name": "P", "platform_name": "Mac"},
            {"id": "pol-case", "name": "p", "platform_name": "Windows"},
            {"id": "pol-win", "name": "P", "platform_name": "Windows", "enabled": True}])
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-win")


class PolicyLegacyFallbackTestCase(PolicyChangeBase):
    """Legacy policies whose rule group was never attached: their Falcon container is empty."""

    def setUp(self):
        super().setUp()
        self.make_legacy()

    def policies_named_p(self, *policy_ids):
        """query_combined_policies: an enabled Windows "P" on hg1 for each id."""
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": pid, "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]}
            for pid in policy_ids])

    def assert_nothing_changed(self, resp):
        self.assertEqual(resp.code, 409)
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_not_called()
        for key in ("old1", "old2"):
            self.assertNotIn("policy_id", self.rel()[key])

    def test_delete_disables_and_deletes_the_only_policy_with_the_name_on_the_host_group(self):
        self.policies_named_p("pol-legacy")
        self.containers({"pol-legacy": []})
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.pol.perform_action.assert_called_once_with(action_name="disable", ids="pol-legacy")
        self.pol.delete_policies.assert_called_once_with(ids="pol-legacy")
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-old"])
        self.assertEqual(set(self.rel()), {"other"})

    def test_update_replaces_the_only_policy_with_the_name_on_the_host_group(self):
        self.policies_named_p("pol-legacy")
        self.containers({"pol-legacy": []})
        resp = self.update(dict(self.update_body, platform=""))
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.pol.create_policies.call_args.kwargs["platform_name"], "Windows")
        self.pol.delete_policies.assert_called_once_with(ids="pol-legacy")
        self.assertEqual(set(self.rel()), {"other", "Games_rg-new_hg1"})

    def update_without_the_old_policy(self, new_records_written=True):
        """
        update-policy when the legacy policy no longer exists: the replacement is created as "P"
        on hg1, and one old record (without policy_id: there was none to store) is left behind.
        """
        self.policies_named_p()
        self.store.fail_delete.add("old2")
        if not new_records_written:
            self.store.fail_put.add("Games_rg-new_hg1")
        self.assertEqual(self.update().code, 200)
        self.assertNotIn("policy_id", self.rel()["old2"])
        self.store.fail_delete.clear()
        self.store.fail_put.clear()
        self.pol.reset_mock()
        self.mgmt.reset_mock()
        self.policies_named_p("pol-new")
        self.containers({"pol-new": ["rg-new"]})

    def test_leftover_legacy_record_never_matches_the_replacement_of_a_missing_policy(self):
        self.update_without_the_old_policy()
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.touched_policies(), set())
        self.assertNotIn("old2", self.rel())
        self.assertIn("Games_rg-new_hg1", self.rel())

    def test_leftover_legacy_record_never_matches_an_untracked_replacement(self):
        # the replacement's records could not be written: no key names rg-new, but it holds it
        self.update_without_the_old_policy(new_records_written=False)
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 409)
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertIn("old2", self.rel())

    def test_health_check_and_delete_agree_on_a_leftover_record_when_the_replacement_record_is_unreadable(self):
        # rg-new's record cannot be read, but its key still names rg-new: in both, the renamed
        # replacement holds a tracked rule group, so the leftover record's policy is gone
        self.update_without_the_old_policy()
        self.store.fail_get.add("Games_rg-new_hg1")
        health = policies.health_check(req(), None, self.logger).body
        entry = next(p for p in health["policies"] if p["rule_group_id"] == "rg-old")
        self.assertEqual((entry["policy_id"], entry["issues"]), (None, ["Policy not found in Falcon"]))
        self.assertEqual(health["warnings"], ["1 relationship record could not be read, so its policy may be "
                                              "missing from this report"])

        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.touched_policies(), set())
        self.assertEqual(set(self.rel()), {"other", "Games_rg-new_hg1"})

    def test_health_check_reports_legacy_policies_unresolved_when_the_keys_cannot_be_listed(self):
        self.policies_named_p("pol-legacy")
        self.containers({"pol-legacy": []})
        with patch.object(policies, "_list_relationship_keys", return_value=(None, "Failed to read relationships")):
            health = policies.health_check(req(), None, self.logger).body
        entry = next(p for p in health["policies"] if p["rule_group_id"] == "rg-old")
        self.assertEqual((entry["policy_id"], entry["issues"]),
                         (None, ["Failed to read relationships, so the policy could not be resolved"]))

    def test_several_policies_with_the_name_on_the_host_group_change_nothing(self):
        self.policies_named_p("pol-a", "pol-b")
        self.containers({}, default=())
        for resp in (self.update(dict(self.update_body, platform="")), self.delete({"rule_group_id": "rg-old"})):
            self.assertIn("2 Falcon policies named 'P'", resp.body["error"])
            self.assert_nothing_changed(resp)

    def test_policy_without_a_container_is_not_matched(self):
        # Falcon's API does not say a policy with no container holds no rule group
        self.policies_named_p("pol-legacy")
        self.mgmt.get_policy_containers.side_effect = lambda ids: {"status_code": 404, "body": {"resources": []}}
        for resp in (self.update(dict(self.update_body, platform="")), self.delete({"rule_group_id": "rg-old"})):
            self.assertIn("no policy container", resp.body["error"])
            self.assert_nothing_changed(resp)

    def test_same_name_policy_is_a_conflict_without_a_stored_host_group(self):
        # it may be the legacy policy, enforcing: deleting the rule group and records would orphan it
        for key in ("old1", "old2"):
            self.rel()[key].pop("host_group_id")
        self.policies_named_p("pol-legacy")
        self.containers({"pol-legacy": []})
        resp = self.delete({"rule_group_id": "rg-old", "hostGroupId": "hg1"})
        self.assertEqual(resp.body["error"], (
            "Failed to look up the policy: 1 Falcon policy named 'P' (pol-legacy) may be the policy of rule group "
            "rg-old, but it cannot be confirmed: no host group is stored for the rule group. Check it in Falcon. "
            "Nothing was deleted."))
        self.assert_nothing_changed(resp)

    def test_same_name_policy_moved_to_another_host_group_is_a_conflict(self):
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": pid, "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": hg}]}
            for pid, hg in (("pol-a", "hg2"), ("pol-b", "hg3"))])
        self.containers({}, default=())
        for resp in (self.update(dict(self.update_body, platform="")), self.delete({"rule_group_id": "rg-old"})):
            self.assertIn("2 Falcon policies named 'P' (pol-a, pol-b) may be the policy of rule group rg-old, but none "
                          "can be confirmed: none is on its host group hg1. Check them in Falcon.", resp.body["error"])
            self.assert_nothing_changed(resp)
        health = policies.health_check(req(), None, self.logger).body
        entry = next(p for p in health["policies"] if p["rule_group_id"] == "rg-old")
        self.assertEqual((entry["policy_id"], entry["status"]), (None, "error"))
        self.assertIn("none can be confirmed", entry["issues"][0])

    def test_policy_on_the_stored_host_group_is_used_over_a_same_name_one_elsewhere(self):
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": pid, "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": hg}]}
            for pid, hg in (("pol-legacy", "hg1"), ("pol-elsewhere", "hg2"))])
        self.containers({"pol-legacy": [], "pol-elsewhere": []})
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.touched_policies(), {"pol-legacy"})
        self.assertEqual(set(self.rel()), {"other"})

    def test_leftover_legacy_record_without_a_host_group_never_matches_the_replacement(self):
        # the replacement holds rg-new, which this app tracks: it is never a candidate, so the
        # leftover record's policy is gone and the record is cleaned up
        self.update_without_the_old_policy()
        self.rel()["old2"].pop("host_group_id")
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-old"])
        self.assertEqual(set(self.rel()), {"other", "Games_rg-new_hg1"})


class PolicyLegacyPlatformTestCase(PolicyChangeBase):
    """Legacy records store no platform: it is read from their rule group in Falcon."""

    def setUp(self):
        super().setUp()
        self.pol.get_policies.side_effect = lambda ids: falcon_ok(
            [{"id": i, "enabled": True, "groups": [{"id": "hg1"}]} for i in ids])

    def legacy_records(self, **rule_groups):
        """Legacy records of "P" on hg1 (no policy_id, no platform), one per {category: rule group}."""
        self.store.data[REL] = {f"{category}_{rg}_hg1": {"category_name": category, "rule_group_id": rg,
                                                         "host_group_id": "hg1", "policy_name": "P"}
                                for category, rg in rule_groups.items()}

    def policies_named_p(self, **platforms):
        """query_combined_policies: an enabled "P" on hg1 per {policy id: platform}, all with empty containers."""
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": pid, "name": "P", "platform_name": platform, "enabled": True, "groups": [{"id": "hg1"}]}
            for pid, platform in platforms.items()])
        self.containers({}, default=())

    def health_entries(self):
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.code, 200)
        return {p["rule_group_id"]: p for p in resp.body["policies"]}

    def assert_mac_policy_gone(self):
        resp = self.delete({"rule_group_id": "rg-mac"})
        self.assertEqual((resp.code, resp.body["warnings"]), (200, []))
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-mac"])
        self.assertEqual(self.rel(), {})
        self.mgmt.get_rule_groups.assert_called_once_with(ids=["rg-mac"])

    def test_delete_never_takes_a_same_name_policy_on_another_platform(self):
        # the legacy Mac "P" of rg-mac was deleted by hand; an unrelated Windows "P" with an empty
        # container is on hg1: it is never disabled or deleted
        self.legacy_records(Games="rg-mac")
        self.rule_group_platforms["rg-mac"] = "mac"
        self.policies_named_p(**{"pol-win": "Windows"})
        self.assert_mac_policy_gone()

    def test_a_deleted_rule_group_still_gives_its_platform(self):
        # Falcon keeps returning a deleted rule group, with deleted: true and its platform
        self.legacy_records(Games="rg-mac")
        self.rule_group_platforms["rg-mac"] = "mac"
        self.deleted_rule_groups.add("rg-mac")
        self.policies_named_p(**{"pol-win": "Windows"})
        self.assert_mac_policy_gone()

    def two_unattached_policies(self):
        """A Windows "P" for rg-win and a Mac "P" for rg-mac, both on hg1, neither rule group ever attached."""
        self.legacy_records(Games="rg-win", News="rg-mac")
        self.rule_group_platforms.update({"rg-win": "windows", "rg-mac": "mac"})
        self.policies_named_p(**{"pol-win": "Windows", "pol-mac": "Mac"})

    def test_delete_resolves_same_name_policies_by_the_platform_of_their_rule_group(self):
        self.two_unattached_policies()
        for rule_group_id, policy_id in (("rg-mac", "pol-mac"), ("rg-win", "pol-win")):
            self.pol.reset_mock()
            resp = self.delete({"rule_group_id": rule_group_id})
            self.assertEqual(resp.code, 200)
            self.assertEqual(self.touched_policies(), {policy_id})
        self.assertEqual(self.rel(), {})

    def test_update_resolves_same_name_policies_by_the_platform_of_their_rule_group(self):
        self.two_unattached_policies()
        cases = (("rg-mac", "pol-mac", "Mac", "pol-win"), ("rg-win", "pol-win", "Windows", "pol-mac"))
        for rule_group_id, policy_id, platform_name, other_policy_id in cases:
            self.pol.reset_mock()
            resp = self.update(dict(self.update_body, ruleGroupId=rule_group_id, platform=""))
            self.assertEqual(resp.code, 200)
            self.assertEqual(self.pol.create_policies.call_args.kwargs["platform_name"], platform_name)
            self.pol.delete_policies.assert_called_once_with(ids=policy_id)
            self.assertNotIn(other_policy_id, self.touched_policies())

    def test_health_check_resolves_same_name_policies_by_the_platform_of_their_rule_group(self):
        self.two_unattached_policies()
        entries = self.health_entries()
        self.assertEqual({rg: e["policy_id"] for rg, e in entries.items()}, {"rg-win": "pol-win", "rg-mac": "pol-mac"})
        self.mgmt.get_rule_groups.assert_called_once()
        self.assertEqual(sorted(self.mgmt.get_rule_groups.call_args.kwargs["ids"]), ["rg-mac", "rg-win"])

    def assert_nothing_changed(self, resp, code):
        self.assertEqual(resp.code, code)
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertEqual(set(self.rel()), {"Games_rg-old_hg1"})
        self.assertNotIn("policy_id", self.rel()["Games_rg-old_hg1"])

    def test_rule_group_read_failure_changes_nothing(self):
        self.legacy_records(Games="rg-old")
        self.policies_named_p(**{"pol-legacy": "Windows"})  # would be taken once the platform is confirmed
        self.mgmt.get_rule_groups.side_effect = lambda ids: {"status_code": 500, "body": {"errors": [{"message": "down"}]}}
        for resp in (self.update(dict(self.update_body, platform="")), self.delete({"rule_group_id": "rg-old"})):
            self.assertIn("Failed to read rule group rg-old from Falcon: down. Nothing was", resp.body["error"])
            self.assert_nothing_changed(resp, 502)
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual((resp.code, resp.body["error"]), (502, "Failed to read rule groups from Falcon: down"))

    def test_rule_group_not_returned_leaves_the_platform_unconfirmed(self):
        self.legacy_records(Games="rg-old")
        self.policies_named_p(**{"pol-legacy": "Windows"})
        error = ("1 Falcon policy named 'P' (pol-legacy) may be the policy of rule group rg-old, but it cannot be "
                 "confirmed: Falcon did not return the rule group, so its platform is unknown. Check it in Falcon")
        not_returned = {"200 without it": lambda ids: falcon_ok([]),
                        "404": lambda ids: {"status_code": 404, "body": {"errors": [{"message": "not found"}]}}}
        for case, response in not_returned.items():
            with self.subTest(case):
                self.mgmt.get_rule_groups.side_effect = response
                for resp in (self.update(dict(self.update_body, platform="")), self.delete({"rule_group_id": "rg-old"})):
                    self.assertIn(error, resp.body["error"])
                    self.assert_nothing_changed(resp, 409)
                self.assertEqual(self.health_entries()["rg-old"]["issues"], [error])


class LegacyRuleFormatTestCase(PolicyChangeBase):
    """A legacy policy deployed the raw entries until a replacement exists (rule_format)."""

    def setUp(self):
        super().setUp()
        self.make_legacy()
        del self.rel()["other"]  # another legacy Games record would keep the raw entries deployed
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-legacy", "name": "P", "platform_name": "Windows", "enabled": True}])
        self.store.objects("domain", "v2.0")["Games"] = {"category": "Games", "domain": "*steam.com"}
        # the simulator only counts records whose rule group a policy holds in Falcon
        self.mgmt.get_rule_groups.side_effect = lambda ids: falcon_ok(
            [{"id": i, "deleted": False, "platform": "windows", "policy_ids": ["pol-legacy"]} for i in ids])

    def simulate(self, fqdn):
        return policies.simulate_policy(req(query={"fqdn": fqdn}), None, self.logger).body

    def test_failed_legacy_delete_keeps_simulating_the_raw_entries(self):
        self.assertEqual(self.simulate("mysteam.com")["rule"], "*steam.com")
        self.pol.delete_policies.return_value = {"status_code": 403, "body": {"errors": [{"message": "forbidden"}]}}
        resp = policies.delete_policy(req({"rule_group_id": "rg-old"}), None, self.logger)
        self.assertTrue(resp.body["error"].endswith("Nothing was deleted."))
        self.assertEqual(self.rel()["old1"]["policy_id"], "pol-legacy")  # the reference is kept
        self.assertNotIn("rule_format", self.rel()["old1"])
        self.assertEqual(self.simulate("mysteam.com")["rule"], "*steam.com")

    def test_rolled_back_legacy_update_keeps_simulating_the_raw_entries(self):
        self.pol.delete_policies.side_effect = lambda **k: (
            {"status_code": 403, "body": {"errors": [{"message": "forbidden"}]}} if k["ids"] == "pol-legacy" else OK)
        resp = self.update(dict(self.update_body, platform=""))
        self.assertIn("Rolled back.", resp.body["error"])
        self.assertNotIn("Games_rg-new_hg1", self.rel())
        self.assertEqual(self.simulate("mysteam.com")["rule"], "*steam.com")

    def test_successful_update_marks_the_new_records(self):
        self.assertEqual(self.update(dict(self.update_body, platform="")).code, 200)
        self.assertEqual(set(self.rel()), {"Games_rg-new_hg1"})
        self.assertEqual(self.rel()["Games_rg-new_hg1"]["rule_format"], "sanitized")
        self.assertFalse(self.simulate("mysteam.com")["found"])  # the replacement drops "*steam.com"


class PolicyDeleteTestCase(PolicyChangeBase):
    # --- delete-policy -----------------------------------------------------
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
        self.assertEqual(self.pol.perform_action.call_args_list, [
            call(action_name="disable", ids="pol-old"), call(action_name="enable", ids="pol-old")])

    def test_delete_policy_failure_reports_policy_left_disabled(self):
        self.pol.delete_policies.return_value = {"status_code": 500}
        self.pol.perform_action.side_effect = lambda **k: OK if k["action_name"] == "disable" else {"status_code": 500}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertIn("left disabled", resp.body["error"])
        self.assertTrue(resp.body["error"].endswith(
            "It must be enabled again manually in Falcon, or the delete retried."))
        self.assertTrue(self.rel()["old1"]["disabled_by_app"])

    def test_delete_left_disabled_without_marker_asks_for_manual_enable(self):
        # a retry only enables the policy again if the marker was saved: without it, the
        # response must not suggest retrying
        self.pol.delete_policies.return_value = {"status_code": 500}
        self.pol.perform_action.side_effect = lambda **k: OK if k["action_name"] == "disable" else {"status_code": 500}
        for failing in ({"old1"}, {"old1", "old2"}):
            with self.subTest(failing=failing):
                for key in ("old1", "old2"):
                    self.rel()[key].pop("disabled_by_app", None)
                self.store.fail_put = set(failing)
                resp = self.delete({"rule_group_id": "rg-old"})
                self.assertEqual(resp.code, 500)
                self.assertTrue(resp.body["error"].endswith(
                    "the policy was left disabled and could not be enabled again (CrowdStrike API returned status 500)."
                    " It must be enabled again manually in Falcon."), resp.body["error"])
                self.assertNotIn("retr", resp.body["error"])
                self.assertNotIn("disabled_by_app", self.rel()["old1"])
                self.assertIn("old1", str(self.logger.error.call_args_list))
        self.mgmt.delete_rule_groups.assert_not_called()

    def test_delete_policy_reads_the_policy_when_not_given(self):
        for state, expected, actions in (
                (falcon_ok([{"id": "pol-x", "enabled": True}]), (True, None, False), ["disable", "delete"]),
                (falcon_ok([{"id": "pol-x", "enabled": False}]), (True, None, False), ["delete"]),
                ({"status_code": 404, "body": {"resources": []}}, (True, None, False), []),
                ({"status_code": 429, "body": {"errors": [{"message": "slow"}]}}, (False, "slow", False), [])):
            with self.subTest(state=state):
                self.pol.reset_mock()
                self.pol.perform_action.return_value = OK
                self.pol.delete_policies.return_value = OK
                self.pol.get_policies.return_value = state
                self.assertEqual(policies._delete_policy(  # pylint: disable=protected-access
                    self.pol, "pol-x", "op", self.logger), expected)
                self.pol.get_policies.assert_called_once_with(ids=["pol-x"])
                done = [c.kwargs["action_name"] for c in self.pol.perform_action.call_args_list]
                done += ["delete"] * self.pol.delete_policies.call_count
                self.assertEqual(done, actions)

    def test_delete_retry_enables_again_a_policy_this_app_left_disabled(self):
        # first attempt: disable OK, delete 500, enable 500
        self.pol.delete_policies.return_value = {"status_code": 500}
        self.pol.perform_action.side_effect = lambda **k: OK if k["action_name"] == "disable" else {"status_code": 500}
        self.delete({"rule_group_id": "rg-old"})
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        self.pol.perform_action.reset_mock()

        # the retry fails again and still cannot enable it: it is still reported as left disabled
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertTrue(resp.body["error"].endswith(
            "It must be enabled again manually in Falcon, or the delete retried."))
        self.assertEqual(self.pol.perform_action.call_args_list, [call(action_name="enable", ids="pol-old")])

        # the next retry fails again but enables it: enforcing again, so the marker is cleared
        self.pol.perform_action.side_effect = None
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertTrue(resp.body["error"].endswith("Nothing was deleted."))
        self.assertNotIn("disabled_by_app", self.rel()["old1"])
        self.assertNotIn("disabled_by_app", self.rel()["old2"])

    def test_delete_failure_does_not_enable_policy_disabled_by_admin(self):
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        self.pol.delete_policies.return_value = {"status_code": 500}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertIn("Nothing was deleted", resp.body["error"])
        self.pol.perform_action.assert_not_called()

    def test_delete_state_read_error_deletes_nothing(self):
        for unreadable in ({"status_code": 500}, falcon_ok([])):  # a 200 without the policy is not "gone"
            self.pol.get_policies.return_value = unreadable
            resp = self.delete({"rule_group_id": "rg-old"})
            self.assertEqual(resp.code, 502)
            self.assertIn("Nothing was deleted", resp.body["error"])
        self.pol.perform_action.assert_not_called()
        self.pol.delete_policies.assert_not_called()
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertIn("old1", self.rel())

    def test_delete_policy_already_gone_in_falcon(self):
        self.pol.get_policies.return_value = {"status_code": 404, "body": {"resources": []}}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_not_called()
        self.assertEqual(set(self.rel()), {"other"})

    def test_delete_disable_failure_deletes_nothing(self):
        self.pol.perform_action.return_value = {"status_code": 500}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 500)
        self.pol.delete_policies.assert_not_called()
        self.assertIn("old1", self.rel())

    def test_delete_rule_group_failure_keeps_relations_for_retry(self):
        self.mgmt.delete_rule_groups.return_value = {"status_code": 500}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.body["error"], "Policy deleted, but the rule group could not be deleted: "
                                             "CrowdStrike API returned status 500. Please retry.")
        self.assertIn("old1", self.rel())

    def test_delete_rule_group_failure_without_a_policy_mentions_none(self):
        self.pol.get_policies.return_value = {"status_code": 404, "body": {"resources": []}}
        self.mgmt.delete_rule_groups.return_value = {"status_code": 500}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.body["error"], "No policy for this rule group was found in Falcon, and the rule group "
                                             "could not be deleted: CrowdStrike API returned status 500. "
                                             "Nothing was deleted; please retry.")
        self.pol.delete_policies.assert_not_called()
        self.assertEqual(set(self.rel()), {"old1", "old2", "other"})

    def test_delete_failure_reports_marker_that_could_not_be_cleared(self):
        # the policy this app left disabled is enabled again, but the marker stays
        for key in ("old1", "old2"):
            self.rel()[key]["disabled_by_app"] = True
        self.pol.get_policies.return_value = falcon_ok([{"id": "pol-old", "enabled": False}])
        self.pol.delete_policies.return_value = {"status_code": 500}
        self.store.fail_put.add("old1")
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertTrue(resp.body["error"].endswith(
            "Nothing was deleted. The policy's records still say this app disabled it (disabled_by_app could not "
            "be cleared), so a later failed delete could enable it again even if it has been disabled in Falcon."),
            resp.body["error"])
        self.assertEqual(self.pol.perform_action.call_args_list, [call(action_name="enable", ids="pol-old")])
        self.assertTrue(self.rel()["old1"]["disabled_by_app"])

    def test_delete_retry_treats_already_deleted_policy_as_gone(self):
        self.pol.perform_action.return_value = {"status_code": 404}
        self.pol.delete_policies.return_value = {"status_code": 404}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 200)
        self.assertEqual(set(self.rel()), {"other"})

    def test_delete_legacy_record_resolves_policy_by_name(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([dict(self.legacy_policy)])
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-legacy")
        self.pol.get_policies.assert_not_called()

    def test_delete_legacy_retry_never_resolves_the_name_again(self):
        # the first attempt deletes the Windows "P" but not its rule group; on the retry only an
        # unrelated Mac "P" is left in Falcon, and it must not be deleted
        self.make_legacy()
        win = {"id": "pol-win", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]}
        mac = {"id": "pol-mac", "name": "P", "platform_name": "Mac", "enabled": True, "groups": [{"id": "hg-mac"}]}
        self.pol.query_combined_policies.return_value = falcon_ok([win, mac])
        self.containers({"pol-win": ["rg-old"], "pol-mac": ["rg-mac"]})
        self.mgmt.delete_rule_groups.return_value = {"status_code": 500}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 500)
        self.assertEqual((self.rel()["old1"]["policy_id"], self.rel()["old1"]["platform"]), ("pol-win", "windows"))

        self.pol.query_combined_policies.return_value = falcon_ok([mac])
        self.pol.get_policies.return_value = {"status_code": 404, "body": {"resources": []}}
        self.mgmt.delete_rule_groups.return_value = OK
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.assertEqual([c.kwargs["ids"] for c in self.pol.delete_policies.call_args_list], ["pol-win"])

    def test_delete_legacy_policy_id_write_failure_deletes_nothing(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([dict(self.legacy_policy)])
        self.store.fail_put.add("old2")
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertIn("Nothing was deleted", resp.body["error"])
        self.pol.perform_action.assert_not_called()
        self.pol.delete_policies.assert_not_called()

    def test_retry_completes_a_partially_stored_policy_id(self):
        self.make_legacy()
        self.rel()["Social_rg-old_hg1"] = {"category_name": "Social", "rule_group_id": "rg-old", "host_group_id": "hg1",
                                           "policy_name": "P"}
        self.pol.query_combined_policies.return_value = falcon_ok([dict(self.legacy_policy, groups=[{"id": "hg1"}])])
        self.store.fail_put.add("old2")
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual((resp.code, resp.body["error"]), (500, "Failed to record the policy id. Nothing was deleted."))
        self.assertEqual({k for k in ("old1", "old2", "Social_rg-old_hg1") if "policy_id" in self.rel()[k]},
                         {"old1", "Social_rg-old_hg1"})

        # the retry completes the write, then Falcon refuses the delete: the records stay
        self.store.fail_put.clear()
        self.store.calls.clear()
        self.pol.get_policies.return_value = falcon_ok([dict(self.legacy_policy)])
        self.pol.delete_policies.return_value = {"status_code": 403, "body": {"errors": [{"message": "forbidden"}]}}
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertTrue(resp.body["error"].endswith("Nothing was deleted."))
        self.assertEqual([c[2] for c in self.store.calls if c[0] == "put"], ["old2"])
        self.assertEqual({self.rel()[k].get("policy_id") for k in ("old1", "old2", "Social_rg-old_hg1")},
                         {"pol-legacy"})

        # health-check counts the policy once
        self.pol.get_policies.side_effect = lambda ids: falcon_ok(
            [{"id": i, "enabled": True, "groups": [{"id": "hg1"}]} for i in ids])
        health = policies.health_check(req(), None, self.logger).body
        self.assertEqual([p["policy_id"] for p in health["policies"] if p["rule_group_id"] == "rg-old"], ["pol-legacy"])

    def test_leftover_legacy_record_never_matches_the_replacement(self):
        # update-policy renames the replacement to "P" on the same host group, and one old record
        # cannot be removed: deleting that leftover must not delete the replacement
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-legacy", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]}])
        self.store.fail_delete.add("old2")
        resp = self.update(dict(self.update_body, platform=""))
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.body["warnings"][0], "1 record of the previous rule group rg-old could not be removed; "
                                                   "delete it from Firewall Rules")
        self.assertEqual(self.rel()["old2"]["policy_id"], "pol-legacy")

        self.store.fail_delete.clear()
        self.pol.delete_policies.reset_mock()
        self.pol.get_policies.return_value = {"status_code": 404, "body": {"resources": []}}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_not_called()
        self.assertIn("Games_rg-new_hg1", self.rel())

    def test_legacy_name_lookup_never_takes_a_policy_holding_untracked_rule_groups(self):
        # no policy_id could be stored (the old policy no longer existed), and the name now
        # belongs to a policy on the same host group holding a rule group no record names (e.g. a
        # replacement whose records could not be written): it cannot be confirmed as the old one
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-new", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]}])
        self.containers({"pol-new": ["rg-new"]})
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 409)
        self.assertIn("pol-new", resp.body["error"])
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertEqual({"old1", "old2"} - set(self.rel()), set())

    def test_partial_relationship_read_changes_nothing(self):
        self.store.fail_get.add("old2")
        for resp in (self.delete({"rule_group_id": "rg-old"}), self.update()):
            self.assertEqual(resp.code, 500)
            self.assertIn("could not be read", resp.body["error"])
        self.pol.create_policies.assert_not_called()
        self.pol.delete_policies.assert_not_called()
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertEqual(set(self.rel()), {"old1", "old2", "other"})

    def add_record(self, key, rule_group_id):
        self.rel()[key] = {"category_name": "News", "rule_group_id": rule_group_id, "host_group_id": "hg9",
                           "policy_name": "R"}

    def test_failed_read_of_another_rule_group_record_is_ignored(self):
        # the key names its rule group, so a record of rg-x is never read for rg-old
        self.add_record("News_rg-x_hg9", "rg-x")
        self.store.fail_get.add("News_rg-x_hg9")
        self.assertEqual(self.update().code, 200)
        self.assertEqual(self.delete({"rule_group_id": "rg-new"}).code, 200)
        self.assertNotIn(("get", "relationship", "News_rg-x_hg9"), self.store.calls)
        self.assertIn("News_rg-x_hg9", self.rel())

    def test_failed_read_of_another_rule_group_record_does_not_block_legacy_records(self):
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([dict(self.legacy_policy)])
        self.add_record("News_rg-x_hg9", "rg-x")
        self.store.fail_get.add("News_rg-x_hg9")
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_called_once_with(ids="pol-legacy")

    def test_failed_read_of_an_own_record_changes_nothing(self):
        self.add_record("News_rg-old_hg1", "rg-old")
        self.store.fail_get.add("News_rg-old_hg1")
        for resp in (self.delete({"rule_group_id": "rg-old"}), self.update()):
            self.assertEqual(resp.code, 500)
            self.assertIn("could not be read. Nothing was", resp.body["error"])
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_not_called()
        self.assertEqual(set(self.rel()), {"old1", "old2", "other", "News_rg-old_hg1"})

    def test_truncated_relationship_listing_changes_nothing(self):
        with patch.object(policies, "RELATIONSHIP_PAGE_SIZE", 2), patch.object(policies, "RELATIONSHIP_MAX_PAGES", 1):
            for resp in (self.delete({"rule_group_id": "rg-old"}), self.update()):
                self.assertEqual(resp.code, 500)
                self.assertIn("could not all be listed", resp.body["error"])
        self.pol.create_policies.assert_not_called()
        self.assertEqual(self.touched_policies(), set())
        self.assertEqual(set(self.rel()), {"old1", "old2", "other"})

    def test_delete_counts_only_successful_deletes(self):
        self.store.fail_delete.add("old2")
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.body["relationsDeleted"], 1)
        self.assertEqual(resp.body["warnings"], [
            "1 relationship record could not be removed, so this rule group is still listed in Firewall Rules: "
            "delete it again to finish the cleanup."])
        self.assertIn("old2", self.rel())
        self.pol.query_combined_policies.return_value = falcon_ok([])  # "other" is legacy; its policy is gone
        resp = self.delete({"rule_group_id": "rg-other"})
        self.assertEqual((resp.code, resp.body["warnings"]), (200, []))

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
        self.assertEqual(self.pol.query_combined_policies.call_args.kwargs["filter"], "name:['o\\'brien\\' OR name:*']")
        self.assertEqual(resp.body["policies"][0]["issues"], ["Policy not found in Falcon"])

    def test_health_check_resolves_legacy_names_in_batches(self):
        self.store.data[REL] = {f"r{i:03d}": {"policy_name": f"N{i}", "rule_group_id": "rg"} for i in range(150)}
        self.pol.query_combined_policies.side_effect = lambda **k: falcon_ok(
            [{"id": f"id-{n.strip(chr(39))}", "name": n.strip(chr(39))} for n in k["filter"][6:-1].split(",")])
        self.pol.get_policies.side_effect = lambda ids: falcon_ok([{"id": i, "enabled": True, "groups": [1]} for i in ids])
        self.mgmt.get_policy_containers.side_effect = lambda ids: falcon_ok(
            [{"policy_id": i, "enforce": True, "rule_group_ids": ["rg"]} for i in ids])

        resp = policies.health_check(req(), None, self.logger)

        self.assertEqual(self.pol.query_combined_policies.call_count, 8)  # 150 names, 20 per query
        self.assertEqual(resp.body["healthy_count"], 150)

    def test_health_check_legacy_name_skips_policies_without_the_rule_group(self):
        self.store.data[REL] = {"a": {"policy_name": "A", "rule_group_id": "rg-a"},
                                "b": {"policy_id": "p1", "policy_name": "A", "rule_group_id": "rg-b"}}
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "p1", "name": "A"}])
        self.pol.get_policies.return_value = falcon_ok([{"id": "p1", "enabled": True, "groups": [1]}])
        self.mgmt.get_policy_containers.return_value = falcon_ok(
            [{"policy_id": "p1", "enforce": True, "rule_group_ids": ["rg-b"]}])
        resp = policies.health_check(req(), None, self.logger)
        legacy = next(p for p in resp.body["policies"] if p["policy_id"] is None)
        self.assertEqual(legacy["issues"], ["Policy not found in Falcon"])

    def test_health_check_reports_ambiguous_legacy_names(self):
        self.store.data[REL] = {"a": {"policy_name": "A", "rule_group_id": "rg-a"}}
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "p1", "name": "A"}, {"id": "p2", "name": "A"}])
        self.mgmt.get_policy_containers.return_value = falcon_ok([
            {"policy_id": "p1", "rule_group_ids": ["rg-a"]}, {"policy_id": "p2", "rule_group_ids": ["rg-a"]}])
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.body["policies"][0]["issues"], ["2 Falcon policies named 'A' hold rule group rg-a"])
        self.pol.get_policies.assert_not_called()

    def test_health_check_legacy_container_error_is_502(self):
        self.store.data[REL] = {"a": {"policy_name": "A", "rule_group_id": "rg-a"}}
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "p1", "name": "A"}])
        self.mgmt.get_policy_containers.return_value = {"status_code": 500, "body": {"errors": [{"message": "down"}]}}
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.code, 502)
        self.assertIn("down", resp.body["error"])
        self.pol.get_policies.assert_not_called()

    def test_health_check_legacy_lookup_error_is_502(self):
        self.store.data[REL] = {"a": {"policy_name": "A"}}
        self.pol.query_combined_policies.return_value = {"status_code": 429, "body": {"errors": [{"message": "slow"}]}}
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.code, 502)
        self.assertIn("slow", resp.body["error"])

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

    def test_health_check_reports_the_readable_records_when_some_cannot_be_read(self):
        self.store.data[REL] = {"a": {"policy_id": "p1", "policy_name": "A"}, "b": {"policy_id": "p2", "policy_name": "B"}}
        self.store.fail_get.add("b")
        self.pol.get_policies.return_value = falcon_ok([{"id": "p1", "enabled": True, "groups": [1]}])
        self.mgmt.get_policy_containers.return_value = falcon_ok(
            [{"policy_id": "p1", "enforce": True, "rule_group_ids": ["r"]}])
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.code, 200)
        self.assertEqual([(p["policy_id"], p["status"]) for p in resp.body["policies"]], [("p1", "healthy")])
        self.assertEqual((resp.body["incomplete"], resp.body["healthy"]), (True, False))
        self.assertEqual(resp.body["warnings"], ["1 relationship record could not be read, so its policy may be "
                                                 "missing from this report"])
        self.pol.get_policies.assert_called_once_with(ids=["p1"])

    def test_health_check_truncated_relationship_read_is_incomplete(self):
        # keys are listed alphabetically: two per page and one page leaves "c" unread
        self.store.data[REL] = {k: {"policy_id": f"p-{k}", "policy_name": k} for k in ("a", "b", "c")}
        self.pol.get_policies.side_effect = lambda ids: falcon_ok([{"id": i, "enabled": True, "groups": [1]} for i in ids])
        self.mgmt.get_policy_containers.side_effect = lambda ids: falcon_ok(
            [{"policy_id": i, "enforce": True, "rule_group_ids": ["r"]} for i in ids])
        with patch.object(policies, "read_all_objects", partial(read_all_objects, page_size=2, max_pages=1)):
            resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.code, 200)
        self.assertEqual([p["policy_id"] for p in resp.body["policies"]], ["p-a", "p-b"])
        self.assertEqual((resp.body["incomplete"], resp.body["healthy"]), (True, False))
        self.assertEqual(resp.body["warnings"], ["only the first 2 relationship records could be read, so some "
                                                 "policies may be missing from this report"])

    def test_health_check_complete_report_has_no_warnings(self):
        self.store.data[REL] = {"a": {"policy_id": "p1", "policy_name": "A"}}
        self.pol.get_policies.return_value = falcon_ok([{"id": "p1", "enabled": True, "groups": [1]}])
        self.mgmt.get_policy_containers.return_value = falcon_ok(
            [{"policy_id": "p1", "enforce": True, "rule_group_ids": ["r"]}])
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual((resp.body["healthy"], resp.body["incomplete"], resp.body["warnings"]), (True, False, []))

    def test_health_check_relationship_listing_failure_is_an_error(self):
        # no record could be read at all: there is no subset to report
        self.store.list_status = 500
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual((resp.code, resp.body["error"]), (500, "Failed to read relationships"))
        self.pol.get_policies.assert_not_called()

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

    def test_check_enforcement_reports_falcon_errors(self):
        self.mgmt.get_policy_containers.return_value = {"status_code": 429, "body": {"errors": [{"message": "slow"}]}}
        resp = policies.check_enforcement(req(query={"policy_id": "p1"}), None, self.logger)
        self.assertEqual(resp.code, 502)
        self.assertIn("slow", resp.body["error"])

        for not_found in ({"status_code": 404, "body": {"resources": []}}, falcon_ok([])):
            self.mgmt.get_policy_containers.return_value = not_found
            self.assertEqual(policies.check_enforcement(req(query={"policy_id": "p1"}), None, self.logger).code, 404)


class AnalyticsTruncatedTestCase(unittest.TestCase):
    def run_handler(self, mgmt, query=None):
        with patch.object(analytics, "get_client", return_value=mgmt):
            return analytics.get_domain_analytics(req(query=query), None, MagicMock())

    def window_days(self, mgmt):
        """Days between now and the start of the event filter sent to Falcon."""
        time_filter = mgmt.query_events.call_args.kwargs["parameters"]["filter"]
        start = datetime.fromisoformat(time_filter.split("'")[1])
        return round((datetime.now(timezone.utc) - start).total_seconds() / 86400)

    def test_days_defaults_to_15(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok([])
        resp = self.run_handler(mgmt)
        self.assertEqual((resp.code, resp.body["days"]), (200, 15))
        self.assertEqual(self.window_days(mgmt), 15)

    def test_days_from_query(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok([])
        resp = self.run_handler(mgmt, {"days": "30"})
        self.assertEqual(resp.body["days"], 30)
        self.assertEqual(self.window_days(mgmt), 30)

    def test_invalid_days_is_rejected(self):
        for value in ("0", "91", "-5", "abc", "1.5"):
            mgmt = MagicMock()
            self.assertEqual(self.run_handler(mgmt, {"days": value}).code, 400, value)
            mgmt.query_events.assert_not_called()

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

    def test_error_when_first_page_fails(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = {"status_code": 403, "body": {"errors": [{"message": "missing scope"}]}}
        resp = self.run_handler(mgmt)
        self.assertEqual(resp.code, 502)
        self.assertIn("missing scope", resp.body["error"])

        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok(["e1"])
        mgmt.get_events.return_value = {"status_code": 500}
        self.assertEqual(self.run_handler(mgmt).code, 502)

        mgmt = MagicMock()
        mgmt.query_events.side_effect = RuntimeError("boom")
        self.assertEqual(self.run_handler(mgmt).code, 502)

    def test_error_when_no_events_could_be_read_before_an_empty_page(self):
        # exactly 500 events: page 1's get_events fails and page 2 would come back empty
        mgmt = MagicMock()
        mgmt.query_events.side_effect = [falcon_ok([f"e{i}" for i in range(500)]), falcon_ok([])]
        mgmt.get_events.return_value = {"status_code": 403, "body": {"errors": [{"message": "missing scope"}]}}
        resp = self.run_handler(mgmt)
        self.assertEqual(resp.code, 502)
        self.assertIn("missing scope", resp.body["error"])

    def test_stops_at_first_get_events_error(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok([f"e{i}" for i in range(500)])
        mgmt.get_events.return_value = {"status_code": 429}
        self.assertEqual(self.run_handler(mgmt).code, 502)
        self.assertEqual((mgmt.query_events.call_count, mgmt.get_events.call_count), (1, 1))

    def test_truncated_on_api_error_after_first_page(self):
        mgmt = MagicMock()
        mgmt.query_events.side_effect = [falcon_ok([f"e{i}" for i in range(500)]), {"status_code": 500}]
        mgmt.get_events.return_value = falcon_ok([self.event])
        resp = self.run_handler(mgmt)
        self.assertEqual(resp.code, 200)
        self.assertTrue(resp.body["truncated"])
        self.assertEqual(resp.body["visualization_data"]["summary"]["total_blocks"], 1)

    def test_empty_window_is_not_an_error(self):
        mgmt = MagicMock()
        mgmt.query_events.return_value = falcon_ok([])
        resp = self.run_handler(mgmt)
        self.assertEqual(resp.code, 200)
        self.assertFalse(resp.body["truncated"])


if __name__ == "__main__":
    unittest.main()

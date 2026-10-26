"""Tests for policy lifecycle (create/update/delete/list/health), helpers and analytics."""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name,too-many-lines

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

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
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy", "name": "P", "enabled": True}])
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

    def test_update_missing_name_or_host_group_is_rejected(self):
        for field_name, body_key in (("policy_name", "policyName"), ("host_group_id", "hostGroupId")):
            stored = {key: self.rel()[key].pop(field_name) for key in ("old1", "old2")}
            resp = self.update(dict(self.update_body, **{body_key: ""}))
            self.assertEqual(resp.code, 400, field_name)
            for key, value in stored.items():
                self.rel()[key][field_name] = value
        self.pol.create_policies.assert_not_called()

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
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy", "name": "P"}])
        resp = self.update(dict(self.update_body, platform="windows"))
        self.assertEqual(resp.code, 400)
        self.pol.create_policies.assert_not_called()

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

    def test_health_check_resolves_same_name_legacy_policies_by_rule_group(self):
        # one entry per policy name: the first record ("a") is checked, and resolves to p2
        self.store.data[REL] = {"a": {"policy_name": "A", "host_group_id": "hg1", "rule_group_id": "rg-a"},
                                "b": {"policy_name": "A", "host_group_id": "hg1", "rule_group_id": "rg-b"}}
        self.pol.query_combined_policies.return_value = falcon_ok([
            {"id": "p1", "name": "A", "platform_name": "Windows", "groups": [{"id": "hg1"}]},
            {"id": "p2", "name": "A", "platform_name": "Mac", "groups": [{"id": "hg1"}]}])
        self.pol.get_policies.return_value = falcon_ok([{"id": "p2", "enabled": True, "groups": [{"id": "hg1"}]}])
        self.mgmt.get_policy_containers.side_effect = None
        self.mgmt.get_policy_containers.return_value = falcon_ok([
            {"policy_id": "p1", "enforce": True, "rule_group_ids": ["rg-b"]},
            {"policy_id": "p2", "enforce": True, "rule_group_ids": ["rg-a"]}])
        resp = policies.health_check(req(), None, self.logger)
        self.assertEqual(resp.body["policies"][0]["policy_id"], "p2")
        self.assertEqual(resp.body["healthy_count"], 1)

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


class LegacyRuleFormatTestCase(PolicyChangeBase):
    """A legacy policy deployed the raw entries until a replacement exists (rule_format)."""

    def setUp(self):
        super().setUp()
        self.make_legacy()
        del self.rel()["other"]  # another legacy Games record would keep the raw entries deployed
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-legacy", "name": "P", "platform_name": "Windows", "enabled": True}])
        self.store.objects("domain", "v2.0")["Games"] = {"category": "Games", "domain": "*steam.com"}

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
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy", "name": "P", "enabled": True}])
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
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy", "name": "P", "enabled": True}])
        self.store.fail_put.add("old2")
        resp = self.delete({"rule_group_id": "rg-old"})
        self.assertEqual(resp.code, 500)
        self.assertIn("Nothing was deleted", resp.body["error"])
        self.pol.perform_action.assert_not_called()
        self.pol.delete_policies.assert_not_called()

    def test_leftover_legacy_record_never_matches_the_replacement(self):
        # update-policy renames the replacement to "P" on the same host group, and one old record
        # cannot be removed: deleting that leftover must not delete the replacement
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-legacy", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]}])
        self.store.fail_delete.add("old2")
        resp = self.update(dict(self.update_body, platform=""))
        self.assertEqual(resp.code, 200)
        self.assertIn("could not be removed", resp.body["warnings"][0])
        self.assertEqual(self.rel()["old2"]["policy_id"], "pol-legacy")

        self.store.fail_delete.clear()
        self.pol.delete_policies.reset_mock()
        self.pol.get_policies.return_value = {"status_code": 404, "body": {"resources": []}}
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.pol.delete_policies.assert_not_called()
        self.assertIn("Games_rg-new_hg1", self.rel())

    def test_legacy_name_lookup_skips_policies_without_the_rule_group(self):
        # no policy_id could be stored (the old policy no longer existed), and the name now
        # belongs to the replacement, on the same host group but holding another rule group
        self.make_legacy()
        self.pol.query_combined_policies.return_value = falcon_ok(
            [{"id": "pol-new", "name": "P", "platform_name": "Windows", "enabled": True, "groups": [{"id": "hg1"}]}])
        self.containers({"pol-new": ["rg-new"]})
        self.assertEqual(self.delete({"rule_group_id": "rg-old"}).code, 200)
        self.assertEqual(self.touched_policies(), set())
        self.mgmt.delete_rule_groups.assert_called_once_with(ids=["rg-old"])

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
        self.pol.query_combined_policies.return_value = falcon_ok([{"id": "pol-legacy", "name": "P", "enabled": True}])
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

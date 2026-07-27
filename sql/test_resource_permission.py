import json
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase

from common.utils.const import WorkflowStatus, WorkflowType
from sql.models import (
    ResourceGroup,
    ResourcePermissionApply,
    Users,
    WorkflowAudit,
    WorkflowAuditSetting,
)
from sql.resource_permission import resource_permission_audit_callback


class TestResourcePermission(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = Users.objects.create_user(
            username="applicant",
            password="password",
            display="申请人",
        )
        self.other_user = Users.objects.create_user(
            username="other",
            password="password",
            display="其他用户",
        )
        permission = Permission.objects.get(codename="resource_permission_apply")
        self.user.user_permissions.add(permission)
        self.other_user.user_permissions.add(permission)
        self.resource_group = ResourceGroup.objects.create(group_name="目标资源组")
        self.deleted_group = ResourceGroup.objects.create(
            group_name="已删除资源组",
            is_deleted=1,
        )
        self.audit_group = Group.objects.create(name="资源权限审批组")
        WorkflowAuditSetting.objects.create(
            group_id=self.resource_group.group_id,
            group_name=self.resource_group.group_name,
            workflow_type=WorkflowType.RESOURCE_PERMISSION,
            audit_auth_groups=str(self.audit_group.id),
        )
        self.client.force_login(self.user)

    def _submit(self, **kwargs):
        data = {
            "group_id": self.resource_group.group_id,
            "title": "申请资源组权限",
            "reason": "工作需要",
            "user_name": self.other_user.username,
        }
        data.update(kwargs)
        with patch("sql.resource_permission.async_task"):
            return self.client.post("/resource-permission/apply/", data=data)

    def test_user_without_resource_group_can_submit_and_identity_cannot_be_forged(self):
        response = self._submit()
        self.assertEqual(json.loads(response.content)["status"], 0)
        apply_info = ResourcePermissionApply.objects.get()
        self.assertEqual(apply_info.user_name, self.user.username)
        self.assertEqual(apply_info.group_id, self.resource_group.group_id)
        self.assertTrue(
            WorkflowAudit.objects.filter(
                workflow_id=apply_info.apply_id,
                workflow_type=WorkflowType.RESOURCE_PERMISSION,
            ).exists()
        )

    def test_only_active_resource_groups_are_returned(self):
        response = self.client.post("/resource-permission/groups/")
        rows = json.loads(response.content)["rows"]
        self.assertEqual(
            rows,
            [{"group_id": self.resource_group.group_id, "group_name": "目标资源组"}],
        )

    def test_invalid_deleted_owned_and_duplicate_application_are_rejected(self):
        self.assertEqual(
            json.loads(self._submit(group_id="invalid").content)["status"],
            1,
        )
        self.assertEqual(
            json.loads(self._submit(group_id=self.deleted_group.group_id).content)["status"],
            1,
        )
        self.user.resource_group.add(self.resource_group)
        self.assertEqual(json.loads(self._submit().content)["msg"], "你已拥有该资源组权限")
        self.user.resource_group.remove(self.resource_group)
        ResourcePermissionApply.objects.create(
            group_id=self.resource_group.group_id,
            group_name=self.resource_group.group_name,
            title="已有申请",
            user_name=self.user.username,
            user_display=self.user.display,
            status=WorkflowStatus.WAITING,
        )
        self.assertEqual(json.loads(self._submit().content)["msg"], "该资源组已有待审批申请")

    def test_detail_has_object_level_visibility(self):
        apply_info = ResourcePermissionApply.objects.create(
            group_id=self.resource_group.group_id,
            group_name=self.resource_group.group_name,
            title="申请",
            user_name=self.user.username,
            user_display=self.user.display,
            status=WorkflowStatus.WAITING,
            audit_auth_groups=str(self.audit_group.id),
        )
        WorkflowAudit.objects.create(
            group_id=self.resource_group.group_id,
            group_name=self.resource_group.group_name,
            workflow_id=apply_info.apply_id,
            workflow_type=WorkflowType.RESOURCE_PERMISSION,
            workflow_title=apply_info.title,
            audit_auth_groups=str(self.audit_group.id),
            current_audit=str(self.audit_group.id),
            next_audit="-1",
            current_status=WorkflowStatus.WAITING,
            create_user=self.user.username,
            create_user_display=self.user.display,
        )
        self.assertEqual(
            self.client.get(f"/resourcepermission/{apply_info.apply_id}/").status_code,
            200,
        )
        self.client.force_login(self.other_user)
        self.assertEqual(
            self.client.get(f"/resourcepermission/{apply_info.apply_id}/").status_code,
            403,
        )

    def test_pass_callback_grants_permission_idempotently(self):
        apply_info = ResourcePermissionApply.objects.create(
            group_id=self.resource_group.group_id,
            group_name=self.resource_group.group_name,
            title="申请",
            user_name=self.user.username,
            user_display=self.user.display,
            status=WorkflowStatus.WAITING,
        )
        resource_permission_audit_callback(
            apply_info.apply_id,
            WorkflowStatus.PASSED,
        )
        resource_permission_audit_callback(
            apply_info.apply_id,
            WorkflowStatus.PASSED,
        )
        apply_info.refresh_from_db()
        self.assertEqual(apply_info.status, WorkflowStatus.PASSED)
        self.assertEqual(
            self.user.resource_group.filter(pk=self.resource_group.pk).count(),
            1,
        )

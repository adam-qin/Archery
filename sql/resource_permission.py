# -*- coding: UTF-8 -*-
"""资源组权限申请业务。"""
import simplejson as json
from django.contrib.auth.decorators import permission_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from common.utils.const import WorkflowStatus
from common.utils.extend_json_encoder import ExtendJSONEncoder
from sql.models import ResourceGroup, ResourcePermissionApply, Users
from sql.notify import notify_for_resource_permission
from sql.utils.workflow_audit import AuditException, get_auditor


def _response(status=0, msg="ok", data=None):
    return HttpResponse(
        json.dumps({"status": status, "msg": msg, "data": data or []}),
        content_type="application/json",
    )


@permission_required("sql.resource_permission_apply", raise_exception=True)
@require_POST
def resource_group_list(request):
    groups = ResourceGroup.objects.filter(is_deleted=0).order_by("group_name")
    return HttpResponse(
        json.dumps(
            {"total": groups.count(), "rows": list(groups.values("group_id", "group_name"))},
            cls=ExtendJSONEncoder,
        ),
        content_type="application/json",
    )


@permission_required("sql.resource_permission_apply", raise_exception=True)
@require_POST
def resource_permission_apply_list(request):
    user = request.user
    search = request.POST.get("search", "")
    queryset = ResourcePermissionApply.objects.all()
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(user_display__icontains=search)
            | Q(group_name__icontains=search)
        )
    if user.is_superuser:
        pass
    elif user.has_perm("sql.query_review"):
        queryset = queryset.filter(group_id__in=user.resource_group.values_list("group_id", flat=True))
    else:
        queryset = queryset.filter(user_name=user.username)
    try:
        offset = max(int(request.POST.get("offset", 0)), 0)
        page_size = min(max(int(request.POST.get("limit", 10)), 1), 100)
    except (TypeError, ValueError):
        return _response(1, "分页参数错误")
    limit = offset + page_size
    rows = queryset.order_by("-apply_id")[offset:limit].values(
        "apply_id", "title", "reason", "group_name", "user_display", "status", "create_time"
    )
    return HttpResponse(
        json.dumps({"total": queryset.count(), "rows": list(rows)}, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


def resource_permission_audit_callback(apply_id, workflow_status):
    with transaction.atomic():
        apply_info = ResourcePermissionApply.objects.select_for_update().get(apply_id=apply_id)
        apply_info.status = workflow_status
        apply_info.save(update_fields=["status", "sys_time"])
        if workflow_status == WorkflowStatus.PASSED:
            user = Users.objects.select_for_update().get(username=apply_info.user_name)
            group = ResourceGroup.objects.get(group_id=apply_info.group_id, is_deleted=0)
            user.resource_group.add(group)


@permission_required("sql.resource_permission_apply", raise_exception=True)
@require_POST
def resource_permission_apply(request):
    if not request.user.is_authenticated:
        return _response(1, "请先登录")
    try:
        group_id = int(request.POST["group_id"])
    except (KeyError, TypeError, ValueError):
        return _response(1, "资源组参数错误")
    title = request.POST.get("title", "").strip()
    reason = request.POST.get("reason", "").strip()
    if not title:
        return _response(1, "请填写申请标题")
    if len(title) > 50:
        return _response(1, "申请标题不能超过50个字符")
    if len(reason) > 500:
        return _response(1, "申请理由不能超过500个字符")
    try:
        with transaction.atomic():
            user = Users.objects.select_for_update().get(pk=request.user.pk)
            group = ResourceGroup.objects.select_for_update().get(
                group_id=group_id, is_deleted=0
            )
            if user.resource_group.filter(group_id=group_id).exists():
                return _response(1, "你已拥有该资源组权限")
            if ResourcePermissionApply.objects.filter(
                user_name=user.username, group_id=group_id, status=WorkflowStatus.WAITING
            ).exists():
                return _response(1, "该资源组已有待审批申请")
            apply_info = ResourcePermissionApply.objects.create(
                group_id=group.group_id,
                group_name=group.group_name,
                title=title,
                reason=reason,
                user_name=user.username,
                user_display=user.display,
                status=WorkflowStatus.WAITING,
            )
            auditor = get_auditor(workflow=apply_info)
            auditor.create_audit()
            resource_permission_audit_callback(
                apply_info.apply_id, auditor.audit.current_status
            )
            transaction.on_commit(
                lambda: async_task(
                    notify_for_resource_permission,
                    workflow_audit=auditor.audit,
                    timeout=60,
                    task_name=f"resource-permission-apply-{apply_info.apply_id}",
                )
            )
    except (ResourceGroup.DoesNotExist, Users.DoesNotExist):
        return _response(1, "资源组或用户不存在")
    except IntegrityError:
        return _response(1, "申请提交冲突，请刷新后重试")
    except AuditException as exc:
        return _response(1, str(exc))
    return _response()

# -*- coding: UTF-8 -*-
"""
资源组权限申请模块
用于没有资源组权限的用户申请加入资源组
审批通过后自动将用户关联到对应的资源组
"""

import logging
import simplejson as json
from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from common.utils.const import WorkflowStatus, WorkflowType, WorkflowAction
from common.utils.extend_json_encoder import ExtendJSONEncoder
from sql.models import ResourceGroupApply, ResourceGroup, Users
from sql.notify import notify_for_audit
from sql.utils.resource_group import user_groups
from sql.utils.workflow_audit import AuditException, get_auditor
from django_q.tasks import async_task

logger = logging.getLogger("default")


@permission_required("sql.menu_resourcegroupapplylist", raise_exception=True)
def resource_group_apply_list(request):
    """
    获取资源组权限申请列表数据
    """
    user = request.user
    limit = int(request.POST.get("limit", 0))
    offset = int(request.POST.get("offset", 0))
    limit = offset + limit
    search = request.POST.get("search", "")

    apply_records = ResourceGroupApply.objects.all()
    if search:
        apply_records = apply_records.filter(
            Q(title__icontains=search) | Q(user_display__icontains=search) | Q(group_name__icontains=search)
        )
    if user.is_superuser:
        pass
    elif user.has_perm("sql.resource_group_review"):
        group_list = user_groups(user)
        group_ids = [group.group_id for group in group_list]
        apply_records = apply_records.filter(group_id__in=group_ids)
    else:
        apply_records = apply_records.filter(user_name=user.username)

    count = apply_records.count()
    lists = apply_records.order_by("-apply_id")[offset:limit].values(
        "apply_id",
        "title",
        "group_name",
        "user_display",
        "status",
        "create_time",
        "apply_remark",
    )

    rows = [row for row in lists]
    result = {"total": count, "rows": rows}
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder, bigint_as_string=True),
        content_type="application/json",
    )


@permission_required("sql.resource_group_apply", raise_exception=True)
def resource_group_apply(request):
    """
    提交资源组权限申请
    """
    title = request.POST.get("title")
    group_name = request.POST.get("group_name")
    apply_remark = request.POST.get("apply_remark", "")

    user = request.user
    result = {"status": 0, "msg": "ok", "data": []}

    if not title or not group_name:
        result["status"] = 1
        result["msg"] = "请填写完整申请信息"
        return HttpResponse(json.dumps(result), content_type="application/json")

    try:
        group_obj = ResourceGroup.objects.get(group_name=group_name, is_deleted=0)
    except ResourceGroup.DoesNotExist:
        result["status"] = 1
        result["msg"] = "资源组不存在"
        return HttpResponse(json.dumps(result), content_type="application/json")

    user_obj = Users.objects.get(id=user.id)
    if user_obj.resource_group.filter(group_id=group_obj.group_id).exists():
        result["status"] = 1
        result["msg"] = f"你已属于{group_name}资源组，无需重复申请"
        return HttpResponse(json.dumps(result), content_type="application/json")

    if ResourceGroupApply.objects.filter(
        user_name=user.username,
        group_id=group_obj.group_id,
        status=WorkflowStatus.WAITING,
    ).exists():
        result["status"] = 1
        result["msg"] = f"你已有待审核的{group_name}资源组申请，请勿重复提交"
        return HttpResponse(json.dumps(result), content_type="application/json")

    apply_info = ResourceGroupApply(
        title=title,
        group_id=group_obj.group_id,
        group_name=group_obj.group_name,
        user_name=user.username,
        user_display=user.display,
        apply_remark=apply_remark,
        status=WorkflowStatus.WAITING,
        audit_auth_groups="",
    )
    audit_handler = get_auditor(workflow=apply_info)
    try:
        with transaction.atomic():
            audit_handler.create_audit()
    except AuditException as e:
        logger.error(f"新建审批流失败, {str(e)}")
        result["status"] = 1
        result["msg"] = "新建审批流失败，请联系管理员"
        return HttpResponse(json.dumps(result), content_type="application/json")

    _resource_group_apply_audit_call_back(
        audit_handler.workflow.apply_id, audit_handler.audit.current_status
    )

    async_task(
        notify_for_audit,
        workflow_audit=audit_handler.audit,
        timeout=60,
        task_name=f"resource-group-apply-{audit_handler.workflow.apply_id}",
    )

    return HttpResponse(json.dumps(result), content_type="application/json")


@permission_required("sql.resource_group_review", raise_exception=True)
def resource_group_audit(request):
    """
    资源组权限审核
    """
    apply_id = int(request.POST["apply_id"])
    try:
        audit_status = WorkflowAction(int(request.POST["audit_status"]))
    except ValueError as e:
        return render(
            request, "error.html", {"errMsg": f"audit_status 参数错误, {str(e)}"}
        )
    audit_remark = request.POST.get("audit_remark", "")

    try:
        apply_obj = ResourceGroupApply.objects.get(apply_id=apply_id)
    except ResourceGroupApply.DoesNotExist:
        return render(request, "error.html", {"errMsg": "工单不存在"})

    auditor = get_auditor(workflow=apply_obj)
    with transaction.atomic():
        try:
            workflow_audit_detail = auditor.operate(
                audit_status, request.user, audit_remark
            )
        except AuditException as e:
            return render(request, "error.html", {"errMsg": f"审核失败: {str(e)}"})

        _resource_group_apply_audit_call_back(
            auditor.audit.workflow_id, auditor.audit.current_status
        )

    async_task(
        notify_for_audit,
        workflow_audit=auditor.audit,
        workflow_audit_detail=workflow_audit_detail,
        timeout=60,
        task_name=f"resource-group-audit-{apply_id}",
    )

    return HttpResponseRedirect(
        reverse("sql:resourcegroupapplydetail", args=(apply_id,))
    )


def _resource_group_apply_audit_call_back(apply_id, workflow_status):
    """
    资源组权限申请审批回调
    审批通过后自动将用户关联到对应的资源组
    """
    apply_info = ResourceGroupApply.objects.get(apply_id=apply_id)
    apply_info.status = workflow_status
    apply_info.save()

    if workflow_status == WorkflowStatus.PASSED:
        try:
            user_obj = Users.objects.get(username=apply_info.user_name)
            group_obj = ResourceGroup.objects.get(group_id=apply_info.group_id)
            user_obj.resource_group.add(group_obj)
            logger.info(
                f"用户 {apply_info.user_display} 已成功加入资源组 {apply_info.group_name}"
            )
        except (Users.DoesNotExist, ResourceGroup.DoesNotExist) as e:
            logger.error(
                f"资源组权限审批回调失败, 用户或资源组不存在: {str(e)}"
            )

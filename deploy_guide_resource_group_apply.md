# 资源权限申请功能 — 增量部署方案

## 一、功能概述

在 SQL查询菜单下新增 **「资源权限申请」** 页面，允许没有资源组权限的用户提交资源组加入申请，审批通过后自动将用户关联到对应资源组。页面风格与现有权限管理页面保持一致，审批流程复用现有 `WorkflowAudit` 体系。

---

## 二、变更清单

### 新增文件（4个）

| 文件 | 说明 |
|------|------|
| `sql/resource_group_apply.py` | 后端核心逻辑：申请列表、提交申请、审批、回调（自动关联资源组） |
| `sql/templates/resourcegroupapplylist.html` | 资源权限申请列表页面 |
| `sql/templates/resourcegroupapplydetail.html` | 资源权限申请详情+审批页面 |
| `src/init_sql/v1.11.0_resource_group_apply.sql` | 增量SQL：建表+权限注册 |

### 修改文件（8个）

| 文件 | 说明 |
|------|------|
| `sql/models.py` | 新增 `ResourceGroupApply` 模型；`WorkflowAuditMixin` 支持类型4；`WorkflowAudit.get_workflow` 支持类型4；Permission Meta 新增3个权限项 |
| `common/utils/const.py` | `WorkflowType` 新增 `RESOURCE_GROUP=4`；`Const.workflowJobprefix` 新增 `resourcegroup` |
| `sql/views.py` | 新增 `resourcegroupapplylist`、`resourcegroupapplydetail` 视图；`workflowsdetail` 支持类型4路由 |
| `sql/urls.py` | 新增5条URL路由 |
| `sql/utils/workflow_audit.py` | `can_operate` 支持类型4权限校验（`sql.resource_group_review`）；`can_review.get_workflow_applicant` 支持类型4 |
| `common/templates/base.html` | SQL查询菜单新增「资源权限申请」入口 |
| `sql/templates/workflow.html` | 待办列表工单类型筛选新增「资源组权限申请」选项 |
| `common/static/dist/js/formatter.js` | `workflow_type_formatter` 支持类型4显示 |

---

## 三、部署步骤

### Step 1：执行增量SQL

连接到 Archery 使用的 MySQL 数据库，执行：

```bash
mysql -u<用户> -p<密码> -h<主机> <archery数据库> < src/init_sql/v1.11.0_resource_group_apply.sql
```

SQL 内容：
- 创建 `resource_group_apply` 表
- 注册3个新权限项到 `auth_permission` 表

### Step 2：同步代码

```bash
cd /opt/archery  # 项目实际部署路径
git fetch origin
git checkout master
git pull origin master
# 或从你的仓库拉取：git pull https://github.com/adam-qin/Archery.git master
```

### Step 3：收集静态资源

```bash
cd /opt/archery
python manage.py collectstatic --noinput
```

> `formatter.js` 位于 `common/static/dist/js/` 目录，需要被收集到 STATIC_ROOT 供 Nginx 使用。

### Step 4：重启服务

```bash
# supervisord 方式（Archery 默认部署方式）
supervisorctl restart archery
# 或 Docker 方式
docker-compose restart archery
```

### Step 5：配置审批流程

以超级管理员登录 → 系统管理 → 其他配置 → **工单审批流程配置**：

为每个需要支持资源权限申请的资源组，配置 **类型4（资源组权限申请）** 的审批权限组链路。操作步骤：
1. 选择资源组
2. 工单类型选择「资源组权限申请」
3. 设置审批权限组（如：DBA → 组长）

### Step 6：分配菜单权限

进入 系统管理 → 资源组管理 → 关联权限组：

将以下权限分配给需要使用该功能的权限组：
- `menu_resourcegroupapplylist` — 菜单 资源权限申请（普通用户可见）
- `resource_group_apply` — 申请资源组权限（普通用户可提交申请）
- `resource_group_review` — 审核资源组权限（审批人需要）

---

## 四、功能验证

### 4.1 申请流程验证

1. 使用**没有资源组权限**的用户登录
2. 进入 SQL查询 → 资源权限申请
3. 点击「资源权限申请」按钮
4. 选择资源组、填写标题和备注
5. 确认审批流程显示后提交

### 4.2 审批流程验证

1. 使用**拥有 `resource_group_review` 权限**的审批人登录
2. 在待办列表或详情页面审核
3. 点击「审核通过」
4. 确认该用户已自动加入对应资源组（可在资源组管理页面验证）

### 4.3 回调验证

审批通过后检查：
- `resource_group_apply` 表中对应申请记录 `status=1`
- `sql_users` 表中对应用户的 `resource_group` 关联已建立
- 用户可访问该资源组关联的实例

---

## 五、回滚方案

如需回滚，执行以下步骤：

### 5.1 代码回滚

```bash
cd /opt/archery
git revert HEAD  # 回滚最近一次提交
# 或指定 commit hash
git revert 40805e0
supervisorctl restart archery
```

### 5.2 数据库回滚

```sql
-- 删除 resource_group_apply 表
DROP TABLE IF EXISTS `resource_group_apply`;

-- 删除新增的权限项
DELETE FROM `auth_permission` WHERE `codename` IN (
    'menu_resourcegroupapplylist',
    'resource_group_apply',
    'resource_group_review'
);

-- 删除关联的权限分配
DELETE FROM `auth_group_permissions` WHERE `permission_id` IN (
    SELECT id FROM `auth_permission` WHERE `codename` IN (
        'menu_resourcegroupapplylist',
        'resource_group_apply',
        'resource_group_review'
    )
);

-- 注意：已审批通过并自动关联的用户-资源组关系不会被自动回滚
-- 需根据实际情况手动在资源组管理页面解除关联
```

### 5.3 清理审批配置

如已配置了类型4的审批流程：

```sql
DELETE FROM `workflow_audit_setting` WHERE `workflow_type` = 4;
```

---

## 六、注意事项

1. **审批流程必须配置**：在系统配置页面为资源组设置类型4的审批流程，否则前端会提示"未配置审批流程"无法提交申请
2. **权限分配**：确保目标用户组拥有 `menu_resourcegroupapplylist` 权限才能看到菜单入口
3. **审批人权限**：审批人需同时拥有 `resource_group_review` 权限且属于审批配置中的权限组
4. **资源组下拉过滤**：申请页面的资源组下拉已自动排除用户已加入的资源组，避免重复申请
5. **重复提交防护**：存在待审核申请时，不允许对同一资源组重复提交
6. **推送问题**：当前提供的 access token 已失效，需提供新的有效 token 执行 `git push`。代码已本地提交完成（commit `40805e0`）

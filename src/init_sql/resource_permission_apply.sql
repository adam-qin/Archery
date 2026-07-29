-- 资源权限申请增量 SQL（MySQL 5.7+/8.0）
START TRANSACTION;

CREATE TABLE IF NOT EXISTS `resource_permission_apply` (
  `apply_id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `group_name` varchar(100) NOT NULL,
  `title` varchar(50) NOT NULL,
  `reason` varchar(500) NOT NULL DEFAULT '',
  `user_name` varchar(30) NOT NULL,
  `user_display` varchar(50) NOT NULL DEFAULT '',
  `status` int NOT NULL DEFAULT 0,
  `audit_auth_groups` varchar(255) NOT NULL DEFAULT '',
  `create_time` datetime(6) NOT NULL,
  `sys_time` datetime(6) NOT NULL,
  PRIMARY KEY (`apply_id`),
  KEY `resource_permission_user_group_status_idx` (`user_name`,`group_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='资源权限申请记录表';

SET @permission_content_type_id = (
  SELECT `id` FROM `django_content_type`
  WHERE `app_label` = 'sql' AND `model` = 'permission'
  LIMIT 1
);
INSERT INTO `auth_permission` (`name`, `content_type_id`, `codename`)
SELECT '资源权限申请', @permission_content_type_id, 'resource_permission_apply'
WHERE @permission_content_type_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM `auth_permission`
    WHERE `content_type_id` = @permission_content_type_id
      AND `codename` = 'resource_permission_apply'
  );

-- 默认权限组及常用普通用户组默认可访问和提交。
INSERT IGNORE INTO `auth_group_permissions` (`group_id`, `permission_id`)
SELECT g.`id`, p.`id`
FROM `auth_group` g
JOIN `auth_permission` p
  ON p.`content_type_id` = @permission_content_type_id
 AND p.`codename` = 'resource_permission_apply'
WHERE g.`name` IN ('Default', 'RD', 'PM', 'QA', 'DBA');

-- 为每个有效资源组复制查询权限申请(type=1)的审批节点，生成独立 type=4 配置。
-- 若某资源组没有 type=1 配置，请在部署前按实际审批组手工补齐，不能留空。
INSERT INTO `workflow_audit_setting`
  (`group_id`, `group_name`, `workflow_type`, `audit_auth_groups`, `create_time`, `sys_time`)
SELECT rg.`group_id`, rg.`group_name`, 4, source.`audit_auth_groups`, NOW(6), NOW(6)
FROM `resource_group` rg
JOIN `workflow_audit_setting` source
  ON source.`group_id` = rg.`group_id` AND source.`workflow_type` = 1
LEFT JOIN `workflow_audit_setting` target
  ON target.`group_id` = rg.`group_id` AND target.`workflow_type` = 4
WHERE rg.`is_deleted` = 0 AND target.`audit_setting_id` IS NULL;

COMMIT;

-- 验证 SQL
SELECT `apply_id`, `group_id`, `user_name`, `status` FROM `resource_permission_apply` LIMIT 1;
SELECT p.`codename`, g.`name`
FROM `auth_permission` p
LEFT JOIN `auth_group_permissions` gp ON gp.`permission_id` = p.`id`
LEFT JOIN `auth_group` g ON g.`id` = gp.`group_id`
WHERE p.`codename` = 'resource_permission_apply';
SELECT `group_id`, `group_name`, `workflow_type`, `audit_auth_groups`
FROM `workflow_audit_setting` WHERE `workflow_type` = 4;

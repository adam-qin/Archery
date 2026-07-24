-- 资源组权限申请功能增量SQL（v1.12.0版本）
-- 对应版本: v1.12.0-resource-group-apply

-- 1. 新建 resource_group_apply 表
CREATE TABLE IF NOT EXISTS `resource_group_apply` (
  `apply_id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL COMMENT '组ID',
  `group_name` varchar(100) NOT NULL COMMENT '组名称',
  `title` varchar(50) NOT NULL COMMENT '申请标题',
  `user_name` varchar(30) NOT NULL COMMENT '申请人',
  `user_display` varchar(50) NOT NULL DEFAULT '' COMMENT '申请人中文名',
  `apply_remark` varchar(140) NOT NULL DEFAULT '' COMMENT '申请备注',
  `status` int NOT NULL COMMENT '审核状态: 0待审核/1通过/2不通过/3取消',
  `audit_auth_groups` varchar(255) NOT NULL COMMENT '审批权限组列表',
  `create_time` datetime(6) NOT NULL COMMENT '创建时间',
  `sys_time` datetime(6) NOT NULL COMMENT '系统时间',
  PRIMARY KEY (`apply_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='资源组权限申请';

-- 2. 新增权限项
INSERT INTO `auth_permission` (`name`, `content_type_id`, `codename`)
SELECT '菜单 资源权限申请', `id`, 'menu_resourcegroupapplylist' FROM `django_content_type` WHERE `app_label`='sql' AND `model`='permission'
ON DUPLICATE KEY UPDATE `name`='菜单 资源权限申请';

INSERT INTO `auth_permission` (`name`, `content_type_id`, `codename`)
SELECT '申请资源组权限', `id`, 'resource_group_apply' FROM `django_content_type` WHERE `app_label`='sql' AND `model`='permission'
ON DUPLICATE KEY UPDATE `name`='申请资源组权限';

INSERT INTO `auth_permission` (`name`, `content_type_id`, `codename`)
SELECT '审核资源组权限', `id`, 'resource_group_review' FROM `django_content_type` WHERE `app_label`='sql' AND `model`='permission'
ON DUPLICATE KEY UPDATE `name`='审核资源组权限';

-- 3. 将菜单权限赋予 Default 组（保证新用户能看到该菜单）
--    已加入对应权限组的用户可跳过此步
INSERT IGNORE INTO `auth_group_permissions` (`group_id`, `permission_id`)
SELECT g.id, p.id FROM `auth_group` g
JOIN `auth_permission` p ON p.codename IN (
    'menu_resourcegroupapplylist', 'resource_group_apply'
)
WHERE g.name = 'Default';

-- 4. 给其他默认组（RD/DBA/PM/QA）也赋予对应权限
INSERT IGNORE INTO `auth_group_permissions` (`group_id`, `permission_id`)
SELECT g.id, p.id FROM `auth_group` g
JOIN `auth_permission` p ON p.codename = 'menu_resourcegroupapplylist'
WHERE g.name IN ('RD', 'DBA', 'PM', 'QA');

-- 普通用户和 DBA 均可提交申请，避免只有菜单权限但提交接口 403
INSERT IGNORE INTO `auth_group_permissions` (`group_id`, `permission_id`)
SELECT g.id, p.id FROM `auth_group` g
JOIN `auth_permission` p ON p.codename = 'resource_group_apply'
WHERE g.name IN ('RD', 'DBA', 'PM', 'QA');

-- DBA/PM 可审核
INSERT IGNORE INTO `auth_group_permissions` (`group_id`, `permission_id`)
SELECT g.id, p.id FROM `auth_group` g
JOIN `auth_permission` p ON p.codename = 'resource_group_review'
WHERE g.name IN ('DBA', 'PM');

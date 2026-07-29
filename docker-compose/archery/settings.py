# -*- coding: UTF-8 -*-


# 在这里写配置可以覆盖 archery/settings.py 内的配置
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'archery',
        'USER': 'root',
        'PASSWORD': 'zuGfMklwMGGlDjKYFOpB',
        'HOST': 'mysql',                 
        'PORT': '3306',
    }
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    'https://dbms.qiniu.io',
]


# ================= 启用 LDAP 认证 =================
import ldap

ENABLE_LDAP = True

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

if ENABLE_LDAP:
    import ldap
    from django_auth_ldap.config import LDAPSearch

    # 1. 认证后端顺序：先校验 LDAP，失败后再校验 Django 本地用户（保障 root/admin 本地账号可登录）
    AUTHENTICATION_BACKENDS = (
        'django_auth_ldap.backend.LDAPBackend',
        'django.contrib.auth.backends.ModelBackend',
    )

    # 2. LDAP 服务地址与端口（支持 ldap:// 或 ldaps://）
    AUTH_LDAP_SERVER_URI = "ldap://ldaps.qiniu.io:389"

    # 3. 用于绑定并查询 LDAP 的服务账号 (Bind DN) 及密码
    AUTH_LDAP_BIND_DN = "cn=sys-zbx-ldap-auth,ou=People,dc=qiniu,dc=com"
    AUTH_LDAP_BIND_PASSWORD = "mFJzD5o_oaO6gX"

    # 4. 用户搜索路径与过滤条件
    # - OpenLDAP 通常使用 '(uid=%(user)s)'
    # - Windows Active Directory 通常使用 '(sAMAccountName=%(user)s)'
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        "ou=People,dc=qiniu,dc=com",  # 搜索 Base DN
        ldap.SCOPE_SUBTREE,            # 搜索范围：递归子树
        "(uid=%(user)s)"               # 匹配过滤表达式
    )

    # 5. 每次登录时自动更新本地用户属性
    AUTH_LDAP_ALWAYS_UPDATE_USER = True

    # 6. 属性映射：将 LDAP 字段映射为 Archery 的用户信息
    # 左侧为 Archery 系统字段，右侧为 LDAP 属性名
    AUTH_LDAP_USER_ATTR_MAP = {
        "username": "uid",             # AD 可替换为 sAMAccountName
        "display": "uid",      # 显示名称
        "email": "mail"                # 邮箱地址
    }



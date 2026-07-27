# -*- coding: UTF-8 -*-
import base64
import logging
import traceback

import simplejson as json
from django.http import HttpResponse

from common.utils.permission import superuser_required
from sql.models import Config
from django.db import transaction

logger = logging.getLogger("default")


def _looks_like_mirage_ciphertext(value):
    """Recognize django-mirage-field's URL-safe base64 ciphertext shape."""
    if len(value) < 24 or len(value) % 4:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return False
    return len(decoded) >= 16 and len(decoded) % 16 == 0


class SysConfig(object):
    def __init__(self):
        self.sys_config = {}

    def get_all_config(self):
        try:
            # 获取系统配置信息
            all_config = Config.objects.all().values("item", "value")
            sys_config = {}
            for items in all_config:
                if items["value"] in ("true", "True"):
                    items["value"] = True
                elif items["value"] in ("false", "False"):
                    items["value"] = False
                sys_config[items["item"]] = items["value"]
            self.sys_config = sys_config
        except Exception as m:
            logger.error(f"获取系统配置信息失败:{m}{traceback.format_exc()}")
            self.sys_config = {}

    def get(self, key, default_value=None):
        value = self.sys_config.get(key)
        if value:
            return value
        # 尝试去数据库里取
        config_entry = Config.objects.filter(item=key).last()
        if config_entry:
            # 清洗成 python 的 bool
            value = self.filter_bool(config_entry.value)
        # 是字符串的话, 如果是空, 或者全是空格, 返回默认值
        if isinstance(value, str) and value.strip() == "":
            return default_value
        if value is not None:
            self.sys_config[key] = value
            return value
        return default_value

    @staticmethod
    def filter_bool(value: str):
        if not isinstance(value, str):
            return value
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        return value

    @staticmethod
    def filter_int(value, default_value=None):
        """Return a valid integer configuration value or the supplied default.

        EncryptedCharField should decrypt values when the application uses the
        same Mirage key as the database writer. If a deployment has a key
        mismatch, Mirage intentionally returns the stored ciphertext instead
        of raising, so numeric settings must be validated before use.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default_value

    @staticmethod
    def filter_text(value, default_value=""):
        """Return printable text; never expose an encrypted config value."""
        if value is None:
            return default_value
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        if not value or _looks_like_mirage_ciphertext(value):
            return default_value
        return value

    def set(self, key, value):
        if value is True:
            db_value = "true"
        elif value is False:
            db_value = "false"
        else:
            db_value = value
        obj, created = Config.objects.update_or_create(
            item=key, defaults={"value": db_value}
        )
        self.sys_config.update({key: value})

    def replace(self, configs):
        result = {"status": 0, "msg": "ok", "data": []}
        # 清空并替换
        try:
            with transaction.atomic():
                self.purge()
                Config.objects.bulk_create(
                    [
                        Config(
                            item=items["key"].strip(), value=str(items["value"]).strip()
                        )
                        for items in json.loads(configs)
                    ]
                )
        except Exception as e:
            logger.error(traceback.format_exc())
            result["status"] = 1
            result["msg"] = str(e)
        finally:
            self.get_all_config()
        return result

    def purge(self):
        """清除所有配置, 供测试以及replace方法使用"""
        try:
            with transaction.atomic():
                Config.objects.all().delete()
                self.sys_config = {}
        except Exception as m:
            logger.error(f"删除缓存失败:{m}{traceback.format_exc()}")


# 修改系统配置
@superuser_required
def change_config(request):
    configs = request.POST.get("configs")
    archer_config = SysConfig()
    result = archer_config.replace(configs)
    # 返回结果
    return HttpResponse(json.dumps(result), content_type="application/json")

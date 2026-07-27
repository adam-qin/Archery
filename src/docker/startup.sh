#!/bin/bash
set -e

cd /opt/archery

# 自动定位「能 import django」的 Python 解释器，避免硬编码 venv 路径 / 激活失败导致运行时找不到包
PYTHON_BIN=""
for cand in /opt/venv4archery/bin/python /opt/venv/bin/python /usr/local/bin/python /usr/bin/python3; do
    if [ -x "$cand" ] && "$cand" -c "import django" >/dev/null 2>&1; then
        PYTHON_BIN="$cand"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: 未找到可 import django 的 Python 解释器，已排查下列候选路径："
    for cand in /opt/venv4archery/bin/python /opt/venv/bin/python /usr/local/bin/python /usr/bin/python3; do
        if [ -x "$cand" ]; then
            echo "  [候选] $cand"
            "$cand" --version
            "$cand" -m pip list 2>/dev/null | grep -iE "django|redis" || echo "    django/redis: 未安装"
        else
            echo "  [缺失] $cand"
        fi
    done
    echo "请确认镜像构建时已将依赖安装到该 venv（见 Dockerfile 中 /opt/venv4archery/bin/pip install 步骤）"
    exit 1
fi

echo "切换python运行环境 -> $PYTHON_BIN"
VENV_BIN="$(dirname "$PYTHON_BIN")"
export PATH="$VENV_BIN:$PATH"
"$PYTHON_BIN" --version

echo 修改重定向端口
if [[ -z $NGINX_PORT ]]; then
    sed -i "s/:nginx_port//g" /etc/nginx/nginx.conf
else
    sed -i "s/nginx_port/$NGINX_PORT/g" /etc/nginx/nginx.conf
fi

echo 启动nginx
/usr/sbin/nginx

echo 收集所有的静态文件到STATIC_ROOT
"$PYTHON_BIN" manage.py collectstatic -v0 --noinput

echo 启动Django Q cluster
"$VENV_BIN/supervisord" -c /etc/supervisord.conf

echo 启动服务
"$VENV_BIN/gunicorn" -w 4 -b 127.0.0.1:8888 --timeout 600 archery.wsgi:application

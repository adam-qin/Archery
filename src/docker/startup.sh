#!/bin/bash
set -e

cd /opt/archery

echo 切换python运行环境
if [ -f /opt/venv4archery/bin/activate ]; then
    source /opt/venv4archery/bin/activate
    export PATH="/opt/venv4archery/bin:$PATH"
else
    echo "ERROR: 虚拟环境不存在: /opt/venv4archery/bin/activate"
    exit 1
fi

echo 修改重定向端口
if [[ -z $NGINX_PORT ]]; then
    sed -i "s/:nginx_port//g" /etc/nginx/nginx.conf
else
    sed -i "s/nginx_port/$NGINX_PORT/g" /etc/nginx/nginx.conf
fi

echo 启动nginx
/usr/sbin/nginx

echo 收集所有的静态文件到STATIC_ROOT
python manage.py collectstatic -v0 --noinput

echo 启动Django Q cluster
supervisord -c /etc/supervisord.conf

echo 启动服务
gunicorn -w 4 -b 127.0.0.1:8888 --timeout 600 archery.wsgi:application

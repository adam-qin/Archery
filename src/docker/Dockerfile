ARG BASE_IMAGE="hhyo/archery-base:sha-d8159f4"
FROM ${BASE_IMAGE}
SHELL ["/bin/bash", "-c"]

ARG HTTP_PROXY="http://120.240.166.145:13228"
ARG HTTPS_PROXY="http://120.240.166.145:13228"

COPY . /opt/archery/

WORKDIR /opt/

RUN useradd nginx
#archery
RUN apt-get update \
    && apt-get install -yq --no-install-recommends nginx mariadb-client \
    # 直接用 venv 绝对路径的 pip，不依赖 source activate 是否生效
    && /opt/venv4archery/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv4archery/bin/pip install --no-cache-dir \
        $( [ -n "$HTTP_PROXY" ] && echo "--proxy $HTTP_PROXY" ) \
        -r /opt/archery/requirements.txt \
    && /opt/venv4archery/bin/pip uninstall -y redis-py-cluster 2>/dev/null || true \
    # 构建末尾验证关键依赖已装进 venv，避免产出「运行时才缺包」的坏镜像
    && /opt/venv4archery/bin/python -c "import django, redis; print('[build] deps ok: django=%s redis=%s' % (django.get_version(), redis.__version__))" \
    && cp -f /opt/archery/src/docker/nginx.conf /etc/nginx/ \
    && cp -f /opt/archery/src/docker/supervisord.conf /etc/ \
    && mv /opt/sqladvisor /opt/archery/src/plugins/ \
    && mv /opt/soar /opt/archery/src/plugins/ \
    && mv /opt/my2sql /opt/archery/src/plugins/ \
    && apt-get -yq remove gcc curl \
    && apt-get clean \
    && rm -rf /var/cache/apt/* \
    && rm -rf /root/.cache

#port
EXPOSE 9123

#start service
ENTRYPOINT ["bash", "/opt/archery/src/docker/startup.sh"]


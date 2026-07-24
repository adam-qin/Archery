ARG BASE_IMAGE="hhyo/archery-base:sha-d8159f4"
FROM ${BASE_IMAGE}
SHELL ["/bin/bash", "-c"]

# ---- Layer 1: 系统包安装（极少变化，缓存复用率最高） ----
RUN useradd nginx \
    && apt-get update \
    && apt-get install -yq --no-install-recommends nginx mariadb-client \
    && apt-get clean \
    && rm -rf /var/cache/apt/*

# ---- Layer 2: 稳定二进制工具迁移（来自 base 镜像，仅基础镜像变化时重建） ----
RUN mkdir -p /opt/archery/src/plugins \
    && mv /opt/sqladvisor /opt/archery/src/plugins/ \
    && mv /opt/soar /opt/archery/src/plugins/ \
    && mv /opt/my2sql /opt/archery/src/plugins/

# ---- Layer 3: Python 依赖安装（仅 requirements.txt 变化时重建） ----
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
COPY requirements.txt /opt/archery/requirements.txt
RUN source venv4archery/bin/activate \
    && pip install --no-cache-dir "setuptools<82" wheel \
    && if [ -n "$HTTP_PROXY" ]; then \
        pip install --no-cache-dir \
            --proxy "$HTTP_PROXY" "oracledb==4.0.1"; \
    else \
        pip install --no-cache-dir "oracledb==4.0.1"; \
    fi \
    && if [ -n "$HTTP_PROXY" ]; then \
        pip install --no-cache-dir \
            --proxy "$HTTP_PROXY" -r /opt/archery/requirements.txt; \
    else \
        pip install --no-cache-dir -r /opt/archery/requirements.txt; \
    fi

# ---- Layer 4: 清理编译工具（依赖安装后执行，避免应用代码变化触发重建） ----
RUN apt-get -yq remove gcc curl \
    && apt-get autoremove -yq \
    && apt-get clean \
    && rm -rf /var/cache/apt/* /var/lib/apt/lists/* /root/.cache

# ---- Layer 5: 基础设施配置（仅 nginx/supervisor 配置变化时重建） ----
COPY src/docker/nginx.conf /etc/nginx/nginx.conf
COPY src/docker/supervisord.conf /etc/supervisord.conf

# ---- Layer 6: 应用代码（变动最频繁，尽量后置） ----
COPY . /opt/archery/

WORKDIR /opt/

EXPOSE 9123

ENTRYPOINT ["bash", "/opt/archery/src/docker/startup.sh"]

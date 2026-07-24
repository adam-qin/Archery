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
    && source venv4archery/bin/activate \
    && if [ -n "$HTTP_PROXY" ]; then \
        pip install --proxy "$HTTP_PROXY" -r /opt/archery/requirements.txt; \
    else \
        pip install -r /opt/archery/requirements.txt; \
    fi \
    && if [ -n "$HTTP_PROXY" ]; then \
        pip install --proxy "$HTTP_PROXY" "redis>=4.1.0"; \
    else \
        pip install "redis>=4.1.0"; \
    fi \
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


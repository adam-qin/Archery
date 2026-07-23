# Archery v1.14.1 镜像构建与部署指导

## 一、构建架构说明

Archery 镜像采用**两层构建**策略：

| 层级 | 镜像 | 说明 |
|------|------|------|
| **基础层** | `hhyo/archery-base:sha-d8159f4` | Python 3.11 venv + 系统依赖（nginx、oracle client、msodbcsql、percona-toolkit、sqladvisor、soar、my2sql、mongo client） |
| **应用层** | `hhyo/archery:v1.14.1` | 基于基础层，安装 Python 依赖 + 拷贝源码 + 配置 nginx/supervisor |

> 基础镜像变更频率低，通常无需重建。本次仅构建应用层镜像。

---

## 二、前置准备

### 2.1 环境要求

| 项目 | 要求 |
|------|------|
| Docker | >= 20.10 |
| 内存 | >= 4GB（构建过程中 pip install 消耗较大） |
| 网络 | 可访问 PyPI、GitHub（或配置代理） |
| Git | 拉取代码仓库 |

### 2.2 拉取代码

```bash
cd /opt
git clone https://github.com/adam-qin/Archery.git archery-v1.14.1
cd archery-v1.14.1
git checkout master
# 确认版本包含资源权限申请功能（commit 40805e0）
git log --oneline -1
```

---

## 三、构建方式（三选一）

### 方式A：标准 Docker Build（推荐）

最简单直接，适合大多数场景：

```bash
cd /opt/archery-v1.14.1

# 1. 拉取基础镜像
docker pull hhyo/archery-base:sha-d8159f4

# 2. 构建应用镜像
docker build \
    -f src/docker/Dockerfile \
    -t hhyo/archery:v1.14.1 \
    --build-arg BASE_IMAGE="hhyo/archery-base:sha-d8159f4" \
    .

# 3. 验证构建结果
docker images | grep archery
```

构建时间约 **10-20 分钟**（取决于网络速度和 pip 缓存）。

### 方式B：多阶段构建（优化镜像大小）

修改 Dockerfile 添加多阶段构建，减小最终镜像体积：

```bash
cd /opt/archery-v1.14.1

# 创建多阶段构建的临时 Dockerfile
cat > /tmp/Dockerfile-multistage << 'EOF'
ARG BASE_IMAGE="hhyo/archery-base:sha-d8159f4"
FROM ${BASE_IMAGE} AS builder
SHELL ["/bin/bash", "-c"]
COPY . /opt/archery/
WORKDIR /opt/
RUN source venv4archery/bin/activate \
    && pip install --no-cache-dir "setuptools<82" wheel \
    && pip install --no-cache-dir "oracledb==4.0.1" \
    && pip install --no-cache-dir -r /opt/archery/requirements.txt

FROM ${BASE_IMAGE} AS runtime
SHELL ["/bin/bash", "-c"]
COPY --from=builder /opt/venv4archery /opt/venv4archery
COPY --from=builder /opt/archery /opt/archery
WORKDIR /opt/
RUN useradd nginx \
    && apt-get update \
    && apt-get install -yq --no-install-recommends nginx mariadb-client \
    && cp -f /opt/archery/src/docker/nginx.conf /etc/nginx/ \
    && cp -f /opt/archery/src/docker/supervisord.conf /etc/ \
    && mv /opt/sqladvisor /opt/archery/src/plugins/ \
    && mv /opt/soar /opt/archery/src/plugins/ \
    && mv /opt/my2sql /opt/archery/src/plugins/ \
    && apt-get -yq remove gcc curl \
    && apt-get clean \
    && rm -rf /var/cache/apt/* /root/.cache
EXPOSE 9123
ENTRYPOINT ["bash", "/opt/archery/src/docker/startup.sh"]
EOF

# 构建多阶段镜像
docker build \
    -f /tmp/Dockerfile-multistage \
    -t hhyo/archery:v1.14.1 \
    --build-arg BASE_IMAGE="hhyo/archery-base:sha-d8159f4" \
    .
```

### 方式C：使用 BuildKit 加速构建

启用 Docker BuildKit，利用缓存挂载加速 pip install：

```bash
cd /opt/archery-v1.14.1

# 需要修改 Dockerfile 增加 cache mount 指令（可选优化）
# 直接使用 BuildKit 构建
DOCKER_BUILDKIT=1 docker build \
    -f src/docker/Dockerfile \
    -t hhyo/archery:v1.14.1 \
    --build-arg BASE_IMAGE="hhyo/archery-base:sha-d8159f4" \
    --progress=plain \
    .
```

---

## 四、代理/离线构建（可选）

### 4.1 使用代理

网络受限环境下配置 HTTP 代理：

```bash
docker build \
    -f src/docker/Dockerfile \
    -t hhyo/archery:v1.14.1 \
    --build-arg BASE_IMAGE="hhyo/archery-base:sha-d8159f4" \
    --build-arg HTTP_PROXY="http://proxy.company.com:8080" \
    --build-arg HTTPS_PROXY="http://proxy.company.com:8080" \
    .
```

> 注意：代理参数仅对基础镜像层（Dockerfile-base）生效。应用层需要在 pip install 前设置环境变量：
> ```dockerfile
> ENV http_proxy=http://proxy.company.com:8080
> ENV https_proxy=http://proxy.company.com:8080
> ```

### 4.2 离线构建

完全无网络环境下：

```bash
# 1. 在有网络的机器上准备离线包
mkdir -p /tmp/offline-pkg
pip download -d /tmp/offline-pkg -r requirements.txt
pip download -d /tmp/offline-pkg "setuptools<82" wheel "oracledb==4.0.1"

# 2. 创建离线 Dockerfile
cat > /tmp/Dockerfile-offline << 'EOF'
ARG BASE_IMAGE="hhyo/archery-base:sha-d8159f4"
FROM ${BASE_IMAGE}
SHELL ["/bin/bash", "-c"]
COPY . /opt/archery/
COPY offline-pkg /tmp/offline-pkg/
WORKDIR /opt/
RUN useradd nginx \
    && apt-get update \
    && apt-get install -yq --no-install-recommends nginx mariadb-client \
    && source venv4archery/bin/activate \
    && pip install --no-index --find-links=/tmp/offline-pkg "setuptools<82" wheel \
    && pip install --no-index --find-links=/tmp/offline-pkg "oracledb==4.0.1" \
    && pip install --no-index --find-links=/tmp/offline-pkg -r /opt/archery/requirements.txt \
    && cp -f /opt/archery/src/docker/nginx.conf /etc/nginx/ \
    && cp -f /opt/archery/src/docker/supervisord.conf /etc/ \
    && mv /opt/sqladvisor /opt/archery/src/plugins/ \
    && mv /opt/soar /opt/archery/src/plugins/ \
    && mv /opt/my2sql /opt/archery/src/plugins/ \
    && apt-get -yq remove gcc curl \
    && apt-get clean \
    && rm -rf /var/cache/apt/* /root/.cache /tmp/offline-pkg
EXPOSE 9123
ENTRYPOINT ["bash", "/opt/archery/src/docker/startup.sh"]
EOF

# 3. 将离线包拷贝到项目目录并构建
cp -r /tmp/offline-pkg /opt/archery-v1.14.1/offline-pkg
docker build \
    -f /tmp/Dockerfile-offline \
    -t hhyo/archery:v1.14.1 \
    --build-arg BASE_IMAGE="hhyo/archery-base:sha-d8159f4" \
    .
```

---

## 五、镜像推送到 Registry

### 5.1 推送至 Docker Hub

```bash
# 登录 Docker Hub
docker login -u <用户名>

# 打标签
docker tag hhyo/archery:v1.14.1 <用户名>/archery:v1.14.1

# 推送
docker push <用户名>/archery:v1.14.1
```

### 5.2 推送至私有 Registry（如 Harbor）

```bash
# 登录私有 Registry
docker login registry.company.com

# 打标签
docker tag hhyo/archery:v1.14.1 registry.company.com/archery/archery:v1.14.1

# 推送
docker push registry.company.com/archery/archery:v1.14.1
```

### 5.3 推送至 GitHub Container Registry

```bash
# 使用 GitHub token 登录
echo <GITHUB_TOKEN> | docker login ghcr.io -u <GITHUB_USER> --password-stdin

# 打标签
docker tag hhyo/archery:v1.14.1 ghcr.io/adam-qin/archery:v1.14.1

# 推送
docker push ghcr.io/adam-qin/archery:v1.14.1
```

---

## 六、部署运行

### 6.1 使用 docker-compose（推荐）

```bash
cd /opt/archery-v1.14.1/src/docker-compose

# 修改 docker-compose.yml 中的镜像版本
sed -i 's/hhyo\/archery:v1.14.0/hhyo\/archery:v1.14.1/' docker-compose.yml

# 或使用私有 Registry 镜像
# sed -i 's|hhyo/archery:v1.14.0|registry.company.com/archery/archery:v1.14.1|' docker-compose.yml

# 查看确认
grep 'image.*archery' docker-compose.yml

# 启动全部服务
docker-compose up -d

# 查看状态
docker-compose ps
```

### 6.2 执行增量 SQL（关键步骤）

首次部署 v1.14.1 或从旧版本升级时，**必须执行增量 SQL**：

```bash
# 等待 MySQL 容器就绪
docker-compose exec mysql mysqladmin ping -h localhost -u root -p123456

# 执行增量 SQL
docker-compose exec mysql mysql -u root -p123456 archery \
    -e "source /opt/archery/src/init_sql/v1.11.0_resource_group_apply.sql"
```

> 如果 docker-compose 中没有映射 SQL 文件到 MySQL 容器，可以手动执行：

```bash
# 将 SQL 文件拷入 MySQL 容器
docker cp /opt/archery-v1.14.1/src/init_sql/v1.11.0_resource_group_apply.sql mysql:/tmp/

# 在 MySQL 容器中执行
docker-compose exec mysql mysql -u root -p123456 archery \
    -e "source /tmp/v1.11.0_resource_group_apply.sql"
```

### 6.3 初始化数据库（首次部署）

首次部署需执行完整初始化：

```bash
docker-compose exec archery bash
source /opt/venv4archery/bin/activate

# 执行迁移
python3 manage.py makemigrations sql
python3 manage.py migrate

# 导入基础数据
python3 manage.py dbshell < sql/fixtures/auth_group.sql
python3 manage.py dbshell < src/init_sql/mysql_slow_query_review.sql

# 创建管理员
python3 manage.py createsuperuser

# 退出容器
exit
```

### 6.4 配置审批流程

登录管理员账号后：

1. 进入 **系统管理 → 其他配置 → 工单审批流程配置**
2. 选择目标资源组
3. 工单类型选择「资源组权限申请」（类型4）
4. 配置审批权限组链路（如：DBA → 组长）
5. 点击保存

### 6.5 分配菜单权限

进入 **系统管理 → 资源组管理**：

将以下权限分配给对应权限组：
- `menu_resourcegroupapplylist` — 菜单可见
- `resource_group_apply` — 可提交申请
- `resource_group_review` — 可审核申请

---

## 七、从旧版本升级

### 7.1 从 v1.14.0 升级到 v1.14.1

```bash
cd /opt/archery-v1.14.1/src/docker-compose

# 1. 拉取新镜像
docker pull hhyo/archery:v1.14.1
# 或: docker pull registry.company.com/archery/archery:v1.14.1

# 2. 修改 docker-compose.yml 镜像版本
sed -i 's/hhyo\/archery:v1.14.0/hhyo\/archery:v1.14.1/' docker-compose.yml

# 3. 停止旧 archery 容器
docker-compose stop archery
docker-compose rm -f archery

# 4. 执行增量 SQL（在 MySQL 中）
docker cp src/init_sql/v1.11.0_resource_group_apply.sql mysql:/tmp/
docker-compose exec mysql mysql -u root -p123456 archery \
    -e "source /tmp/v1.11.0_resource_group_apply.sql"

# 5. 启动新版本
docker-compose up -d archery

# 6. 验证
docker-compose logs -f archery
```

### 7.2 数据库迁移

如果模型有变更（已新增 `resource_group_apply` 表），需要确认 Django migration 状态：

```bash
docker-compose exec archery bash
source /opt/venv4archery/bin/activate
python3 manage.py migrate --check
# 如有未应用的迁移：
python3 manage.py migrate
exit
```

---

## 八、构建验证

### 8.1 验证镜像完整性

```bash
# 查看镜像信息
docker inspect hhyo/archery:v1.14.1 | python3 -m json.tool | head -20

# 查看镜像大小
docker images hhyo/archery:v1.14.1

# 快速功能验证（无需 docker-compose）
docker run --rm -it \
    -e SECRET_KEY="test-key-for-validation" \
    -e DATABASE_URL="mysql://root:123456@172.17.0.1:3306/archery" \
    -e CACHE_URL="redis://172.17.0.1:6379/0" \
    hhyo/archery:v1.14.1 \
    bash -c "source /opt/venv4archery/bin/activate && python3 -c 'import django; print(django.VERSION)'"
```

### 8.2 验证新增功能

启动服务后：

1. 登录 → SQL查询菜单 → 确认出现「资源权限申请」菜单项
2. 提交一个资源组权限申请 → 确认审批流程显示
3. 使用审批人账号 → 待办列表筛选「资源组权限申请」→ 审核通过
4. 确认申请人的资源组关联已建立

---

## 九、常见问题

| 问题 | 解决方案 |
|------|----------|
| 构建时 pip 超时 | 配置代理或使用国内 PyPI 镜像：在 Dockerfile 中添加 `RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/` |
| 基础镜像拉取失败 | 先手动 `docker pull hhyo/archery-base:sha-d8159f4`，确认可以拉取后再构建 |
| 启动后菜单没有「资源权限申请」 | 检查权限分配：执行增量 SQL 后需给用户组分配 `menu_resourcegroupapplylist` 权限 |
| 申请时提示"未配置审批流程" | 在系统配置页面为该资源组配置类型4（资源组权限申请）的审批权限组 |
| 数据库连接失败 | 检查 `.env` 中 `DATABASE_URL` 配置，确认 MySQL 容器已启动 |
| static 文件 404 | 确认 `startup.sh` 中 `collectstatic` 执行成功，检查 nginx 配置中 `alias /opt/archery/static` |

---

## 十、构建命令速查

```bash
# === 标准构建（推荐） ===
cd /opt/archery-v1.14.1
docker pull hhyo/archery-base:sha-d8159f4
docker build -f src/docker/Dockerfile -t hhyo/archery:v1.14.1 .

# === 推送镜像 ===
docker tag hhyo/archery:v1.14.1 ghcr.io/adam-qin/archery:v1.14.1
docker push ghcr.io/adam-qin/archery:v1.14.1

# === 部署 ===
cd /opt/archery-v1.14.1/src/docker-compose
sed -i 's/hhyo\/archery:v1.14.0/hhyo\/archery:v1.14.1/' docker-compose.yml
docker-compose up -d

# === 执行增量SQL ===
docker cp src/init_sql/v1.11.0_resource_group_apply.sql mysql:/tmp/
docker-compose exec mysql mysql -u root -p123456 archery -e "source /tmp/v1.11.0_resource_group_apply.sql"

# === 验证 ===
docker-compose ps
docker-compose logs -f archery
```

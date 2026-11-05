# 黔西南职院数据采集系统（DAS data acquisition system）

校内数据汇聚、审核、发布与共享平台。后端已实现登录认证、用户管理、权限管理、系部管理和数据字典；ODS 业务表已有模型与迁移。填报、审核、文件解析和共享接口尚未实现。前端已有登录页和各角色工作台，目前使用浏览器本地会话，尚未调用后端接口。

需求与排期见：

- [需求文档](docs/数据采集系统需求文档.md)
- [开发计划](docs/数据采集系统开发计划.md)
- 页面原型：`docs/datacollect/`

## 技术栈

| 部分     | 选型                                                    |
| -------- | ------------------------------------------------------- |
| 前端     | Next.js App Router、TypeScript、Tailwind CSS、shadcn/ui |
| 后端     | FastAPI、Pydantic v2、SQLAlchemy 2.0、Alembic           |
| 数据库   | PostgreSQL 15+（异步驱动 asyncpg）                      |
| 异步任务 | arq + Redis 7（worker 已配置，任务函数尚未接入）        |
| 包管理   | 后端使用 uv，前端使用 npm（镜像见 `frontend/.npmrc`）   |

## 目录

```text
qxnzy-das/
├── backend/
│   ├── app/
│   │   ├── api/routes/      # 健康检查、认证、用户、角色、系部、字典
│   │   ├── core/            # 环境配置、密码哈希与 JWT
│   │   ├── models/          # ODS 业务表与 sys_* 系统表
│   │   ├── seeds/           # 权限、角色、系部、字典与管理员初始化
│   │   └── workers/         # arq 配置
│   ├── alembic/             # 数据库迁移
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/app/             # 登录页与各角色工作台（本地演示数据）
│   ├── src/components/ui/
│   └── .env.example
├── docs/
└── compose.yaml             # 可选的 PostgreSQL 17、Redis 7 容器
```

## 环境要求

- Python 3.12+
- Node.js 22+
- uv
- 本机 PostgreSQL，库名 `qxnzy_das`，监听 `localhost:5432`

当前开发机使用 Postgres.app（PostgreSQL 15.19），用户 `postgres`、密码 `postgres`、库 `qxnzy_das`。这与代码默认连接串一致，不必再启动 `compose.yaml` 里的数据库，也不要停掉已经占用 `5432` 的本机 Postgres。

没有本机数据库时，可以用仓库根目录的容器（PostgreSQL 17，同样的用户、密码和库名）：

```bash
docker compose up -d postgres
```

Redis 只给尚未接入任务的异步 worker 使用，启动 API 时可以不运行。

## 数据库连接

后端在 `backend/app/db.py` 里用 `settings.database_url` 创建异步引擎，驱动为 asyncpg。配置类在 `backend/app/core/config.py`，只读取**进程当前工作目录**下的 `.env`，找不到就用代码默认值：

```text
postgresql+asyncpg://postgres:postgres@localhost:5432/qxnzy_das
```

因此必须在 `backend/` 目录启动。仓库里目前没有 `backend/.env`，走的就是这条默认连接串。Alembic 在线迁移也会改用同一地址，`alembic.ini` 里的 URL 只是占位。用户名、密码、端口或库名不同时，再复制示例配置并修改：

```bash
cd backend
cp .env.example .env
```

## 启动

在 `backend/` 目录执行。迁移和初始化只需在库结构变化或首次部署时运行，两者都可以重复执行：

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seeds.initial_data
uv run fastapi dev app/main.py
```

- API：<http://localhost:8000>
- OpenAPI：<http://localhost:8000/docs>
- 健康检查：`GET /health`

`app.seeds.initial_data` 可重复执行，会按编码更新而不是重复插入。它写入：

- 17 个权限点、4 个内置角色（教师 / 系部数据管理员 / 业务部门审核员 / 信息中心管理员），角色带数据范围 `self` / `department` / `all`
- 6 个教学系部和 7 个职能部门（教务处、人事处、科研处、学生处、招生就业处、校企合作处、信息中心）
- 《数据标准规范》D01—D70 共 70 个数据字典、1281 个取值，来源文件为 `backend/app/seeds/data_dictionary.json`（由标准 Excel 的「03数据字典」导出）
- 管理员账号。未提供 `.env` 时，默认账号 `admin`、初始密码 `Admin@2026`，来自 `INITIAL_ADMIN_ACCOUNT` / `INITIAL_ADMIN_PASSWORD`。该密码在执行初始化脚本时写入，之后修改 `.env` 不会改掉已有账号的密码

管理端接口都在 `/api` 前缀下，先用 `POST /api/auth/login` 换取 Bearer 令牌：

| 模块     | 路径                                                                              | 权限                                   |
| -------- | --------------------------------------------------------------------------------- | -------------------------------------- |
| 认证     | `/api/auth/login`、`/api/auth/token`、`/api/auth/me`、`/api/auth/change-password` | 登录即可                               |
| 用户管理 | `/api/users` 分页、新增、修改、启停、重置密码、删除                               | `user:read` / `user:write`             |
| 权限管理 | `/api/permissions`、`/api/roles` 增删改、分配权限点                               | `role:read` / `role:write`             |
| 系部管理 | `/api/departments` 增删改查                                                       | `department:read` / `department:write` |
| 数据字典 | `/api/dicts`、`/api/dicts/{code}`、取值维护                                       | `dict:read` / `dict:write`             |

超级管理员跳过权限检查；其他账号按角色聚合的权限点放行，停用账号登录和访问都会被拒绝。

前端：

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

前端地址为 <http://localhost:3000>。登录页按角色写入浏览器本地会话，系部、用户、角色、字典等页面使用前端演示数据，尚未请求 `/api`。`.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL` 预留给后续接口调用。

异步 worker 目前没有注册任务，本地开发可以先不启动。任务模块接入后再执行：

```bash
cd backend
uv run arq app.workers.settings.WorkerSettings
```

## 本机 Redis

API 不依赖 Redis。接入异步任务后再启动，可以用 Homebrew 的 `redis@8.2`，避免和容器里的 Redis 争用 `6379`：

```bash
brew services start redis@8.2
brew services list
```

常用操作：

```bash
brew services stop redis@8.2
brew services restart redis@8.2
```

`redis-server` 的路径取决于 Homebrew 安装位置：Apple Silicon 一般为 `/opt/homebrew/opt/redis@8.2/bin/redis-server`，Intel 一般为 `/usr/local/opt/redis@8.2/bin/redis-server`。使用 `brew services` 时不必手写该路径。

## 已落地的数据表

模型与迁移 `7279be8ab696` 已包含 13 张 ODS 表。需求文档中的十二类数据域之外，另有新生表 `ODS_XSXSSJ`。

| 数据域           | 模型                        | 表名             |
| ---------------- | --------------------------- | ---------------- |
| 专业设置         | `Major`                     | `ODS_ZYSZSJ`     |
| 教职工基本信息   | `StaffMember`               | `ODS_JZGJBSJ`    |
| 教师培训与交流   | `TeacherTraining`           | `ODS_XXJXSJ`     |
| 教师获奖信息     | `TeacherAward`              | `ODS_JSHJSJ`     |
| 教师论文著作     | `TeacherPublication`        | `ODS_LWZZSJ`     |
| 纵向科研项目     | `ResearchProject`           | `ODS_KYXMJBSJ`   |
| 横向课题         | `HorizontalResearchProject` | `ODS_HXKTSJ`     |
| 教师企业实践锻炼 | `EnterprisePractice`        | `ODS_JSQYJZSJSJ` |
| 教师知识产权     | `IntellectualProperty`      | `ODS_ZSCQSJ`     |
| 课程基本数据     | `Course`                    | `ODS_KCJBSJ`     |
| 授课信息         | `TeachingAssignment`        | `ODS_SKXXSJ`     |
| 在校生基本信息   | `Student`                   | `ODS_XSJBSJ`     |
| 新生信息         | `SeptemberNewStudent`       | `ODS_XSXSSJ`     |

业务表使用 PostgreSQL 检查约束和唯一约束。部分年月、学期字段使用数据库正则，迁移需在 PostgreSQL 上执行。

系统表由迁移 `a3f1c2d4e5b6` 创建，与 ODS 表分开：`sys_department`、`sys_user`、`sys_role`、`sys_permission`、`sys_dict_type`、`sys_dict_item`，以及 `sys_user_role`、`sys_role_permission`。

## 日志

API 和 worker 各自写一个文件，默认在 `backend/storage/logs/`：

| 文件          | 内容                                                    |
| ------------- | ------------------------------------------------------- |
| `api.log`     | 访问日志（方法、路径、状态码、耗时、请求 ID）与接口异常 |
| `worker.log`  | 任务调度、解析进度、模型调用失败与解析失败              |

每条日志都带 `[请求 ID]`，页面上报错时把 `request_id` 一起提供即可定位。worker 处理的任务没有请求上下文，该位置显示 `-`，用任务 ID 查找。

```bash
tail -f backend/storage/logs/worker.log
rg "task=b4f82031" backend/storage/logs/worker.log
```

模型输出解析失败时会额外记录 `tokens_out`、内容长度和原文片段。若 `tokens_out` 正好等于 `AI_MAX_TOKENS`，说明输出被截断。日志含业务数据时，可用 `LOG_FAILED_MODEL_OUTPUT=false` 关闭原文片段。

## 配置

后端示例见 `backend/.env.example`：

| 变量                                               | 作用                                                                                                                        |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                                     | PostgreSQL 连接串。不设置时使用 `postgresql+asyncpg://postgres:postgres@localhost:5432/qxnzy_das`，与当前 Postgres.app 一致 |
| `REDIS_URL`                                        | Redis 连接串，默认 `redis://localhost:6379/0`                                                                               |
| `CORS_ORIGINS`                                     | 允许的前端来源                                                                                                              |
| `DEEPSEEK_API_KEY`                                 | 模型密钥，留空即可启动                                                                                                      |
| `UPLOAD_DIR`                                       | 上传目录，默认 `./storage/uploads`                                                                                          |
| `MAX_UPLOAD_SIZE_MB`                               | 上传大小上限，默认 20                                                                                                       |
| `LOG_LEVEL` / `LOG_TO_FILE`                        | 日志级别（默认 `INFO`）与是否写文件（默认 `true`）                                                                          |
| `LOG_DIR`                                          | 日志目录，默认 `./storage/logs`                                                                                             |
| `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT`               | 单个日志文件大小上限（默认 10MB）与保留份数（默认 5）                                                                       |
| `LOG_FAILED_MODEL_OUTPUT`                          | 模型输出解析失败时是否记录原文片段，默认 `true`                                                                             |
| `JWT_SECRET_KEY`                                   | 签发访问令牌的密钥，生产环境必须替换为至少 32 字节随机值                                                                    |
| `ACCESS_TOKEN_EXPIRE_MINUTES`                      | 令牌有效期，默认 720 分钟                                                                                                   |
| `INITIAL_ADMIN_ACCOUNT` / `INITIAL_ADMIN_PASSWORD` | 初始化脚本创建的管理员账号与密码，首次登录后请修改                                                                          |

密钥只放在本地 `.env`，不要写入代码库。`.env` 已被忽略，`.env.example` 可以提交。

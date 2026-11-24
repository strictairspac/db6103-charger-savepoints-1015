# 桐驿充电·换站批次验收

逐站登记枪口，隔离编号冲突以及检测未过的站点，同批其他站点仍可交接。

## 业务流程

1. 换站交接
2. 站点与枪口
3. 分站验收
4. 送电核对单

PostgreSQL 对站点和枪口写入建立真实 SAVEPOINT，站内原子回退、批内继续。

桐驿公共充电运维组接收安装方调试台账，各站需独立核对站号和枪口检测资料，再交接送电调度。手工登记时，重复枪口常在后续巡视才发现，错站需要逐条撤销，同一批多个现场的移交时间被绑定。

08:30 收到 TY-1124-站批，08:35 核对四个站号，08:40 录入枪口序列和检测值，08:45 设定演练下限 1000 kΩ，08:50 后台逐站入表，08:52 核对两个通过站与两次搁置，09:05 导出交班单。

使用 PostgreSQL 主键检测重复，保存点覆盖站表与所有枪口写入，有质量失败也回滚。同批剩余通过站可以使用已回滚站曾尝试写入的枪口编号。默认通过 TY-S11、TY-S14，登记 3 个枪口。绝缘下限为模拟调试参数，整批使用数据库暂存表与最终结果快照，供验收培训。

## 启动

```sh
cp -n .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
```

打开 <http://localhost:18252>。OpenAPI 在 <http://localhost:19252/docs>，数据库映射到本机 17752。所有暴露端口只绑定回环地址。Compose 启动 frontend、backend、worker、db、redis，各自通过健康探针检查。数据库、Redis 和共享产物目录各有命名卷；任务状态及导出内容以数据库中的证据为准。

首次启动时幂等载入演示数据。手动载入可运行 `docker compose exec -T backend python -m scripts.seed_demo`。常规停止可用 `docker compose down`。验收环境清理才加 `-v`，它会删除本项目的数据卷。

## 角色与交接

演示账号共用口令 `Demo-DbWorkbench-2026`。

| 登录名 | 角色 | 可执行操作 |
|---|---|---|
| operator | 资料操作员 | 登记业务资料、设置「绝缘读数下限（kΩ）」、提交、查看和下载结果 |
| reviewer | 业务复核员 | 查看执行证据、签署单次复核、下载交接单 |
| viewer | 只读观察员 | 查看资料、执行结果及审计，下载证据 |

选用「TY-1124-站批」对应的演示资料，保存一份复演资料，再以默认参数 1000 提交。worker 保存结果摘要、业务明细和 SHA-256。复核员登录后在「送电核对单」签署。

## 开发说明

| 部分 | 实现 |
|---|---|
| 前端 | 原生 HTML、CSS、JavaScript ES Modules、Nginx |
| 后端 | Python 3.11、FastAPI、SQLAlchemy、JWT |
| 数据库 | PostgreSQL 16 |
| 后台执行 | Redis 通知、数据库持久任务队列和行锁、Python worker |

从 `backend/src/domain/scenario.py` 修改业务入口和演示口径，运行 `docker compose up -d --build --wait` 查看变更。数据库表结构在 `backend/src/models` 和 `backend/migrations`，输入模型在 `backend/src/schemas`。业务页和请求接口在 `frontend/src/pages`、`frontend/src/api`。资料、执行、复核三个工作流实体各有独立表和 API；场景输入及结果保留在所属资料和批次中。

角色枚举在 `backend/src/constants/roles.py`、`frontend/src/constants/roles.js`，用于服务端访问控制、账号初始化、前端导航与签署。批次状态在 `backend/src/constants/job_state.py`、`frontend/src/constants/states.js`，用于队列、状态 API、状态标记与轮询。登记、提交、完成和签署事件写入审计表。

`COMPOSE_PROJECT_NAME` 设置栈名，`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 设置端口。通过 `DB_PASSWORD`、`JWT_SECRET`、`DEMO_PASSWORD` 配置本地凭据。设置 `SEED_DEMO=false` 可关闭演示数据载入，此时数据库初始没有演示账号。数据库密码调整后，已有数据卷需在数据库内同步修改用户密码。

## 验收范围

各站通过真实保存点独立验收。演练的数据表在事务结束时清理。 当前界面用 JSON 编辑业务资料，以 JSON 下载证据。过程和截图保存在批次的 [验收记录](../../test-artifacts/gb-6103/TESTING.md)。

[MIT License](LICENSE)

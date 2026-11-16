# Trends

Trends 是面向 A 股与港股公司基本面的趋势研究工作台。火山云线上站点覆盖 17 家公司，首批真实数据来自经过核对的发行人公开披露。开发环境默认另用 Mock 样本，两种数据模式分开查询和标识。

## 架构

浏览器通过同一个域名访问 Next.js 页面和 Go API。公开端口由 Go 监听。Go 读取 PostgreSQL，并把页面及静态资源请求转发到容器内的 Next.js。Python 管道在启动时依次执行迁移、读取模拟报表、校验、计算指标、检测规则并写入 PostgreSQL。

观测记录保留期间、数据可用时间、币种、版本和来源。洞察引用确切的观测记录，可回看计算所用的数据。数据库在独立服务运行，Web 与 API 同容器便于首轮部署。

## 云服务器部署

线上入口为 `https://iamcsq.top/trends`。VPS 部署复用服务器上的 PostgreSQL 16 和 Caddy。应用使用独立的 PostgreSQL 数据库及登录角色，通过已有的 Docker 私有网络连接数据库。Compose 只将应用端口 18180 绑定到服务器回环地址，由 Caddy 提供 HTTPS。

1. 在现有 PostgreSQL 上创建应用专用数据库和普通登录角色。将连接串写入服务器上的环境文件，文件权限设为 `0600`；真实披露库同时设置 `TRENDS_DATA_MODE=official`，用 `TRENDS_ENV_FILE` 指向它。
2. 把 Git 提交对应的源码放到服务器，设置 `TRENDS_RELEASE` 为提交号并构建启动。若 PostgreSQL 位于不同 Docker 网络，设置 `TRENDS_PG_NETWORK`。

```sh
docker compose -p trends -f compose.vps.yml up --build -d
curl -fsS http://127.0.0.1:18180/trends/api/v1/health
```

3. 在 Caddy 的 HTTPS 站点块内导入 `deploy/Caddyfile.trends`，用 `caddy validate` 校验后重载。访问 `/trends`，再用下文的 Playwright 脚本验收。
4. 后续发布使用新的源码目录和 `TRENDS_RELEASE`，运行同一条 Compose 命令。回滚时选择上一版源码和镜像标签，保留数据库。

镜像构建默认使用 Docker Hub、Go 官方模块代理、npm 官方 registry 和 Debian 软件源。如服务器访问受限，可通过 `TRENDS_NODE_IMAGE`、`TRENDS_GO_IMAGE`、`TRENDS_GO_PROXY`、`TRENDS_NPM_REGISTRY` 和 `TRENDS_DEBIAN_MIRROR` 指定可达的来源。当前服务器的构建参数保存在 `/opt/trends/shared/build.env`，可通过 Compose 的 `--env-file` 选项复用。

网络受限时，可在发布目录的 `deploy/.build-cache/npm` 放入用锁文件预取的 npm 缓存，在 `deploy/.build-cache/wheels` 放入 Linux amd64 / CPython 3.11 的 PostgreSQL 客户端依赖包。构建会使用可用的缓存离线安装，缓存目录不进入 Git 或最终镜像。

### Render 部署备选

`render.yaml` 配置一个 Docker Web Service 和同区域的 PostgreSQL 17。它使用 Render 免费档作为短期 Mock 验收环境，免费数据库创建 30 天后到期。数据库外网访问关闭，连接地址通过服务环境变量注入。 [Render 免费档说明](https://render.com/docs/free)

1. 将项目推送到可由 Render 访问的 Git 仓库。
2. 在 Render 中创建 Blueprint，选择仓库和分支，应用配置。容器启动时自动执行迁移和 Mock 导入。
3. 打开 Render 生成的网站地址。部署健康检查为 `GET /api/v1/health`。
4. 在云端或 CI runner 上运行验收脚本。

```sh
python -m pip install playwright
python -m playwright install chromium
python tests/smoke.py https://YOUR-SERVICE.onrender.com
```

验收覆盖首页图表、分类筛选、搜索、公司详情、指标和范围切换、洞察证据，以及 API 的 Mock 来源标记。GitHub Actions 工作流 `.github/workflows/smoke.yml` 在云端 runner 上构建并启动整套容器，额外检查导入幂等性。

### Docker Compose 开发入口

```sh
docker compose up --build -d
```

访问 `http://127.0.0.1:8080`。可复制 `.env.example` 设置另一个本地端口。PostgreSQL 数据由 Compose volume 保存。

## 页面

| 路径 | 功能 |
| --- | --- |
| `/` | 跳转至股票探索 |
| `/stocks` | 按名称、代码和市场探索公司 |
| `/stocks/[symbol]` | 近三年六张季度指标趋势图和原始来源 |

## API

所有路径位于 `/api/v1`，成功响应使用 `data`，失败使用 `error.code` 和 `error.message`。

| GET | 参数与用途 |
| --- | --- |
| `/health` | 确认 PostgreSQL 与 Mock 导入可用 |
| `/overview` | 覆盖数量、最新入库时间 |
| `/entities` | `q`、`market=CN\|HK`、`limit`、`offset` |
| `/entities/{id}` | 示例 `0700.HK` |
| `/entities/{id}/quarterly` | 近 12 个完整自然季度的指标观测，包括同币种单季同比 |
| `/metrics` | 指标列表及计算口径 |
| `/series` | 必填 `entity_id`、`metric_id`。默认 `period=annual`，`quarterly` 为单季，`monthly` 为按自然月披露的指标 |
| `/insights` | `entity_id`、`category`、`limit`、`offset` |
| `/insights/{id}` | 规则洞察及对应信号序列 |
| `/insights/{id}/evidence` | 规则使用的观测记录与来源 |

## 真实数据

### AKShare 月度同步

`deploy/akshare` 提供独立的云端同步容器和 systemd timer。任务按北京时间每月 5 日 03:15 查询最近 8 个完整自然季度，另取上年同期供同比计算。首次安装后手动启动一次即可初始化。

同步使用 `AKSHARE_DATABASE_URL` 连接独立的 `trends_akshare` 库。任务保留每次运行与缺失记录，已拉取的季度数据保留来源与修订历史。相同结果重复运行会复用现有版本。公开 API 使用独立的披露数据库，AKShare 数据先在私有库核对。

首批数据来自 [发行人披露清单](services/data-pipeline/data/disclosures.json)。每条记录附有原始文件、公开日期、披露期间、币种和原始单位。导入时校验期间与单位并在一个事务中写入。重复导入同一来源中的同一记录不会写入新版本。

- 股票详情图统一展示最近 12 个完整自然季度，未披露单季留空。财务数据保留发行人报告币种。两项增长率按同币种上年同期计算，利润基期不为正时留空。PE 和股息率按季末口径预留，取得可用于公开展示的市场数据后才会出现数值。
- 小米全球月活跃用户按报告列明的自然月入库。月度序列目前只覆盖已核对的月份，披露月份之外留空。
- 首批关注营业收入、归母净利润和已核对的经营指标。源文件以财报或公司公告链接为主，不保存报告全文。当前导入来自经复核的静态清单，未配置每日自动采集，也未接入需要另行许可的行情数据。

### 理杏仁 API 对账

在运行环境中设置 `LIXINGER_TOKEN`，即可检查理杏仁对当前关注公司的历史覆盖。默认检查全部公司，可重复指定 `--symbol` 缩小范围。

```sh
python3 services/data-pipeline/audit_lixinger.py --start 2024-09-30 --end 2026-09-30 --symbol 000333.SZ --symbol 0700.HK
```

结果按字段列出单季、单半年和年度覆盖，并与披露清单逐项比较。数值按原币种换算到币种主单位再比较，金额舍入、报表重列和字段口径差异均可能产生差异记录。脚本仅输出覆盖和比对状态，不输出令牌或供应商金额，不写入数据库。

## Mock 数据口径

- 原始样本见 `services/data-pipeline/mock_source.py`。无外部数据 API、真实财报披露时间、行情或估值授权。
- 所有样本为年度 CNY。存储货币指标使用十亿 CNY，页面换算为亿元 CNY。同比和利润率以百分数存储，差值以百分点呈现。
- 无可比前期或缺失原值时不创建观测。API 字段 `quality_status=mock` 及 `source_kind=mock` 表示模拟来源。
- 首版规则覆盖营收加速、营收减速、净利率连续变化、利润与现金流背离、资产负债率样本新低。当前洞察内容来自确定性计算。
- 后续接入真实数据前需确认授权范围并保存披露时间，随后可增加季度口径和基于证据的 AI 分析。

## 独立构建与单测

```sh
go -C apps/api test ./...
python3 -m unittest discover -s services/data-pipeline -v
cd apps/web && npm ci && npm run build
```

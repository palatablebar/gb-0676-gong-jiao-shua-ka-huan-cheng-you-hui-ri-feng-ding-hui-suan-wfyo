# 公交刷卡换乘优惠与日封顶回算

供公交清分中心复核员核对原始记录、处理差异并封存证据。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

打开 http://localhost:18245 。首次进入自动运行仓内脏样例。工具条可重跑、切换样例或上传CSV。SQLite保存在命名卷records中，重建服务保留批次。

## 模块

- 1. 刷卡采信：`/taps`，`/api/taps`。
- 2. 线路换乘：`/routes`，`/api/routes`。
- 3. 票价版本：`/fares`，`/api/fares`。
- 4. 行程配对：`/journeys`，`/api/journeys`。
- 5. 优惠回算：`/discounts`，`/api/discounts`。
- 6. 清分对账：`/clearing`，`/api/clearing`。
- 7. 日结归档：`/settlement`，`/api/settlement`。

## 核心规则

换乘按上次有效付费行程的时间窗计算，优惠与日封顶按确定顺序裁决并保留分币守恒。

### 接驳方向裁决

M5 参数 `direction_mode`：`both`（默认）下同一组接驳线路双向对称，接驳方向（支线→主干线）与返程（主干线→支线）均享换乘优惠；`feeder` 下仅承认接驳方向，返程与非接驳组跨线拒绝，每行展示实际采用方向与拒绝理由。配对由 `feeder_links: [[支线,主干线], ...]` 声明。方向规则非法时批次接口不写库，完整沿用最近一次旧版日账并在页面顶部提示回退原因。

### 卡日账与封账

M7 按卡号+业务日聚合，每张卡每日恰好一份日账，含换乘优惠合计、封顶减免合计与封顶应收；日账落 SQLite 唯一表，重跑同一批复用而不新增占额。封账前跨模块守恒闸口校验来源行平衡、清分合计与日账合计相等、分币守恒，未对平一律拒绝封账。证据导出包含 `daily_ledger` 行。

## 演示

1. 打开首页，核对当次计算、差异和隔离原因。
2. 切换模块查看源行及裁决依据。
3. 重跑相同样例，批次号与行数保持一致。
4. 复核后导出一份证据CSV。版本已变化的复核提交返回409。

## 输入与输出

输入列见 `docs/DATA-DICTIONARY.md`。项目包含dirty.csv、clean.csv、legacy.csv，统一走实际导入路径。上传限制4MB，拒绝不带时区的时间。业务键按字符串保留，Decimal参与计算，空值不会当零。

`POST /api/runs` 接收sample或csv；`GET /api/runs`返回历史批次；`POST /api/runs/<id>/review`需要version与decision；`GET /api/runs/<id>/archive`返回唯一证据导出。

## 范围

样例均为虚构。单机复核工具不连接生产系统；不提供登录、远端数据库或自动支付。内存计算按4MB输入上限控制，SQLite事务保证结果完整写入。

## 目录

app为服务与规则，sample_data为输入，tests为测试，docs为定义与深度登记。

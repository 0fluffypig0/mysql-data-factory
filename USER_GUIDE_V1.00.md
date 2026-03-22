# V1.00 详细用户说明书

这份文档面向第一次接触项目的人。

如果你还不知道这个项目到底怎么用，建议先看：

- [`README.md`](./README.md)：总览
- [`DEPLOYMENT.md`](./DEPLOYMENT.md)：堡垒机部署操作

如果你已经准备真正使用它，请从本文开始按顺序操作。

---

## A. 项目设计思路

### A.1 为什么采用 CSV 模板工作流

这个项目选择 CSV 模板工作流，不是因为 CSV 最先进，而是因为它在 V1.00 阶段最稳、最容易交接：

- 数据库里导出的样本可以直接看
- 堡垒机上不需要复杂 UI
- 模板数据可以手工编辑
- 生成结果容易审查
- `dry-run` 之前可以直接打开 CSV 做最后检查

对于发布前的 V1.00，这种方式的优点远大于“功能看起来更高级”。

### A.2 为什么不直接做复杂数据工厂

因为复杂数据工厂通常意味着：

- 多表联动
- 业务规则自动推断
- 外键处理
- 复杂模板系统
- 大量特例逻辑

这些能力做得不好，反而会让现场使用风险更高。

V1.00 的目标不是“全能”，而是“明天能带去堡垒机试，而且有人接手也能用”。

### A.3 为什么 Notebook 不是主入口

Notebook 更适合：

- 调试
- 演示
- 临时探索

但不适合作为正式交付入口，因为它：

- 依赖交互环境
- 不利于标准化操作
- 不利于文档收口
- 不利于在堡垒机上稳定执行

因此，V1.00 的正式入口是：

- Python 脚本
- `.bat` 包装

### A.4 为什么要先 dry-run

`dry-run` 的目的不是“形式上多一步”，而是为了在正式写库前拦住最常见的问题：

- 目标表写错
- CSV 列不匹配
- 主键为空
- 主键在 CSV 内部重复
- JSON 不合法
- batch size 设置不合理

这一步非常重要。V1.00 的使用习惯应该始终是：

先 `dry-run`，再正式插入。

---

## B. 核心概念解释

### B.1 `sample.csv`

从数据库中导出的少量真实样本。

用途：

- 看真实字段结构
- 看真实值长什么样
- 作为模板编辑起点

### B.2 `template.csv`

由人工基于 `sample.csv` 整理出来的模板文件。

用途：

- 保留你想扩增的字段结构
- 保留你想复制的字段内容
- 手工把不合适的样本值改成模板值

### B.3 `generated.csv`

由 `expand_rows.py` 基于模板生成的最终待插入 CSV。

用途：

- 给 `dry-run` 检查
- 给正式插入使用

### B.4 `PRIMARY_KEY_COLUMNS`

必须配置。

表示哪些列是主键列，扩增时这些列需要生成新值，插入前也会重点检查是否为空、是否重复。

### B.5 `UNIQUE_KEY_COLUMNS`

可选配置。

表示哪些列虽然不是主键，但必须变化，否则可能触发唯一键冲突。

### B.6 `TIME_OFFSET_COLUMNS`

可选配置。

表示哪些列属于时间列，需要在扩增时按固定天数或秒数偏移。

### B.7 `JSON_COLUMNS`

可选配置。

表示哪些列是 MySQL 的 JSON 列。

在 V1.00 中，JSON 列的工作方式是：

- 导出时变成 CSV 中的 JSON 字符串
- 扩增时原样复制
- `dry-run` 时做合法性校验
- 正式插入时写回 MySQL JSON 列

### B.8 `dry-run`

正式插入前的检查模式。

它不会写库，但会帮助你提前发现问题。

### B.9 batch insert

正式插入时，程序不会一次把所有行都塞进数据库，而是按批次分段插入。

批次大小由：

- `INSERT_BATCH_SIZE`
- 或 `--batch-size`

控制。

---

## C. 完整使用教程

以下是从零开始的完整使用流程。

### C.1 打包离线环境

在线机执行：

```powershell
python scripts\build_offline_env.py
```

成功后会生成：

```text
env_export\mysql_factory_env.tar.gz
```

### C.2 部署到堡垒机

把仓库和离线环境包一起带到堡垒机后，执行：

```batch
bin\setup_offline.bat
```

### C.3 配置 `.env`

执行：

```batch
copy .env.example .env
notepad .env
```

示例：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=my_user
DB_PASSWORD=my_pass
DB_NAME=my_db
DB_CHARSET=utf8mb4
TARGET_TABLE=demo_table
PRIMARY_KEY_COLUMNS=id
UNIQUE_KEY_COLUMNS=code
TIME_OFFSET_COLUMNS=created_at
JSON_COLUMNS=profile
TIME_OFFSET_DAYS=1
INSERT_BATCH_SIZE=500
CSV_BASE_DIR=data
```

### C.4 测试数据库连接

执行：

```batch
bin\test_connection.bat
```

如果你要用另一个配置文件：

```batch
bin\test_connection.bat --env-file .env.smoke
```

### C.5 导出样本

执行：

```batch
bin\export_sample.bat --table demo_table --limit 3
```

输出文件通常位于：

```text
data\demo_table\sample.csv
```

### C.6 手工修改模板

打开 `sample.csv`，把它整理成你真正想扩增的模板，保存为：

```text
data\demo_table\template.csv
```

建议第一轮只保留 1 到 2 行模板。

### C.7 扩增记录

执行：

```batch
bin\expand_rows.bat --table demo_table --rows 100
```

输出：

```text
data\demo_table\generated.csv
```

### C.8 dry-run 检查

执行：

```batch
bin\insert_csv.bat --table demo_table --dry-run
```

重点检查：

- 表名是否正确
- CSV 路径是否正确
- 总行数是否符合预期
- 主键是否为空
- 主键是否重复
- JSON 是否非法

### C.9 正式插入

确认 `dry-run` 没问题后再执行：

```batch
bin\insert_csv.bat --table demo_table --batch-size 500
```

### C.10 插入后验证

插入完成后，建议你自己再做一次数据库回查：

- 记录总数是否增加
- 新主键是否存在
- 唯一键是否冲突
- JSON 列是否能正常查询

---

## D. 每个脚本的详细说明

### D.1 `test_connection.py` / `bin\test_connection.bat`

作用：

- 读取配置
- 连接数据库
- 执行最小连通性检查
- 可选检查目标表是否存在

关键参数：

- `--env-file`
- `--table`

典型命令：

```batch
bin\test_connection.bat
bin\test_connection.bat --table smoke_users
bin\test_connection.bat --env-file .env.smoke --table smoke_users
```

常见错误：

- `.env` 填错
- 目标表不存在
- 用户权限不足

### D.2 `export_sample.py` / `bin\export_sample.bat`

作用：

- 从单表导出少量样本到 CSV

关键参数：

- `--env-file`
- `--table`
- `--limit`
- `--output`

典型命令：

```batch
bin\export_sample.bat --table customer --limit 3
bin\export_sample.bat --env-file .env.smoke --table smoke_users --limit 2
```

输出位置：

- 默认：`data\<table>\sample.csv`

常见错误：

- 表名写错
- 没有查询权限
- 输出目录无写权限

### D.3 `expand_rows.py` / `bin\expand_rows.bat`

作用：

- 读取模板 CSV
- 生成待插入的 `generated.csv`

关键参数：

- `--env-file`
- `--table`
- `--rows`
- `--pk-cols`
- `--unique-cols`
- `--time-cols`
- `--json-cols`

典型命令：

```batch
bin\expand_rows.bat --table customer --rows 100
bin\expand_rows.bat --env-file .env.smoke --table smoke_users --rows 3
```

输出位置：

- 默认：`data\<table>\generated.csv`

常见错误：

- `template.csv` 不存在
- `PRIMARY_KEY_COLUMNS` 未配置
- 配置里写了 JSON/时间/唯一列，但 CSV 中没有这些列

### D.4 `insert_csv.py` / `bin\insert_csv.bat`

作用：

- 对 `generated.csv` 做检查
- 在通过后批量插入数据库

关键参数：

- `--env-file`
- `--table`
- `--input`
- `--batch-size`
- `--pk-cols`
- `--json-cols`
- `--dry-run`

典型命令：

```batch
bin\insert_csv.bat --table customer --dry-run
bin\insert_csv.bat --table customer --batch-size 500
bin\insert_csv.bat --env-file .env.smoke --table smoke_users --dry-run
```

输出内容：

- 表名
- CSV 路径
- 总行数
- 列名
- batch size
- 主键检查结果
- JSON 检查结果

常见错误：

- 主键为空
- 主键重复
- JSON 非法
- CSV 列与目标表不一致

---

## E. JSON 列使用专题

### E.1 在 CSV 里如何表示 JSON

在 CSV 中，JSON 列不是对象结构，而是“字符串化后的 JSON 内容”。

例如，一个单元格里的内容可能是：

```text
"{""team"":""red"",""score"":10}"
```

### E.2 合法示例

对象：

```json
{"team":"red","score":10}
```

数组：

```json
["a","b","c"]
```

布尔值：

```json
true
```

空对象：

```json
{}
```

### E.3 非法示例

以下都属于非法 JSON：

```text
{team:"red"}
{'team':'red'}
{ "team": "red", }
just text
```

### E.4 空值示例

空单元格表示：

- 不写 JSON 内容
- 插入时按 `NULL` 处理

### E.5 导出/扩增/插入时的行为

导出：

- 保留合法 JSON 字符串

扩增：

- 原样复制 JSON 列

dry-run：

- 检查 JSON 是否合法

正式插入：

- 合法 JSON 写回 MySQL
- 空字符串写成 `NULL`

---

## F. 典型操作案例

### F.1 例子一：普通表（无 JSON）

假设表结构：

- `id`
- `code`
- `created_at`
- `name`

示例 `.env`：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=test
DB_PASSWORD=test
DB_NAME=demo
DB_CHARSET=utf8mb4
TARGET_TABLE=customer_demo
PRIMARY_KEY_COLUMNS=id
UNIQUE_KEY_COLUMNS=code
TIME_OFFSET_COLUMNS=created_at
JSON_COLUMNS=
TIME_OFFSET_DAYS=1
INSERT_BATCH_SIZE=200
```

执行顺序：

```batch
bin\test_connection.bat
bin\export_sample.bat --table customer_demo --limit 2
bin\expand_rows.bat --table customer_demo --rows 20
bin\insert_csv.bat --table customer_demo --dry-run
bin\insert_csv.bat --table customer_demo --batch-size 200
```

### F.2 例子二：含 JSON 列的表

假设表结构：

- `id`
- `code`
- `created_at`
- `name`
- `status`
- `profile`（JSON）

示例 `.env`：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=smoke_user
DB_PASSWORD=smoke_pass
DB_NAME=smoke_factory
DB_CHARSET=utf8mb4
TARGET_TABLE=smoke_users
PRIMARY_KEY_COLUMNS=id
UNIQUE_KEY_COLUMNS=code
TIME_OFFSET_COLUMNS=created_at
JSON_COLUMNS=profile
TIME_OFFSET_DAYS=1
INSERT_BATCH_SIZE=2
```

执行顺序：

```batch
bin\test_connection.bat --env-file .env.smoke --table smoke_users
bin\export_sample.bat --env-file .env.smoke --table smoke_users --limit 2
bin\expand_rows.bat --env-file .env.smoke --table smoke_users --rows 3
bin\insert_csv.bat --env-file .env.smoke --table smoke_users --dry-run
bin\insert_csv.bat --env-file .env.smoke --table smoke_users --batch-size 2
```

这类表的重点检查点是：

- `profile` 是否仍是合法 JSON
- `code` 是否仍保持唯一
- `profile` 插入后能否正常被 `JSON_EXTRACT` 查询

---

## G. 风险与边界

### G.1 当前版本适合什么

- 小到中等规模的单表数据准备
- 离线部署
- 先做模板、再做扩增
- 需要人工可控而不是全自动造数

### G.2 当前版本不适合什么

- 多表导入
- 外键联动
- 自动生成复杂业务数据
- 不经人工检查直接大规模写库

### G.3 什么时候应先在本地 Docker / MySQL 试跑

以下情况建议先在本地或测试库试跑：

- 第一次使用本项目
- 第一次接某张新表
- 第一次配置 `JSON_COLUMNS`
- 第一次调整唯一键规则
- 计划正式插入较大批量数据

### G.4 什么时候必须先 dry-run

答案其实很简单：

- 任何正式插入之前都应该先 dry-run

如果是以下情况，更是必须：

- 新模板
- 新表
- 新配置
- 新增了 JSON 列
- 调整了 `PRIMARY_KEY_COLUMNS` / `UNIQUE_KEY_COLUMNS`

---

## H. FAQ

### H.1 为什么我不直接改 `generated.csv`，而要先有 `sample.csv` 和 `template.csv`？

因为 `sample.csv` 是“真实样本”，`template.csv` 是“人工确认后的模板”，`generated.csv` 是“程序生成的结果”。三者分开，能减少误操作。

### H.2 `UNIQUE_KEY_COLUMNS` 不写会怎样？

如果目标表里存在必须唯一的字段，而你又没有让它变化，正式插入时可能会触发数据库唯一键冲突。

### H.3 JSON 列里能写普通字符串吗？

不能。非空时必须是合法 JSON。

### H.4 JSON 列空着可以吗？

可以。空单元格会按 `NULL` 处理。

### H.5 为什么 `expand_rows.py` 不自动改 JSON 内部字段？

这是 V1.00 的刻意取舍。自动修改 JSON 内部字段很容易引入业务误判，当前版本选择稳妥优先。

### H.6 为什么 `insert_csv.py` 不做 upsert？

因为 V1.00 的目标是“低风险、可审查、可交付”的 plain insert 闭环。`upsert` 容易带来更复杂的行为和更高的误写风险。

### H.7 bat 和 Python 脚本应该用哪个？

堡垒机上优先用 bat。bat 已经指向离线环境中的 Python，可减少环境差异问题。

### H.8 我可以保留多个配置文件吗？

可以。现在主脚本支持：

```text
--env-file your_config.env
```

比如：

```batch
bin\test_connection.bat --env-file .env.smoke
```

### H.9 如果 `dry-run` 通过，是否代表一定能插入成功？

不一定，但风险已经显著降低。`dry-run` 主要检查：

- CSV 结构
- 主键
- JSON 合法性

如果数据库里还有 CSV 外部的唯一键冲突，正式插入时仍可能失败。

### H.10 我第一次上线时最稳妥的做法是什么？

建议：

1. 先在本地 Docker MySQL 跑通
2. 再在测试库跑通
3. 堡垒机上先小批量
4. 永远先 `dry-run`
5. 首次正式插入不要上大批量

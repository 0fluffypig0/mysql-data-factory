# MySQL Data Factory

面向堡垒机/离线环境的单表 MySQL 数据处理工具。

这个项目聚焦一个已经跑通的 V1.00 主流程：

在线机打包离线环境 -> 堡垒机部署 -> 读取 `.env` 连库 -> 导出样本 CSV -> 人工整理模板 -> 扩增记录 -> `dry-run` 检查 -> 批量插入

## 项目简介

这个项目解决的不是“通用数据工厂”问题，而是一个更具体、可落地的问题：

- 在线环境可以联网安装依赖，但堡垒机或隔离区不能联网
- 需要从 MySQL 里取出少量真实样本，人工整理成模板
- 需要基于模板快速扩增出一批新记录
- 在正式写库前，需要先做结构、主键、JSON 合法性等检查

V1.00 的核心思路是：

- 不做复杂平台
- 不做多表编排
- 不做自动业务规则推断
- 先把“单表 CSV 工作流”做成一个稳定、可交接、可离线部署的闭环

## 典型使用场景

最典型的使用方式如下：

1. 在线机执行 `scripts\build_offline_env.py`，生成离线 Python 环境包
2. 将仓库代码和 `env_export\mysql_factory_env.tar.gz` 一起带到堡垒机
3. 堡垒机执行 `bin\setup_offline.bat` 完成离线环境部署
4. 复制 `.env.example` 为 `.env`，填写数据库信息
5. 执行 `bin\test_connection.bat` 验证数据库连通性
6. 执行 `bin\export_sample.bat` 导出 `sample.csv`
7. 人工把 `sample.csv` 改成 `template.csv`
8. 执行 `bin\expand_rows.bat` 生成 `generated.csv`
9. 执行 `bin\insert_csv.bat --dry-run` 做正式插入前检查
10. 确认无误后执行 `bin\insert_csv.bat` 正式批量插入

## 核心特性

- 离线部署：可以在在线机打包 Python 运行环境，再带到无网/堡垒机使用
- 单表 CSV 工作流：围绕 `sample.csv` / `template.csv` / `generated.csv` 展开
- JSON 列支持：MySQL `JSON` 列以“CSV 中 JSON 字符串”的方式参与主流程
- `dry-run`：正式插入前先检查主键、列对齐、JSON 合法性等
- Windows 友好：主入口为 `Python 脚本 + bat`
- 本地 Docker MySQL 已验证：V1.00 闭环已在本地 Docker MySQL 上真实跑通

## 适用范围与限制

当前 V1.00 适合：

- 单表批量数据准备
- 堡垒机/隔离区离线运行
- 先导样本、再人工修模板、再扩增、再插入的场景
- 需要保留真实字段结构而不是纯随机造数的场景

当前 V1.00 不适合：

- 多表联动导入
- 外键编排
- `upsert` / `update` / `delete`
- 自动造复杂假数据
- 复杂业务规则生成
- 以 `.json` / `.jsonl` 作为主输入流程

重要限制说明：

- 当前只支持单表
- 当前只支持 CSV 主流程
- JSON 列支持方式是“CSV 中 JSON 字符串”，不是 JSON 文件主流程
- Notebook 仅保留为参考/调试入口，不是正式主入口

## 仓库结构

```text
mysql-data-factory/
├─ bin/                     Windows 入口脚本
├─ scripts/                 主流程 Python 脚本
├─ src/                     复用模块
├─ env_export/              在线机构建出的离线环境包
├─ README.md                GitHub 首页总览
├─ DEPLOYMENT.md            堡垒机部署操作说明
├─ USER_GUIDE_V1.00.md      超详细 V1.00 使用说明书
├─ QUICKSTART.txt           最短操作顺序
├─ .env.example             配置模板
└─ requirements.txt         离线环境依赖列表
```

## 最小使用流程

### 1. 在线机打包离线环境

```powershell
python scripts\build_offline_env.py
```

### 2. 堡垒机部署离线环境

```batch
bin\setup_offline.bat
```

### 3. 准备配置文件

```batch
copy .env.example .env
notepad .env
```

### 4. 测试连接

```batch
bin\test_connection.bat
```

### 5. 导出样本

```batch
bin\export_sample.bat --table your_table --limit 3
```

### 6. 人工整理模板

把：

```text
data\your_table\sample.csv
```

整理为：

```text
data\your_table\template.csv
```

### 7. 扩增记录

```batch
bin\expand_rows.bat --table your_table --rows 100
```

### 8. dry-run

```batch
bin\insert_csv.bat --table your_table --dry-run
```

### 9. 正式插入

```batch
bin\insert_csv.bat --table your_table --batch-size 500
```

## `--env-file` 支持

V1.00 发布前已补齐 `--env-file` 支持，以下脚本都可以显式指定配置文件：

- `test_connection.py`
- `export_sample.py`
- `expand_rows.py`
- `insert_csv.py`

例如：

```batch
bin\test_connection.bat --env-file .env.smoke --table smoke_users
```

默认仍然读取项目根目录下的 `.env`。

## 文档导航

- 堡垒机部署操作说明：[`DEPLOYMENT.md`](./DEPLOYMENT.md)
- 超详细 V1.00 用户说明书：[`USER_GUIDE_V1.00.md`](./USER_GUIDE_V1.00.md)
- 最短上手步骤：[`QUICKSTART.txt`](./QUICKSTART.txt)

## 常见问题入口

如果你第一次接触这个项目，建议按下面顺序看文档：

1. 先看本文，理解项目目标和边界
2. 真正要部署到堡垒机时，看 `DEPLOYMENT.md`
3. 真正要操作 sample/template/generated 流程时，看 `USER_GUIDE_V1.00.md`
4. 临时现场操作时，看 `QUICKSTART.txt`

常见问题通常集中在：

- 离线环境包没有生成成功
- 堡垒机缺少 `tar` 或权限不足
- `.env` 配置错误导致连接失败
- `PRIMARY_KEY_COLUMNS` / `UNIQUE_KEY_COLUMNS` / `JSON_COLUMNS` 配置不正确
- `generated.csv` 中主键或 JSON 数据不合法
- 没有先做 `dry-run` 就直接插入

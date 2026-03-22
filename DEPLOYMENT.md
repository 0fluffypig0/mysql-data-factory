# 堡垒机部署操作说明

本文档面向实际部署人员，重点说明如何在 Windows 在线机上打包离线环境，并在无网/堡垒机环境中完成部署与首次使用。

这份文档不是概述，而是按操作顺序编写的部署说明书。

---

## 1. 部署前准备

### 1.1 在线机需要具备什么

在线机建议满足以下条件：

- Windows 系统
- 可以联网下载 Conda/Python 依赖
- 可以正常运行 `python`
- 可以正常运行 Conda
- 当前仓库已经拉到本地

在线机的作用只有两个：

- 生成离线 Python 环境包
- 整理要带去堡垒机的交付目录

### 1.2 堡垒机需要具备什么

堡垒机建议满足以下条件：

- Windows 系统
- 不要求联网
- 不要求预装 Python
- 不要求预装 Conda
- 可以执行 `.bat`
- 可以使用 `tar`
- 对 `C:\tools\mysql_factory_env` 有写权限
- 可以访问目标 MySQL

### 1.3 需要带走哪些文件

至少需要带走以下内容：

```text
mysql-data-factory\
├─ env_export\
│  └─ mysql_factory_env.tar.gz
├─ bin\
├─ scripts\
├─ src\
├─ README.md
├─ DEPLOYMENT.md
├─ USER_GUIDE_V1.00.md
├─ QUICKSTART.txt
├─ .env.example
└─ requirements.txt
```

其中最关键的是：

- `env_export\mysql_factory_env.tar.gz`
- `bin\setup_offline.bat`
- `.env.example`

如果没有离线环境包，堡垒机无法直接运行主流程。

---

## 2. 在线机操作

### 2.1 进入仓库目录

示例：

```powershell
cd /d D:\996.NTTDATA\002.mysql-data-factory
```

### 2.2 生成离线环境包

最常用命令：

```powershell
python scripts\build_offline_env.py
```

如果你需要强制重建环境：

```powershell
python scripts\build_offline_env.py --rebuild
```

如果在线机有多套 Python/Conda，可以显式指定：

```powershell
D:\016.Miniconda\python.exe scripts\build_offline_env.py --conda-exe D:\016.Miniconda\condabin\conda.bat
```

### 2.3 打包成功的判据

成功后，命令行会看到类似结果：

```text
Build complete.
Environment prefix: ...
Output: ...\env_export\mysql_factory_env.tar.gz
Size: ...
```

同时请确认以下文件真实存在：

```text
env_export\mysql_factory_env.tar.gz
```

如果这个文件不存在，说明打包没有真正成功。

### 2.4 如何准备交付目录

建议直接把整个仓库目录打包或复制带走，不要只带单个脚本。

推荐交付内容：

- 仓库代码
- `env_export\mysql_factory_env.tar.gz`
- `README.md`
- `DEPLOYMENT.md`
- `USER_GUIDE_V1.00.md`
- `QUICKSTART.txt`
- `.env.example`

这样堡垒机使用者拿到手后，不需要再猜路径或找文档。

---

## 3. 堡垒机部署步骤

这一节请严格按顺序执行。

### 3.1 复制项目到堡垒机

假设你把项目放到了：

```text
D:\deploy\mysql-data-factory
```

进入该目录：

```batch
cd /d D:\deploy\mysql-data-factory
```

### 3.2 运行离线环境部署脚本

执行：

```batch
bin\setup_offline.bat
```

### 3.3 `bin\setup_offline.bat` 会做什么

该脚本会自动完成以下步骤：

1. 检查 `env_export\mysql_factory_env.tar.gz` 是否存在
2. 把离线环境解压到 `C:\tools\mysql_factory_env`
3. 执行 `conda-unpack`
4. 验证 `python.exe` 是否可以运行

### 3.4 成功时你应该看到什么

成功时通常会看到类似输出：

```text
[1/4] Preparing target directory...
[2/4] Extracting offline environment...
[3/4] Running conda-unpack...
[4/4] Verifying python.exe...
Python 3.10.x
Offline environment is ready.
```

### 3.5 如何确认 Python 环境真的可用

除了 `setup_offline.bat` 的成功输出外，还可以额外执行：

```batch
C:\tools\mysql_factory_env\python.exe --version
```

如果能正常输出 Python 版本，说明离线环境已经具备基本可运行性。

### 3.6 准备 `.env`

复制模板：

```batch
copy .env.example .env
```

然后编辑：

```batch
notepad .env
```

### 3.7 `.env` 至少需要填写哪些内容

最小配置如下：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database
DB_CHARSET=utf8mb4
TARGET_TABLE=your_table
PRIMARY_KEY_COLUMNS=id
```

常用可选项如下：

```env
UNIQUE_KEY_COLUMNS=
TIME_OFFSET_COLUMNS=
JSON_COLUMNS=
TIME_OFFSET_DAYS=0
TIME_OFFSET_SECONDS=0
EXPORT_SAMPLE_LIMIT=3
INSERT_BATCH_SIZE=500
CSV_BASE_DIR=data
```

### 3.8 填写数据库配置时的注意点

- `DB_HOST` / `DB_PORT` 必须能从堡垒机连到目标 MySQL
- `DB_USER` / `DB_PASSWORD` 必须有查询和插入目标表的权限
- `TARGET_TABLE` 必须是单个表名
- `PRIMARY_KEY_COLUMNS` 必填
- `UNIQUE_KEY_COLUMNS` 只填写确实需要按序变化的列
- `JSON_COLUMNS` 只填写 MySQL 里的 JSON 列

### 3.9 用 `bin\test_connection.bat` 验证

执行：

```batch
bin\test_connection.bat
```

如果你要显式指定配置文件：

```batch
bin\test_connection.bat --env-file .env
```

成功判据：

- 能看到数据库主机、端口、数据库名
- `SELECT 1` 成功
- 如果配置了目标表，表存在检查通过

---

## 4. 堡垒机上的首次使用流程

### 4.1 导出样本

执行：

```batch
bin\export_sample.bat --table your_table --limit 3
```

如果省略 `--table`，脚本会使用 `.env` 里的 `TARGET_TABLE`。

成功后默认输出到：

```text
data\your_table\sample.csv
```

### 4.2 生成人工模板

打开：

```text
data\your_table\sample.csv
```

把其中 1 到 2 行改成你要扩增的模板，另存为：

```text
data\your_table\template.csv
```

建议第一轮先做少量记录，不要一开始就上万行。

### 4.3 扩增记录

执行：

```batch
bin\expand_rows.bat --table your_table --rows 100
```

如果要显式指定 env：

```batch
bin\expand_rows.bat --env-file .env --table your_table --rows 100
```

成功后输出：

```text
data\your_table\generated.csv
```

扩增规则是：

- 主键列递增
- 必要唯一键列递增
- 时间列按固定偏移递增
- JSON 列原样复制
- 其他列保持模板值

### 4.4 先做 `dry-run`

执行：

```batch
bin\insert_csv.bat --table your_table --dry-run
```

成功时至少会输出：

- 目标表
- CSV 路径
- 总记录数
- 列名
- batch size
- 主键列
- 空主键行数
- CSV 内部重复主键数
- JSON 列名
- 非法 JSON 行数
- JSON 错误示例行（若有）

只有 `dry-run` 通过后，才建议正式插入。

### 4.5 正式插入

执行：

```batch
bin\insert_csv.bat --table your_table --batch-size 500
```

如果你在 `.env` 中已经设置 `INSERT_BATCH_SIZE`，也可以省略该参数。

正式插入前建议再次确认：

- 目标表是否正确
- `generated.csv` 是否是最终版本
- JSON 字段是否仍是合法 JSON 字符串
- 主键/唯一键是否不会与线上已有数据冲突

---

## 5. JSON 列配置说明

### 5.1 `JSON_COLUMNS` 是什么

`JSON_COLUMNS` 用来声明哪些列是 MySQL JSON 列，例如：

```env
JSON_COLUMNS=profile,extra_info
```

### 5.2 CSV 中 JSON 列应该长什么样

CSV 中的 JSON 列，本质上是“一个单元格里的 JSON 字符串”。

合法示例：

```text
"{""team"":""red"",""score"":10}"
```

更容易阅读的等价 JSON 内容是：

```json
{"team":"red","score":10}
```

### 5.3 空值规则

V1.00 的规则很简单：

- 空单元格：按 `NULL` 处理
- 非空单元格：必须是合法 JSON
- 不会自动修改 JSON 内部字段

### 5.4 导出阶段如何处理 JSON

`export_sample.py` 会把 JSON 列导成合法 JSON 字符串，保证：

- 可以继续写入 CSV
- 可以继续作为 `template.csv`
- 可以继续被 `insert_csv.py` 做合法性校验

### 5.5 扩增阶段如何处理 JSON

`expand_rows.py` 不会动 JSON 内部字段。

也就是说：

- 不做 JSON patch
- 不做路径替换
- 不做内部字段自动递增

### 5.6 插入阶段如何处理 JSON

`insert_csv.py` 会在 `dry-run` 和正式插入前验证 JSON：

- 合法 JSON 才允许通过
- 非法 JSON 会报错并给出示例行
- 空字符串会写成 `NULL`

---

## 6. 常见报错与排查

### 6.1 `conda-unpack` 报错

常见原因：

- 解压不完整
- 目标目录权限不足
- 离线包损坏

排查建议：

1. 重新执行 `bin\setup_offline.bat`
2. 确认 `env_export\mysql_factory_env.tar.gz` 完整存在
3. 确认 `C:\tools\mysql_factory_env` 可写

### 6.2 提示找不到 `tar`

常见原因：

- 堡垒机没有可用的 Windows `tar`

排查建议：

- 先在命令行执行 `tar --version`
- 如果不可用，需要由堡垒机环境提供 `tar`

### 6.3 提示权限不足

常见原因：

- 无法创建 `C:\tools\mysql_factory_env`
- 无法写入当前项目目录下的 `data\`

排查建议：

- 确认当前账号有目录写权限
- 必要时让管理员提前创建目标目录

### 6.4 `.env` 配置错误

表现可能包括：

- 数据库连不上
- 连接到错误的库
- 导出的不是预期表
- 插入到了错误表

排查建议：

1. 先执行 `bin\test_connection.bat`
2. 检查 `DB_HOST` / `DB_PORT`
3. 检查 `DB_NAME`
4. 检查 `TARGET_TABLE`
5. 检查 `PRIMARY_KEY_COLUMNS`

### 6.5 连接失败

常见原因：

- 主机不可达
- 端口不通
- 用户名密码错误
- 防火墙限制
- 数据库权限不足

排查建议：

- 先确认堡垒机能访问目标 MySQL
- 再确认账号权限

### 6.6 编码问题

如果控制台输出出现乱码或特殊符号问题：

- 优先使用仓库自带 bat 入口
- 不要随意换成系统 PATH 下的 Python
- 如果是 CSV 打开后显示异常，优先用支持 UTF-8 的编辑器查看

### 6.7 JSON 非法

表现：

- `dry-run` 提示 `Invalid JSON rows`
- 给出具体行号和列名

排查建议：

- 检查该单元格是不是合法 JSON
- 确认花括号、方括号、引号是否闭合
- 确认不要把普通文本误填进 JSON 列

### 6.8 主键或唯一键冲突

表现：

- `dry-run` 报 CSV 内部主键重复
- 正式插入时报数据库唯一键冲突

排查建议：

- 检查 `PRIMARY_KEY_COLUMNS`
- 检查 `UNIQUE_KEY_COLUMNS`
- 确认模板中的唯一列是否需要人工改写
- 必要时先小批量验证

---

## 7. 部署成功后的目录结构示例

示例：

```text
D:\deploy\mysql-data-factory\
├─ bin\
├─ scripts\
├─ src\
├─ env_export\
│  └─ mysql_factory_env.tar.gz
├─ README.md
├─ DEPLOYMENT.md
├─ USER_GUIDE_V1.00.md
├─ QUICKSTART.txt
├─ .env.example
├─ .env
└─ data\
   └─ your_table\
      ├─ sample.csv
      ├─ template.csv
      └─ generated.csv
```

离线 Python 运行时默认部署到：

```text
C:\tools\mysql_factory_env
```

---

## 8. 安全注意事项

- 不要把真实 `.env` 提交到 git
- 不要把测试配置混入正式环境
- 不要跳过 `dry-run`
- 不要在未确认目标表前直接正式插入
- 不要把本地 Docker 测试库配置误用于正式堡垒机
- 不要把临时测试 CSV 当成正式交付数据

---

## 9. 推荐的最小上线习惯

为了降低风险，建议每次都遵守以下顺序：

1. 先 `test_connection`
2. 再 `export_sample`
3. 再人工检查 `template.csv`
4. 再 `expand_rows`
5. 再 `dry-run`
6. 最后才正式插入

如果你是第一次部署这套工具，强烈建议先在本地 Docker MySQL 或测试库中完整走一遍，再上堡垒机连接正式库。

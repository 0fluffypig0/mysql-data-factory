> 本文档提供完整的部署流程，包括离线部署和在线开发两种场景。

---

## 📋 目录

- [🎯 部署场景选择](#-部署场景选择)
- [📦 场景一：离线部署（推荐）](#-场景一离线部署推荐)
- [💻 场景二：在线开发](#-场景二在线开发)
- [🔧 配置数据库连接](#-配置数据库连接)
- [🚀 运行项目](#-运行项目)
- [❌ 故障排除](#-故障排除)
- [❓ 常见问题](#-常见问题)

---

## 🎯 部署场景选择

| 场景 | 适用情况 | 是否需要联网 | 是否需要预装环境 |
|------|---------|-------------|-----------------|
| **离线部署** | 堡垒机、隔离网络、生产环境 | ❌ 否 | ❌ 否（解压即用） |
| **在线开发** | 本地开发、测试、调试 | ✅ 是 | ✅ 是（需安装 conda） |

**推荐使用离线部署**：一次打包，多处使用，无需重复安装。

---

## 📦 场景一：离线部署（推荐）

### 阶段 1：准备离线包（在可联网的开发机）

> ⚠️ 此步骤只需执行一次，生成的离线包可重复使用。

#### 1.1 安装依赖工具

```powershell
# 1. 下载并安装 Miniconda (Windows)
# 地址：https://docs.conda.io/en/latest/miniconda.html
# 选择：Miniconda3-latest-Windows-x86_64.exe
# 安装时勾选 "Add to PATH"

# 2. 验证安装
conda --version
# 输出：conda 24.x.x
```

#### 1.2 克隆项目

```powershell
# 克隆仓库
git clone https://github.com/yourname/mysql-data-factory.git
cd mysql-data-factory
```

#### 1.3 运行打包脚本

```powershell
# 运行简化版打包脚本
python scripts\create_offline_env_simple.py
```

**执行过程：**
```
============================================================
MySQL Data Factory - 离线环境构建
============================================================

[1/4] 检查 conda...
✓ Conda 可用

[2/4] 创建 conda 环境: mysql_factory
✓ 环境创建成功

[3/4] 安装包...
  安装 pymysql...
  安装 sqlalchemy...
  ... (约 5-10 分钟)
✓ 所有包安装完成

[4/4] 打包环境...
  安装 conda-pack...
✓ 打包完成: env_export\mysql_factory_env.tar.gz (456.32 MB)

============================================================
🎉 离线环境构建完成！
============================================================
```

#### 1.4 验证输出

```powershell
# 检查生成的文件
ls -lh env_export\

# 应该看到：
# mysql_factory_env.tar.gz  ~300-600MB
# README_OFFLINE.md         部署说明
```

#### 1.5 准备交付物

将整个项目文件夹复制到可移动存储或内部网络：

```
mysql-data-factory/
├── env_export/
│   ├── mysql_factory_env.tar.gz  ← 核心离线包
│   └── README_OFFLINE.md
├── bin/
│   ├── setup_offline.bat         ← 一键部署脚本
│   └── run_notebook.bat
├── src/
├── notebooks/
├── scripts/
├── .env.example
└── README.md
```

---

### 阶段 2：堡垒机部署（完全离线）

> ✅ 此阶段无需安装 Python、无需安装 conda、无需联网

#### 2.1 复制项目到堡垒机

将整个 `mysql-data-factory` 文件夹复制到堡垒机，例如：

```
D:\deploy\mysql-data-factory\
```

#### 2.2 运行部署脚本

```batch
# 进入项目目录
cd /d D:\deploy\mysql-data-factory

# 运行一键部署脚本
bin\setup_offline.bat
```

**执行过程：**
```
========================================
MySQL Data Factory - 离线环境部署
========================================

[检查] 检查离线环境包...
[信息] 找到离线环境包
  D:\deploy\mysql-data-factory\env_export\mysql_factory_env.tar.gz

[1/3] 创建环境目录...
  创建目录: C:\tools\mysql_factory_env

[2/3] 解压环境包...
  目标目录: C:\tools\mysql_factory_env

[3/3] 修复路径...
  ✓ 路径修复完成

========================================
✓ 离线环境部署完成！
========================================

环境路径: C:\tools\mysql_factory_env
Python: C:\tools\mysql_factory_env\python.exe

下一步:
  1. 复制.env.example 为.env
  2. 编辑.env 配置数据库信息
  3. 运行 bin\run_notebook.bat
```

#### 2.3 配置数据库连接

```batch
# 复制配置模板
copy .env.example .env

# 编辑配置文件
notepad .env
```

填入你的数据库信息：

```env
# 数据库连接
DB_HOST=jump-jp.ebaocloud.com
DB_PORT=33061
DB_USER=your_user_id
DB_PASSWORD=your_password
DB_NAME=cloverit_bo_db
DB_CHARSET=utf8mb4

# 目标表
TARGET_TABLE=t_legal

# 批量插入配置
BATCH_SIZE=1000

# 数据生成
FAKER_LOCALE=ja_JP
```

#### 2.4 验证环境

```batch
# 测试 Python 环境
C:\tools\mysql_factory_env\python.exe --version
# 输出：Python 3.10.x

# 测试关键依赖
C:\tools\mysql_factory_env\python.exe -c "import pymysql; print('OK')"
# 输出：OK
```

---

## 💻 场景二：在线开发

> 适用于本地开发、测试、调试

### 2.1 安装依赖

```powershell
# 1. 安装 Miniconda（如果未安装）
# 地址：https://docs.conda.io/miniconda.html

# 2. 克隆项目
git clone https://github.com/yourname/mysql-data-factory.git
cd mysql-data-factory
```

### 2.2 创建环境

```powershell
# 方式 A：使用 environment.yml（推荐）
conda env create -f environment.yml

# 方式 B：手动创建
conda create -n mysql_factory python=3.10 -y
conda activate mysql_factory
conda install pymysql pandas sqlalchemy faker python-dotenv loguru jupyter -y
```

### 2.3 激活环境

```powershell
conda activate mysql_factory
```

### 2.4 配置并运行

```powershell
# 配置数据库
copy .env.example .env
notepad .env  # 编辑配置

# 启动 Jupyter
jupyter notebook notebooks/01_workflow.ipynb
```

---

## 🔧 配置数据库连接

无论哪种部署方式，都需要配置 `.env` 文件。

### 配置项说明

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DB_HOST` | 数据库主机地址 | `jump-jp.#####.com` |
| `DB_PORT` | 数据库端口 | `3306` |
| `DB_USER` | 数据库用户名 | `8bcebb8e-xxxx-xxxx` |
| `DB_PASSWORD` | 数据库密码 | `your_password` |
| `DB_NAME` | 数据库名 | `######_db` |
| `DB_CHARSET` | 字符集 | `utf8mb4` |
| `TARGET_TABLE` | 目标表名 | `######` |
| `BATCH_SIZE` | 批量插入数量 | `1000` |
| `FAKER_LOCALE` | 数据生成语言 | `######` |

### 安全建议

- ✅ `.env` 文件**不要**提交到 Git（已在 `.gitignore` 中）
- ✅ 使用环境变量管理敏感信息
- ✅ 定期轮换数据库密码

---

## 🚀 运行项目

### 方式 1：Jupyter Notebook（推荐）

```batch
bin\run_notebook.bat
```

浏览器会自动打开，进入 `notebooks/01_workflow.ipynb`，按顺序执行单元格即可。

### 方式 2：Python 脚本

```batch
# 运行查询脚本
bin\run_query.bat

# 运行批量插入脚本
bin\bulk_insert.bat
```

### 方式 3：直接使用 Python

```powershell
# 使用离线环境的 Python
C:\tools\mysql_factory_env\python.exe scripts\your_script.py
```

---

## ❌ 故障排除

### 问题 1：`conda-unpack.exe` 报错

**现象：**
```
[3/3] 修复路径...
Error: Path mismatch...
```

**解决：**
```batch
# 1. 确保解压路径与打包路径不同
# 2. 手动运行修复
C:\tools\mysql_factory_env\Scripts\conda-unpack.exe

# 3. 如果仍失败，重新打包环境
```

### 问题 2：数据库连接失败

**现象：**
```
✗ 连接失败: Can't connect to MySQL server
```

**排查步骤：**
```powershell
# 1. 测试网络连通性
Test-NetConnection jump-jp.ebaocloud.com -Port 33061

# 2. 检查.env配置
type .env

# 3. 验证账号权限（在 A5:SQL 中测试）
```

**常见原因：**
- ❌ 数据库主机/端口错误
- ❌ 用户名或密码错误
- ❌ 来源 IP 未加入白名单
- ❌ 数据库未启动

### 问题 3：Python 找不到模块

**现象：**
```
ModuleNotFoundError: No module named 'pymysql'
```

**解决：**
```powershell
# 1. 确认使用了正确的 Python
C:\tools\mysql_factory_env\python.exe --version

# 2. 确认已执行 conda-unpack
C:\tools\mysql_factory_env\Scripts\conda-unpack.exe

# 3. 检查环境变量（可选）
set PYTHONPATH=C:\tools\mysql_factory_env\Lib\site-packages
```

### 问题 4：Jupyter 无法启动

**现象：**
```
ERROR: Failed to start notebook server
```

**解决：**
```batch
# 1. 尝试直接启动
C:\tools\mysql_factory_env\python.exe -m jupyter notebook

# 2. 检查端口占用
netstat -ano | findstr :8888

# 3. 指定其他端口
C:\tools\mysql_factory_env\python.exe -m jupyter notebook --port 8889
```

### 问题 5：插入数据失败

**现象：**
```
✗ 批量插入失败: Duplicate entry 'xxx' for key 'PRIMARY'
```

**解决：**
```python
# 1. 检查主键是否重复
# 2. 使用 generate_from_sample 时确保主键递增
# 3. 或先删除测试数据再重试
```

---

## ❓ 常见问题

### Q: 离线包有多大？
**A:** 约 300-600MB，取决于安装的包数量。

### Q: 可以在不同 Windows 版本间使用吗？
**A:** 可以。Windows 10/11/Server 2019+ 均兼容。

### Q: 可以在 Linux 上使用 Windows 打包的环境吗？
**A:** ❌ 不可以。必须同系统打包和使用。

### Q: 如何更新离线包中的依赖？
**A:** 
1. 在开发机修改 `requirements.txt`
2. 重新运行 `create_offline_env_simple.py`
3. 复制新生成的 `mysql_factory_env.tar.gz` 到堡垒机

### Q: 可以只打包部分依赖吗？
**A:** 可以。修改脚本中的 `packages` 列表，只安装需要的包。

### Q: 如何验证离线环境是否完整？
**A:** 运行测试命令：
```powershell
C:\tools\mysql_factory_env\python.exe -c "
import pymysql, pandas, sqlalchemy, faker, jupyter
print('✓ 所有核心依赖可用')
"
```

---

## 📞 获取帮助

- 📖 查看 `README.md` 了解项目概览
- 🔍 查看 `notebooks/01_workflow.ipynb` 了解使用流程
- 🐛 提交 Issue: https://github.com/yourname/mysql-data-factory/issues
- 💬 联系维护者: your.email@example.com

---

> 📅 文档最后更新: 2026-03-16  
> 🔄 项目版本: 1.0.0
```

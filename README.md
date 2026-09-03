# ql_scripts

> 借助 AI 编写并调试的青龙面板脚本库，持续学习与更新中，欢迎指导与使用。

[![GitHub stars](https://img.shields.io/github/stars/lxpkwwz/ql_scripts)](https://github.com/lxpkwwz/ql_scripts/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/lxpkwwz/ql_scripts)](https://github.com/lxpkwwz/ql_scripts/network)
[![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 📦 订阅链接

### 青龙面板中新建订阅，填入以下任一链接即可：
### 直连订阅

ql repo https://github.com/lxpkwwz/ql_scripts.git "" "backup" "" "" "py|yaml|sh|js"

### 代理订阅（国内网络不佳时使用）（推荐）

ql repo https://gh-proxy.com/https://github.com/lxpkwwz/ql_scripts.git "" "backup" "" "" "py|yaml|sh|js"

---

## 📜 脚本详情

### 1. depends_install.py – 青龙面板全依赖自动安装

**功能说明**  
自动检测并安装预设的 青龙面板运行 Python 脚本所需的常用依赖库（如 requests, beautifulsoup4, pandas, numpy 等），跳过已安装的包，避免重复安装。

**特点**  
- 无需人工干预，适合新部署的青龙容器。
- 自动跳过已安装依赖，节省时间。
- 默认定时：建议设置为开机运行一次即可。
- 可自行修改脚本添加确实的依赖

**使用方法**  
1. 将脚本上传至青龙 `scripts` 目录。  
2. 创建定时任务，命令填写 `task depends_install.py`。  
3. 设置 Cron 为 `@reboot` 或运行一次后禁用。

---

### 2. tianyi_checkin.py – 天翼云盘自动签到（疑似失效）

**功能说明**  
模拟天翼云盘网页版签到，获取云存储空间容量奖励。

**特点**  
- 支持多账号（需配置多个环境变量）。
- 签到结果通过青龙通知渠道推送（成功/失败）。
- 自动处理 Cookie 刷新。

**配置方法**  
在青龙面板的「环境变量」中添加以下变量：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `TY_USER` | 天翼云盘手机号 | `13800138000` |
| `TY_PWD` | 天翼云盘密码（需 MD5 加密） | `e10adc3949ba59abbe56e057f20f883e` |

*密码 MD5 加密可在网上搜索在线工具计算。*  
若需多账号，使用相同变量名加数字后缀（如 `TY_USER1`, `TY_PWD1`）。

**定时建议**  
每天一次，例如：`0 8 * * *`（每天早晨 8 点）

---

### 3. ddnsto_renew.py – ddnsto 免费续期，2026.6.8实测正常


自动为 DDNSTO 路由器续费免费套餐，支持多账户多设备。

#### 功能特点

- ✅ 支持多账户多设备
- ✅ 自动识别设备 UID 并转换为数字 ID
- ✅ 青龙面板通知集成
- ✅ 支持 push+ 推送回退
- ✅ 每周一自动执行（可配置）

#### 使用方法

##### 1. 获取 Cookie

1. 登录 [DDNSTO 管理后台](https://web.ddnsto.com/new-app/)
2. 打开浏览器开发者工具（F12），切换到 Network 标签
3. 刷新页面，点击任意请求
4. 在 Request Headers 中找到 Cookie 字段，复制完整内容

##### 2. 获取设备标识

支持两种格式：
- **UID 格式（推荐）**：路由器列表页面显示的设备 UID（如 `8ac12dfe9738`）
- **ID 格式**：数字 ID（如 `817023`）

##### 3. 配置环境变量

在青龙面板添加以下环境变量：

| 变量名 | 说明 |
|--------|------|
| `ddnsto` | 账号配置（必填） |
| `plustoken` | push+ 推送 token（可选） |

###### ddnsto环境变量配置格式

```
# 单账号单设备
cookie#uid

# 单账号多设备（用 # 分隔）
cookie#uid1#uid2

# 多账号多设备（用 & 分隔）
cookie1#uid#uid1&cookie2#uid2#uid3

# 完整示例
csrftoken=xxx;sessionid=yyy#8ac12dfe9738#eea71f9422dc
```

##### 4. 添加定时任务

```bash
# 每周一 9 点执行
0 9 * * 1
```

#### 脚本说明

##### 执行流程

1. 解析环境变量，提取账号配置
2. 对于每个账号的每个设备：
   - 如果是 UID 格式，自动获取对应的数字 ID
   - 创建免费套餐订单
   - 将订单绑定到设备
3. 汇总结果并发送通知

##### 通知方式

1. **青龙面板通知**（优先）
2. **push+ 推送**（回退）

#### 注意事项

- Cookie 可能会过期，需要定期更新
- 每个账号每周只能续费一次
- 确保 Cookie 包含 `csrftoken` 和 `sessionid`

---

### 4. mi_battery_price_watch.py – 小米电池换新价格预警

#### ✨ 特性
- ✅ 严格匹配：仅监控 WATCH_LIST 中显式填写的机型，不会误报相似型号
- 📱 89 款机型参考：内置全量机型列表，方便直接复制粘贴
- 💰 价格变动通知：自动记录历史价格，仅当价格变化时触发通知（支持青龙 notify 模块）
- 🧩 多系列支持：覆盖小米数字系列、Redmi K 系列、Redmi Note 系列、Civi/Turbo 等
- ⏱️ 定时运行：建议每 30 分钟执行一次，及时感知价格调整

#### 🔧 配置方法
编辑脚本开头的「配置区域」：
1. WATCH_LIST —— 要监控的机型（必填）
将下方「参考列表」中的完整名称原样复制到 WATCH_LIST 中，例如：

```
python
WATCH_LIST = [
    "Xiaomi 14 Pro 电池换新服务",
    "Redmi K70 电池换新服务",
    "Xiaomi 15 Ultra 电池换新服务"
]
```

如果设置为空列表 []，则会监控所有可用机型（不推荐，会产生大量无关数据）。

2. REFERENCE_MODELS —— 参考列表（已有 89 款）
脚本内已包含当前所有可用的机型名称，直接从该列表中复制需要的名称即可。
列表按字母排序，涵盖了：
```
Xiaomi 数字系列（9 ~ 15 Ultra）
Redmi K 系列（K30 ~ K80）
Redmi Note 系列（Note 8 ~ Note 15R）
Civi / Turbo 系列等
```

3. PRODUCT_SERIES —— 系列 ID（一般无需修改）
不同产品系列对应的后端接口 ID，已按官方分类预置。

4. 价格记录文件
脚本会在同目录下自动生成 mi_battery_strict_prices.json 用于保存上次价格，请勿手动删除。

#### 📝 注意事项
- 价格数据从小米官方 API 获取，实时准确。
- 仅当价格发生变动时才会发送通知（不会重复通知相同价格）。
- 如果小米官方调整了产品名称，需要同步更新 WATCH_LIST 和 REFERENCE_MODELS 中的名称。
- 建议配合青龙面板使用，独立运行时也可输出日志供其他脚本调用。
---

### 5. github_monitor.py – GitHub 仓库代码提交监控

**功能说明**  
监控指定 GitHub 仓库的默认分支代码提交（push），通过青龙面板通知渠道实时推送更新详情。

**特点**  
- 支持监控多个公开/私有仓库。
- 自动识别仓库默认分支（main/master）。
- 捕获长时间未运行期间的所有新提交（最多 30 条），一次性汇总通知。
- 时间自动转换为北京时间（UTC+8）。
- 支持 GitHub Token（提高 API 速率限制，可访问私有仓库）。
- 本地状态持久化，避免重复通知。

**配置方法**  
编辑脚本顶部的配置区：

```
# 必填：要监控的仓库（用户名/仓库名）
REPOS = [
    "xxx/yyy",
    "lxpkwwz/ql_scripts",
    ...
]

# 可选：GitHub Token（强烈建议填写）
GITHUB_TOKEN = "ghp_xxxxxxxxxxxx"
```

### 定时建议
每 30 分钟检查一次：*/30 * * * *

### 通知示例

```
📦 仓库：lxpkwwz/ql_scripts
🔁 Commit：a1b2c3d
👤 作者：lxpkwwz
🕐 时间：2026-06-05 10:25:33 (北京时间)
📝 信息：修复通知模块导入问题
🔗 详情：https://github.com/.../commit/a1b2c3d
📌 通用注意事项
```

---

## 备注

* 环境变量：需要配置环境变量的脚本，已在脚本开头注释说明。
* 定时规则：部分脚本自带默认 Cron，可按需修改。
* 日志查看：青龙面板运行日志中可查看脚本详细输出。
* 脚本更新：通过订阅拉取会自动更新，建议定期 git pull 或重新订阅。

## 🤝 贡献与反馈
如果你在使用中遇到问题，或有新的脚本需求，欢迎提交 Issue 或直接联系作者。

如果你喜欢这个项目，请点亮 ⭐ Star 支持一下～

## 📄 许可证
MIT License

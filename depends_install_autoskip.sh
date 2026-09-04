#!/bin/bash

# new Env:('安装依赖（跳过已安装）');
# cron: @boot
echo "===== 开始安装常用依赖（跳过已安装） ====="

# ---------- Node.js 依赖 ----------
echo "检查 Node.js 依赖..."
# 定义需要安装的 Node.js 全局包列表
node_packages=(
crypto-js
prettytable
dotenv
jsdom
date-fns
tough-cookie
tslib
ws
ts-md5
jieba
form-data
json5
global-agent
png-js
@types/node
typescript
js-base64
axios
moment
request
qs
sharp
jsencrypt
node-rsa
xmldom
socks-proxy-agent
crc
undici
got
ts-node
node-telegram-bot-api
)

for pkg in "${node_packages[@]}"; do
    # 检查包是否已全局安装
    if npm list -g "$pkg" --depth=0 > /dev/null 2>&1; then
        echo "  ✓ $pkg 已安装，跳过"
    else
        echo "  → 安装 $pkg ..."
        npm install -g "$pkg"
    fi
done



# ---------- Python 依赖 ----------
echo "检查 Python3 依赖..."
# 定义需要安装的 Python 包列表
py_packages=(
requests
canvas
ping3
jieba
PyExecJS
aiohttp
redis
httpx
bs4
openai
dashscope
tenacity
loguru
onepush
qrcode
jsonpath_ng
requests_toolbelt
rsa
beautifulsoup4
openpyxl
xlsxwriter
pandas
lxml
fake-useragent
pycryptodome
curl_cffi
cffi
tqdm
PyYAML
Pillow
pyquery
pyaes
borax
pytz
)

# Python 安装时指定镜像源并增加错误重试
for pkg in "${py_packages[@]}"; do
    if pip3 show "$pkg" > /dev/null 2>&1; then
        echo "  ✓ $pkg 已安装，跳过"
    else
        echo "  → 安装 $pkg ..."
        PIP_ROOT_USER_ACTION=ignore pip3 install -i https://pypi.tuna.tsinghua.edu.cn/simple "$pkg" || echo "  ✗ $pkg 安装失败，请手动重试"
    fi
done

# ---------- 系统依赖（可选）----------
if [ -f /etc/alpine-release ]; then
    echo "检测到 Alpine Linux，检查系统依赖..."
    if ! command -v ffmpeg > /dev/null 2>&1; then
        echo "  → 安装 ffmpeg ..."
        apk add --no-cache ffmpeg
    else
        echo "  ✓ ffmpeg 已安装，跳过"
    fi
else
    echo "非 Alpine 系统，请手动安装系统依赖（如 ffmpeg）"
fi






# ---------- 项目本地依赖安装 ----------
echo "检查项目本地依赖..."
project_dirs=(
    "/ql/data/scripts/shufflewzc_faker2_main"
)
for dir in "${project_dirs[@]}"; do
    if [ -d "$dir" ]; then
        echo "  → 进入目录: $dir"
        cd "$dir" || continue
        if [ -f "package.json" ]; then
            echo "    检测到 package.json，执行 npm install (忽略依赖冲突)..."
            npm install --legacy-peer-deps --registry=https://registry.npmmirror.com
        else
            echo "    未找到 package.json，创建临时 package.json 并安装特定包..."
            npm init -y > /dev/null 2>&1
            npm install http-cookie-agent tough-cookie axios socks-proxy-agent@8 smallfawn@latest crc --legacy-peer-deps --registry=https://registry.npmmirror.com
        fi
        echo "    ✓ $dir 依赖处理完成"
    else
        echo "  ✗ 目录不存在: $dir，跳过"
    fi
done
cd - > /dev/null

echo "===== 依赖安装完成 ====="
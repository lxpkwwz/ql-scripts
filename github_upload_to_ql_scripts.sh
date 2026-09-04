#!/usr/bin/env bash

# 将指定目录的文件同步到 GitHub 仓库 lxpkwwz/ql_scripts。
# 用法：
#   export GITHUB_TOKEN="你的 GitHub Token"
#   ./upload_to_ql_scripts.sh                 # 上传脚本所在目录的内容
#   ./upload_to_ql_scripts.sh /path/to/files  # 增量上传指定目录的内容
#
# 青龙面板通常会在 /ql/data/config/config.sh 或 /ql/config/config.sh
# 中配置 ProxyUrl；也可以通过 QL_CONFIG_FILE 指定 config.sh 的实际路径。

set -Eeuo pipefail

REPO_URL="https://github.com/lxpkwwz/ql_scripts.git"
BRANCH="main"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="/ql/data/scripts/1280"

echo "全新同步版本，仅更新不删除"


# 自动读取青龙面板代理配置。未找到 config.sh 或 ProxyUrl 时不启用代理。
CONFIG_FILE="${QL_CONFIG_FILE:-}"
if [[ -z "$CONFIG_FILE" ]]; then
    for candidate in "/ql/data/config/config.sh" "/ql/config/config.sh"; do
        if [[ -f "$candidate" ]]; then
            CONFIG_FILE="$candidate"
            break
        fi
    done
fi

if [[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]]; then
    # config.sh 是青龙面板自身的配置文件，读取其中的 ProxyUrl。
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

PROXY_URL="${ProxyUrl:-}"
if [[ -n "$PROXY_URL" ]]; then
    export HTTP_PROXY="$PROXY_URL"
    export HTTPS_PROXY="$PROXY_URL"
    export ALL_PROXY="$PROXY_URL"
    export http_proxy="$PROXY_URL"
    export https_proxy="$PROXY_URL"
    export all_proxy="$PROXY_URL"
    printf '已启用代理：%s\n' "$PROXY_URL"
fi

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "错误：请先设置环境变量 GITHUB_TOKEN。" >&2
    echo '示例：export GITHUB_TOKEN="ghp_xxx"' >&2
    exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "错误：目录不存在：$SOURCE_DIR" >&2
    exit 1
fi

SOURCE_DIR="$(cd -- "$SOURCE_DIR" && pwd)"
WORK_DIR="$(mktemp -d)"
ASKPASS_FILE="$WORK_DIR/git-askpass.sh"

cleanup() {
    rm -rf -- "$WORK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 通过临时 GIT_ASKPASS 脚本提供令牌，避免把令牌写入远程 URL。
umask 077
cat > "$ASKPASS_FILE" <<'EOF'
#!/usr/bin/env bash
case "$1" in
    *Username*) printf '%s\n' 'x-access-token' ;;
    *Password*) printf '%s\n' "$GITHUB_TOKEN" ;;
    *) printf '\n' ;;
esac
EOF
chmod 700 "$ASKPASS_FILE"

export GIT_ASKPASS="$ASKPASS_FILE"
export GIT_TERMINAL_PROMPT=0

printf '正在克隆目标仓库……\n'
if [[ -n "$PROXY_URL" ]]; then
    git -c "http.proxy=$PROXY_URL" clone --branch "$BRANCH" --single-branch "$REPO_URL" "$WORK_DIR/repo" >/dev/null
else
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$WORK_DIR/repo" >/dev/null
fi

# 使用 cp 递归逐个复制文件，兼容青龙面板这类没有预装 rsync 的容器。
# 只复制源目录实际存在的文件，不删除目标仓库任何文件。
# 同时跳过源目录的 .git，避免覆盖临时仓库自身的 Git 元数据。
# 记录每一个实际同步的文件，后续只暂存这些文件路径。
SYNC_PATHS=()
while IFS= read -r -d '' source_item; do
    relative_path="${source_item#"$SOURCE_DIR"/}"
    [[ "$relative_path" == ".git" || "$relative_path" == .git/* ]] && continue

    destination="$WORK_DIR/repo/$relative_path"
    mkdir -p -- "$(dirname -- "$destination")"
    cp -a -- "$source_item" "$destination"
    SYNC_PATHS+=("$relative_path")
done < <(find "$SOURCE_DIR" \( -type f -o -type l \) -print0)

cd "$WORK_DIR/repo"

# 青龙容器中可能出现临时目录所有权与当前用户不一致，
# 通过环境配置仅信任本次临时仓库，不修改容器的全局 Git 配置。
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="safe.directory"
export GIT_CONFIG_VALUE_0="$WORK_DIR/repo"

# 只暂存源目录实际复制的文件，不对整个仓库或目录执行 git add。
# 因此源目录没有的仓库文件不会进入暂存区，也不会被删除。
for sync_path in "${SYNC_PATHS[@]}"; do
    git add -- "$sync_path"
done

if git diff --cached --quiet; then
    echo "没有检测到文件更新，无需上传。"
    trap - EXIT

    # 兼容青龙 task 包装器：被 source 引入时返回；直接执行时退出。
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
        return 0
    else
        exit 0
    fi
fi

COMMIT_MESSAGE="同步文件更新 $(date '+%Y-%m-%d %H:%M:%S %z')"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
# 使用 --only 限定提交范围，只提交源目录实际同步的文件。
git commit --only -m "$COMMIT_MESSAGE" -- "${SYNC_PATHS[@]}" >/dev/null

printf '正在推送更新……\n'
if [[ -n "$PROXY_URL" ]]; then
    git -c "http.proxy=$PROXY_URL" push origin "$BRANCH" >/dev/null
else
    git push origin "$BRANCH" >/dev/null
fi
printf '上传完成：%s\n' "$REPO_URL"

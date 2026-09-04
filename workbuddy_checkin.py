#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
WorkBuddy 每日积分自动签到 —— 青龙面板版 (纯标准库, 无第三方依赖, 支持多账号)
================================================================================
部署到青龙面板的步骤:
  1) 把本文件上传到青龙的 scripts 目录
    2) 环境变量:WORKBUDDY（二选一）:
     A. 直接粘贴完整的 workbuddy-desktop.info JSON 内容（推荐单账号）:
        {"account":{"uid":"u_123456",...},"auth":{"accessToken":"eyJ...",...}}
     B. 原有多账号格式（每行一条）:
        ACCESS_TOKEN#UID#备注
        eyJxxx.aaa.bbb#u_123456#主号
        eyJyyy.ccc.ddd#u_654321#小号A
     workbuddy-desktop.info 位于 Windows 本机的:
      %LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info
     脚本仅从 JSON 的 auth.accessToken 和 account.uid 读取签到所需字段。

  3) 在"定时任务"里新建, 命令填本脚本路径, 定时规则例如: 30 9 * * *


说明:
  - accessToken 是 JWT, 约 60 天有效; 过期后对应账号会报 401, 重新粘贴最新值到
    WORKBUDDY 对应行即可。
  - 签到接口是幂等的(重复跑不重复发), 多账号挂上去不用担心。
"""

import json
import os
import sys
import base64
import datetime
import logging
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# 青龙环境变量名(在面板"环境变量"里设置)
ENV_MULTI = "WORKBUDDY"                 # 多账号: 每行 ACCESS_TOKEN#UID#备注
ENV_TOKEN = "WORKBUDDY_ACCESS_TOKEN"    # 旧单账号兜底
ENV_UID = "WORKBUDDY_UID"               # 旧单账号兜底


# ---------- 日志: 输出到 stdout(青龙会捕获) ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("wb-checkin")


def token_file_candidates():
    env = os.environ
    return [c for c in [
        os.path.join(env.get("LOCALAPPDATA", ""), "CodeBuddyExtension", "Data", "Public", "auth", "workbuddy-desktop.info"),
        os.path.join(env.get("APPDATA", ""), "CodeBuddyExtension", "Data", "Public", "auth", "workbuddy-desktop.info"),
        os.path.expanduser("~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info"),
        os.path.expanduser("~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info"),
    ] if c]


ENDPOINT_CHECKIN = "https://copilot.tencent.com/v2/billing/meter/daily-checkin"
ENDPOINT_RESOURCE = "https://copilot.tencent.com/v2/billing/meter/get-user-resource"
RESOURCE_BODY = {"PageNumber": 1, "PageSize": 100, "ProductCode": "p_tcaca", "Status": [0, 3], "OnlyValidPeriod": True}


def parse_account_line(line):
    """解析单行: ACCESS_TOKEN#UID#备注 -> dict。备注可省略, 可含 '#'。"""
    line = (line or "").strip()
    if not line:
        return None
    parts = line.split("#")
    token = parts[0].strip()
    uid = parts[1].strip() if len(parts) > 1 else ""
    remark = "#".join(parts[2:]).strip() if len(parts) > 2 else ""
    if not token or not uid:
        return None
    return {"token": token, "uid": uid, "remark": remark or "(未备注)"}
def parse_desktop_info(raw):
    """解析直接粘贴到 WORKBUDDY 的完整 workbuddy-desktop.info JSON。"""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        log.warning("环境变量 %s 中的 JSON 无法解析: %s", ENV_MULTI, e)
        return None
    if not isinstance(data, dict):
        log.warning("环境变量 %s 中的 JSON 根节点必须是对象", ENV_MULTI)
        return None
    auth = data.get("auth") or {}
    account = data.get("account") or {}
    if not isinstance(auth, dict) or not isinstance(account, dict):
        log.warning("环境变量 %s 中缺少 auth 或 account 对象", ENV_MULTI)
        return None
    token = str(auth.get("accessToken") or "").strip()
    uid = str(account.get("uid") or "").strip()
    if not token or not uid:
        log.warning("环境变量 %s 的 JSON 中未找到 auth.accessToken 或 account.uid", ENV_MULTI)
        return None
    remark = str(account.get("nickname") or account.get("uin") or "(desktop.info)").strip()
    return {"token": token, "uid": uid, "remark": remark, "src": "<env:%s JSON>" % ENV_MULTI}
def load_accounts():
    """优先级: WORKBUDDY 完整 JSON/多账号 > 旧单账号环境变量 > 本机文件。"""
    raw = (os.environ.get(ENV_MULTI) or "").strip()
    if raw.startswith("{"):
        account = parse_desktop_info(raw)
        if account:
            return [account]
        # JSON 格式有误时继续检查旧单账号变量，避免完全失去兜底配置。
    accounts = []
    if raw and not raw.startswith("{"):
        for line in raw.splitlines():
            acc = parse_account_line(line)
            if acc:
                acc["src"] = "<env:%s>" % ENV_MULTI
                accounts.append(acc)
    if accounts:
        return accounts


    # 兜底 1: 旧单账号环境变量
    token = (os.environ.get(ENV_TOKEN) or "").strip()
    uid = (os.environ.get(ENV_UID) or "").strip()
    if token and uid:
        return [{"token": token, "uid": uid, "remark": "(env单账号)", "src": "<env:%s>" % ENV_TOKEN}]

    # 兜底 2: 本机文件(单账号)
    for p in token_file_candidates():
        if not (p and os.path.isfile(p)):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            auth = data.get("auth", {}) or {}
            t = auth.get("accessToken")
            u = (data.get("account", {}) or {}).get("uid")
            if t and u:
                return [{"token": t, "uid": u, "remark": "(本机文件)", "src": p}]
        except Exception as e:
            log.warning("读取令牌文件失败 %s: %s", p, e)
    return []


def decode_exp(token):
    """从 JWT 解析 exp 字段, 失败返回 None。"""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(part).decode("utf-8", "replace"))
        return payload.get("exp")
    except Exception:
        return None


def _prepare_ql_notify_paths():
    """加入常见青龙通知模块路径，兼容不同青龙目录布局。"""
    paths = [os.path.dirname(os.path.abspath(__file__))]
    ql_dir = os.environ.get("QL_DIR")
    if ql_dir:
        paths.append(os.path.join(ql_dir, "scripts"))
    paths.extend(["/ql/scripts", "/ql/data/scripts"])
    for path in paths:
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

def ql_notify(title, content):
    """调用青龙面板已配置的系统通知，不再依赖或回退到 WxPusher。"""
    _prepare_ql_notify_paths()
    errors = []

    # 青龙常见 notify.py：优先使用 send，其次兼容 send_notify。
    try:
        import notify
        for name in ("send", "send_notify"):
            sender = getattr(notify, name, None)
            if callable(sender):
                try:
                    sender(title, content)
                    log.info("[通知] 已通过青龙系统通知 (%s.%s)", name, name)
                    return True
                except Exception as e:
                    errors.append("notify.%s: %s" % (name, e))
    except Exception as e:
        errors.append("notify: %s" % e)

    # 兼容旧版 sendNotify.py 中的类、实例方法或函数形式。
    try:
        import sendNotify
        sender = getattr(sendNotify, "sendNotify", None)
        if callable(sender):
            try:
                sender().send(title, content)
            except (AttributeError, TypeError):
                sender(title, content)
            log.info("[通知] 已通过青龙系统通知 (sendNotify)")
            return True
    except Exception as e:
        errors.append("sendNotify: %s" % e)

    log.warning("[通知] 未找到可用的青龙系统通知模块，请检查青龙通知配置%s",
                "；" + " | ".join(errors[-2:]) if errors else "")
    return False



def post_json(url, token, uid, body_obj=None):
    data = b"{}" if body_obj is None else json.dumps(body_obj).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "X-User-Id": uid,
        "User-Agent": "WorkBuddyCheckin/1.4-ql",
    }
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except URLError as e:
        return 0, "URLError: %s" % e


def parse_result(status, body):
    code = None
    msg = ""
    awarded = None
    streak = None
    try:
        obj = json.loads(body)
        code = obj.get("code")
        msg = obj.get("msg") or obj.get("message") or ""
        data = obj.get("data") or {}
        if isinstance(data, dict):
            if data.get("credit") is not None:
                try:
                    awarded = int(data.get("credit"))
                except Exception:
                    awarded = None
            if data.get("streak_days") is not None:
                try:
                    streak = int(data.get("streak_days"))
                except Exception:
                    streak = None
    except Exception:
        pass

    if status == 200 and code in (0, None):
        extra = (" (连续 %d 天)" % streak) if streak is not None else ""
        return True, False, "签到成功" + extra + ((" | " + msg) if msg else ""), awarded, streak
    if code == 10001 or ("已签到" in body) or ("already" in body.lower()):
        return True, True, "今日已签到(幂等命中)" + ((" | code=%s" % code) if code is not None else ""), 0, streak
    if status == 401:
        return False, False, "令牌失效(401), 请在青龙环境变量 %s 对应行更新令牌" % ENV_MULTI, None, None
    return False, False, "签到失败 status=%s code=%s msg=%s" % (status, code, msg), None, None


def query_balance(token, uid):
    status, body = post_json(ENDPOINT_RESOURCE, token, uid, RESOURCE_BODY)
    if status != 200:
        return None, None
    try:
        obj = json.loads(body)
        accts = (obj.get("data", {}) or {}).get("Response", {}) or {}
        accts = (accts.get("Data", {}) or {}).get("Accounts", []) or []
        total = 0.0
        for a in accts:
            v = a.get("CycleCapacityRemainPrecise")
            if v is None:
                v = a.get("CycleCapacityRemain")
            if v is None:
                v = a.get("CapacityRemainPrecise")
            if v is None:
                v = a.get("CapacityRemain")
            try:
                total += float(v)
            except (TypeError, ValueError):
                pass
        return int(round(total)), obj
    except Exception:
        return None, None


def fmt_credits(v):
    return "—" if v is None else str(v)


def run_account(acc, dry):
    """处理单个账号, 返回汇总字典(含备注与积分信息)。"""
    remark = acc["remark"]
    token = acc["token"]
    uid = acc["uid"]
    src = acc["src"]

    exp = decode_exp(token)
    if exp:
        remain = datetime.datetime.fromtimestamp(exp) - datetime.datetime.now()
        log.info("账号[%s] 已加载登录态(来源 %s, uid=%s, 令牌剩余 ~%s)", remark, src, uid, remain)
    else:
        log.info("账号[%s] 已加载登录态(来源 %s, uid=%s)", remark, src, uid)

    if dry:
        log.info("账号[%s] [dry-run] 跳过实际请求", remark)
        return {"remark": remark, "ok": None, "dry": True,
                "msg": "[dry-run] 未执行", "before": None, "after": None, "gained": None}

    before, _ = query_balance(token, uid)
    if before is None:
        log.warning("账号[%s] 签到前总积分查询失败(接口无响应), 仍继续执行签到", remark)
    else:
        log.info("账号[%s] 签到前总积分: %s", remark, fmt_credits(before))

    status, body = post_json(ENDPOINT_CHECKIN, token, uid)
    ok, already, msg, awarded, streak = parse_result(status, body)
    log.info("账号[%s] 签到接口返回: %s", remark, msg)

    after, _ = query_balance(token, uid)
    if after is None:
        log.warning("账号[%s] 签到后总积分查询失败(接口无响应)", remark)
    else:
        log.info("账号[%s] 签到后总积分: %s", remark, fmt_credits(after))

    if awarded is not None:
        gained = awarded
    elif before is not None and after is not None:
        gained = after - before
    else:
        gained = None

    if ok:
        log.info("账号[%s] ✅ %s", remark, msg)
    else:
        log.error("账号[%s] ❌ %s | 响应: %s", remark, msg, body[:300])

    return {"remark": remark, "ok": ok, "dry": False, "msg": msg,
            "before": before, "after": after, "gained": gained}


def main():
    dry = "--dry-run" in sys.argv
    no_notify = "--no-notify" in sys.argv
    accounts = load_accounts()
    if not accounts:
        log.error("未找到任何登录态: 请在青龙环境变量 %s 粘贴完整 workbuddy-desktop.info JSON，"
                  "或按每行 ACCESS_TOKEN#UID#备注设置；也可使用旧变量 %s/%s。",
                  ENV_MULTI, ENV_TOKEN, ENV_UID)
        return 2

    log.info("共加载 %d 个账号, 开始签到%s", len(accounts), " [dry-run]" if dry else "")
    results = [run_account(acc, dry) for acc in accounts]

    # 汇总
    ok_count = sum(1 for r in results if r.get("ok") is True)
    fail_count = sum(1 for r in results if r.get("ok") is False)
    dry_count = sum(1 for r in results if r.get("dry"))

    date_str = datetime.date.today().strftime("%Y-%m-%d")
    if dry:
        title = "WorkBuddy 签到 [dry-run]"
    elif fail_count == 0:
        title = "WorkBuddy 签到 全部成功 (%d/%d)" % (ok_count, len(results))
    else:
        title = "WorkBuddy 签到 %d成功 %d失败" % (ok_count, fail_count)

    lines = ["📅 %s 每日签到 (共 %d 个账号)" % (date_str, len(results)), "─" * 28]
    for r in results:
        remark = r["remark"]
        lines.append("【%s】" % remark)
        if r.get("dry"):
            lines.append("  结果: %s" % r["msg"])
            continue
        lines.append("  结果: %s" % ("✅ " + r["msg"] if r["ok"] else "❌ " + r["msg"]))
        lines.append("  总积分(签到前→后): %s → %s" % (fmt_credits(r["before"]), fmt_credits(r["after"])))
        gained = r["gained"]
        if gained is not None:
            lines.append("  本次获得: %s" % ("0 (今日已签到/无增量)" if gained == 0 else "+%d" % gained))
        if not r["ok"]:
            lines.append("  状态: 失败, 请检查该账号令牌是否有效")
    content = "\n".join(lines)
    log.info("已生成通知内容(%d 个账号)", len(results))

    if not no_notify:
        ql_notify(title, content)
    else:
        log.info("已指定 --no-notify, 跳过推送")

    # 退出码: 有真实失败则非 0(仅 dry-run 视为成功)
    if dry:
        return 0
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

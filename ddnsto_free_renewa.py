#!/usr/bin/python3
# -- coding: utf-8 --
# new Env: 'ddnsto七天免费续费';
# cron: 0 9 * * 1
# -------------------------------
# 脚本名称：ddnsto 七天免费续费
# 功能：自动为 ddnsto 路由器续费免费套餐，支持多账户多设备
# 通知策略：优先调用青龙面板系统通知（notify.send），失败时回退到 push+
# 使用说明：
#   1. 获取 cookie：
#      - 登录 https://web.ddnsto.com/new-app/
#      - 打开浏览器开发者工具（F12），切换到 Network 标签
#      - 刷新页面，点击任意请求，在 Request Headers 中找到 Cookie 字段
#      - 复制完整的 Cookie 字符串（应包含 csrftoken 和 sessionid）
#   2. 获取设备标识（支持两种格式）：
#      - UID 格式（推荐）：在路由器列表页面查看设备 UID（如 8ac12dfe9738）
#      - ID 格式：在 Network 中查找 /api/user/routers/ 请求返回中的 id 字段（如 817023）
#   3. 环境变量填写规范（青龙面板）：
#      - 变量名：ddnsto
#      - 格式：cookie#device_id
#      - 多设备：cookie#uid1#uid2（同一账号多个设备用 # 分隔）
#      - 多账号：cookie1#uid1&cookie2#uid2（多个账号用 & 分隔）
#      - 示例：
#        单账号单设备：csrftoken=xxx;sessionid=yyy#8ac12dfe9738
#        单账号多设备：csrftoken=xxx;sessionid=yyy#8ac12dfe9738#eea71f9422dc
#        多账号多设备：cookie1#uid1#uid2&cookie2#uid3
#      - 可选：plustoken（push+ 推送 token，仅当青龙通知不可用时作为回退）
# -------------------------------

import requests
import json
import uuid
import datetime
import re
import os
import sys
from datetime import timedelta

# ================== 通知模块 ==================
def send_notification(title, content):
    """
    发送通知，优先级如下：
      1. 青龙面板系统通知（notify.send）  —— 最高优先级
      2. push+ 推送（需要配置 plustoken）  —— 回退方案
      3. 控制台打印                          —— 最终兜底
    """
    # ---------- 1. 优先：青龙面板系统通知 ----------
    try:
        from notify import send
        send(title, content)
        print(f"[通知] 青龙面板通知发送成功：{title}")
        return
    except ImportError:
        # notify 模块不在搜索路径中，尝试补全青龙脚本目录后重试
        _ql_paths = [
            '/ql/data/scripts',
            '/ql/scripts',
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notify.py'),
        ]
        for _p in _ql_paths:
            if os.path.isfile(os.path.join(_p, 'notify.py')) if os.path.isdir(_p) else os.path.isfile(_p):
                sys.path.insert(0, os.path.dirname(_p) if os.path.isdir(_p) else _p)
                break
        try:
            from notify import send
            send(title, content)
            print(f"[通知] 青龙面板通知发送成功（补全路径后）：{title}")
            return
        except Exception:
            pass
    except Exception as e:
        print(f"[通知] 青龙面板通知调用异常：{e}，将尝试回退方案")

    # ---------- 2. 回退：push+ 推送 ----------
    plustoken = os.getenv("plustoken")
    if plustoken:
        headers = {'Content-Type': 'application/json'}
        json_data = {
            "token": plustoken,
            'title': title,
            'content': content.replace('\n', '<br>'),
            "template": "json"
        }
        try:
            resp = requests.post(
                'http://www.pushplus.plus/send',
                json=json_data,
                headers=headers,
                timeout=10
            ).json()
            if resp.get('code') == 200:
                print("[通知] push+ 推送成功（青龙通知不可用，已回退）")
            else:
                print(f"[通知] push+ 推送失败：{resp}")
        except Exception as e:
            print(f"[通知] push+ 推送异常：{e}")

    # ---------- 3. 兜底：控制台打印 ----------
    print(f"[通知] 未发送成功，以下为通知内容：")
    print(f"标题：{title}")
    print(f"内容：{content}")

# ================== 辅助函数 ==================
def UTC2BJS(UTC):
    """UTC时间转北京时间"""
    UTC_format = "%Y-%m-%dT%H:%M:%S.%fZ"
    BJS_format = "%Y-%m-%d %H:%M:%S"
    UTC_dt = datetime.datetime.strptime(UTC, UTC_format)
    BJS_dt = UTC_dt + timedelta(hours=8)
    return BJS_dt.strftime(BJS_format)

def get_router_id_by_uuid(cookie, xcsrftoken, device_uuid):
    """通过设备UUID获取路由器数字ID"""
    url = 'https://web.ddnsto.com/api/user/routers/'
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cookie': cookie,
        'referer': 'https://web.ddnsto.com/app/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
        'x-csrftoken': xcsrftoken
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code >= 400:
            return None, f"获取路由器列表失败 (HTTP {resp.status_code})"

        routers = resp.json()

        # 处理分页格式 {"count": 2, "results": [...]}
        if isinstance(routers, dict) and 'results' in routers:
            router_list = routers.get('results', [])
        elif isinstance(routers, list):
            router_list = routers
        else:
            return None, "路由器列表格式异常"

        for router in router_list:
            if isinstance(router, dict):
                router_uid = router.get('uid', '')
                router_id = router.get('id', '')
                if router_uid == device_uuid:
                    return router_id, None
        return None, f"未找到 UID 为 {device_uuid} 的路由器"
    except Exception as e:
        return None, f"获取路由器列表异常: {e}"

def process_device(cookie, userid):
    """处理单个设备的续费"""
    # 提取 csrftoken
    match = re.findall('csrftoken=(.*?);', cookie, re.S)
    if not match:
        return False, f"❌ cookie中未找到 csrftoken，请检查 cookie 格式（应包含 csrftoken=xxx;）"
    xcsrftoken = match[0]

    # 构建请求头
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cookie': cookie,
        'referer': 'https://web.ddnsto.com/app/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
        'x-csrftoken': xcsrftoken
    }

    # 判断是否为UID格式（非纯数字），自动转换为数字ID
    router_id = userid
    if not userid.isdigit():
        id_result, err = get_router_id_by_uuid(cookie, xcsrftoken, userid)
        if id_result:
            router_id = str(id_result)
        else:
            return False, f"❌ 获取路由器 ID 失败: {err}"

    # 1. 创建订单
    uu_id = uuid.uuid4()
    suu_id = ''.join(str(uu_id).split('-'))
    url_create_order = 'https://web.ddnsto.com/api/user/product/orders/'
    data_order = {
        'product_id': '2',
        'uuid_from_client': suu_id
    }

    try:
        resp2 = requests.post(url_create_order, headers=headers, data=data_order, timeout=15)
        if resp2.status_code >= 400:
            try:
                err_json = resp2.json()
                err_msg = err_json.get('application-error', err_json.get('detail', str(err_json)))
            except:
                err_msg = resp2.text
            return False, f"创建订单失败 (HTTP {resp2.status_code}): {err_msg}"

        result_2 = resp2.json()
    except Exception as e:
        return False, f"创建订单异常: {e}"

    # 处理返回格式
    if isinstance(result_2, list):
        if len(result_2) == 0:
            return False, "订单创建返回空列表，可能本周免费次数已用完或 cookie 失效"
        elif isinstance(result_2[0], dict):
            result_2 = result_2[0]
        else:
            return False, "返回列表格式异常"

    if isinstance(result_2, dict) and 'application-error' in result_2:
        return False, result_2['application-error']

    if not (isinstance(result_2, dict) and 'id' in result_2):
        return False, "订单创建返回数据异常，无法获取 ID"

    order_id = result_2['id']

    # 2. 绑定订单
    url_bind_order = f'https://web.ddnsto.com/api/user/routers/{router_id}/'
    data_bind = {
        "plan_ids_to_add": [str(order_id)],
        "server": 3
    }
    try:
        resp4 = requests.patch(url_bind_order, headers=headers, data=data_bind, timeout=10)
        if resp4.status_code >= 400:
            try:
                err_json = resp4.json()
                err_msg = err_json.get('application-error', err_json.get('detail', str(err_json)))
            except:
                err_msg = resp4.text
            return False, f"绑定订单失败 (HTTP {resp4.status_code}): {err_msg}"

        result_4 = resp4.json()
    except Exception as e:
        return False, f"绑定订单异常: {e}"

    if result_4.get('uid'):
        expire_time = UTC2BJS(result_4['active_plan']["product_expired_at"])
        return True, f"✅ 续费成功\n到期时间：{expire_time}"
    else:
        return False, "绑定成功但未获取到 uid，可能续费失败，请检查路由器状态"

def parse_config(config_str):
    """
    解析配置字符串
    格式：cookie#userid1#userid2&cookie#userid
    返回：[(cookie, [userid1, userid2]), ...]
    """
    accounts = []

    # 按 & 分隔多个账号
    account_strs = config_str.split('&')

    for account_str in account_strs:
        account_str = account_str.strip()
        if not account_str:
            continue

        # 按 # 分隔 cookie 和 userid（第一个是 cookie，后面都是 userid）
        if '#' not in account_str:
            print(f"⚠️ 配置格式错误，缺少 # 分隔符：{account_str[:20]}...")
            continue

        parts = account_str.split('#')
        if len(parts) < 2:
            print(f"⚠️ 配置格式错误：{account_str[:20]}...")
            continue

        cookie = parts[0].strip()
        userids = [uid.strip() for uid in parts[1:] if uid.strip()]

        if not cookie:
            print(f"⚠️ cookie 为空")
            continue

        if not userids:
            print(f"⚠️ 未找到有效的 userid")
            continue

        accounts.append((cookie, userids))

    return accounts

# ================== 解析配置 ==================
ddnsto_config = os.getenv("ddnsto")

if not ddnsto_config:
    msg = "❌ 错误：ddnsto 环境变量未设置\n" \
          "格式说明：\n" \
          "  单账号单设备：cookie#userid\n" \
          "  单账号多设备：cookie#userid1#userid2\n" \
          "  多账号多设备：cookie1#userid1&cookie2#userid2"
    print(msg)
    send_notification("DDNSTO免费续费失败", msg)
    exit(1)

# 解析账号配置
accounts = parse_config(ddnsto_config)

if not accounts:
    msg = "❌ 错误：未解析到有效的账号配置，请检查格式"
    print(msg)
    send_notification("DDNSTO免费续费失败", msg)
    exit(1)

print(f"📋 共解析到 {len(accounts)} 个账号")

# ================== 执行续费并收集结果 ==================
overall_success = True
account_msgs = []

for idx, (cookie, userids) in enumerate(accounts):
    account_msg = f"\n===== 账户 {idx+1}，共 {len(userids)} 个设备 ====="
    account_details = []

    for userid in userids:
        success, msg = process_device(cookie, userid)
        account_details.append(f"👉 设备 {userid}: {msg}")
        if not success:
            overall_success = False

    account_msg += "\n" + "\n".join(account_details)
    account_msgs.append(account_msg)

# 生成最终通知内容
final_content = "\n".join(account_msgs).strip()
if overall_success:
    final_content += "\n\n🎉 所有设备续费完成"
else:
    final_content += "\n\n⚠️ 部分设备续费失败，请根据上述错误信息检查配置"

# 输出到控制台（仅最终汇总）
print(final_content)

# 发送汇总通知（只发一条）
send_notification("DDNSTO免费续费结果", final_content)

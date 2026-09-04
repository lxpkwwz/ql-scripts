# new Env:('小米电池换新价监控-自选机型')
# cron: */30 * * * *

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
严格匹配版小米/红米电池监控脚本：
1. 支持 WATCH_LIST 严格匹配，避免型号混淆
2. 配置区域提供全量 89 款机型标准名称，方便直接复制
3. 价格变动触发青龙通知
"""

import requests
import json
import os
import sys
import time


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
    """优先调用青龙面板系统通知，不使用模拟通知。"""
    _prepare_ql_notify_paths()
    errors = []

    # 青龙常见 notify.py：优先 send，其次兼容 send_notify。
    try:
        import notify
        for name in ("send", "send_notify"):
            sender = getattr(notify, name, None)
            if callable(sender):
                try:
                    sender(title, content)
                    print(f"✅ 已通过青龙系统通知发送：{title}")
                    return True
                except Exception as exc:
                    errors.append(f"notify.{name}: {exc}")
    except Exception as exc:
        errors.append(f"notify: {exc}")

    # 兼容旧版 sendNotify.py 的类、实例方法或函数形式。
    try:
        import sendNotify
        sender = getattr(sendNotify, "sendNotify", None)
        if callable(sender):
            try:
                sender().send(title, content)
            except (AttributeError, TypeError):
                sender(title, content)
            print(f"✅ 已通过青龙系统通知发送：{title}")
            return True
    except Exception as exc:
        errors.append(f"sendNotify: {exc}")

    print("⚠️ 未找到可用的青龙系统通知模块，请检查青龙通知配置。")
    if errors:
        print("通知诊断：" + " | ".join(errors[-2:]))
    return False

# ================= 配置区域 =================

# 1. 关注列表：从下方的【参考列表】中复制完整名称粘贴到这里。
# 只有在这里的机型才会被监控和通知。如果留空 [] 则监控所有机型。
WATCH_LIST = [
    "Xiaomi 14 Pro 电池换新服务",
    "Xiaomi 15 电池换新服务",
    "Redmi K70 电池换新服务"
]

# 2. 参考列表（当前所有可用机型名称，直接复制到上面的 WATCH_LIST 即可）：
# 共 89 款机型，已按字母顺序排列
REFERENCE_MODELS = [
    "REDMI K80 Pro 电池换新服务", "REDMI K80 电池换新服务", "REDMI K80 至尊版 电池换新服务",
    "REDMI Turbo 4 Pro 电池换新服务", "REDMI Turbo 4 电池换新服务", "Redmi K30 5G 电池换新服务",
    "Redmi K30 Pro 电池换新服务", "Redmi K30 电池换新服务", "Redmi K30 至尊纪念版 电池换新服务",
    "Redmi K30S 至尊纪念版 电池换新服务", "Redmi K30i 5G 电池换新服务", "Redmi K40 Pro 电池换新服务",
    "Redmi K40 Pro+ 电池换新服务", "Redmi K40 游戏增强版 电池换新服务", "Redmi K40 电池换新服务",
    "Redmi K40S 电池换新服务", "Redmi K50 Pro 电池换新服务", "Redmi K50 电池换新服务",
    "Redmi K50 电竞版（含冠军版） 电池换新服务", "Redmi K50至尊版 电池换新服务", "Redmi K60 Pro 电池换新服务",
    "Redmi K60 电池换新服务", "Redmi K60E 电池换新服务", "Redmi K60至尊版 电池换新服务",
    "Redmi K70 Pro 电池换新服务", "Redmi K70 电池换新服务", "Redmi K70 至尊版 电池换新服务",
    "Redmi K70E 电池换新服务", "Redmi Note 10 Pro 电池换新服务", "Redmi Note 11 4G 电池换新服务",
    "Redmi Note 11 5G 电池换新服务", "Redmi Note 11 Pro 电池换新服务", "Redmi Note 11 Pro+ 电池换新服务",
    "Redmi Note 11R 电池换新服务", "Redmi Note 11T Pro 电池换新服务", "Redmi Note 11T Pro+ 电池换新服务",
    "Redmi Note 12 Pro 电池换新服务", "Redmi Note 12 Pro+ 电池换新服务", "Redmi Note 12 Pro极速版 电池换新服务",
    "Redmi Note 12 Turbo 电池换新服务", "Redmi Note 12 潮流版 电池换新服务", "Redmi Note 12R 电池换新服务",
    "Redmi Note 12T Pro 电池换新服务", "Redmi Note 13 Pro 电池换新服务", "Redmi Note 13 Pro+ 电池换新服务",
    "Redmi Note 13 电池换新服务", "Redmi Note 13R Pro 电池换新服务", "Redmi Note 13R 电池换新服务",
    "Redmi Note 14 Pro 电池换新服务", "Redmi Note 14 Pro+ 电池换新服务", "Redmi Note 14 电池换新服务",
    "Redmi Note 15R 电池换新服务", "Redmi Note 8 Pro 电池换新服务", "Redmi Note 9 4G 电池换新服务",
    "Redmi Note 9 pro 电池换新服务", "Redmi Note 9 电池换新服务", "Redmi Turbo 3 电池换新服务",
    "Xiaomi  Civi 3 电池换新服务", "Xiaomi 10 Pro 电池换新服务", "Xiaomi 10 电池换新服务",
    "Xiaomi 10 至尊纪念版 电池换新服务", "Xiaomi 10 至尊纪念透明版 电池换新服务", "Xiaomi 10S 电池换新服务",
    "Xiaomi 11 Pro 电池换新服务", "Xiaomi 11 Ultra 电池换新服务", "Xiaomi 11 电池换新服务",
    "Xiaomi 12 Pro 天玑版 电池换新服务", "Xiaomi 12 Pro 电池换新服务", "Xiaomi 12 电池换新服务",
    "Xiaomi 12S Pro 电池换新服务", "Xiaomi 12S Ultra 电池换新服务", "Xiaomi 12S 电池换新服务",
    "Xiaomi 12X 电池换新服务", "Xiaomi 13 Pro 电池升级服务（5361mAh）", "Xiaomi 13 Pro 电池换新服务",
    "Xiaomi 13 Ultra 电池升级服务（5500mAh）", "Xiaomi 13 电池升级服务（4850mAh）", "Xiaomi 13 电池换新服务",
    "Xiaomi 14 Pro 电池换新服务", "Xiaomi 14 电池换新服务", "Xiaomi 15 Pro 电池换新服务",
    "Xiaomi 15 Ultra 电池换新服务", "Xiaomi 15 电池换新服务", "Xiaomi 15S Pro 电池换新服务",
    "Xiaomi Civi 2 电池换新服务", "Xiaomi Civi 4 Pro 电池换新服务", "Xiaomi Civi 5 Pro 电池换新服务",
    "小米9 电池换新服务", "小米9 透明版 电池换新服务"
]

# 3. 监控的系列 ID（无需改动）
PRODUCT_SERIES = {
    "13396": "小米数字系列",
    "1230802569": "Redmi K系列",
    "13389": "Redmi Note系列",
    "1230802571": "其它系列(Civi/Turbo等)",
}
# ===========================================

# 与 ql_github_monitor_script.py 的 github_monitor_stable.json 放在同一配置目录，
# 可在青龙面板“配置文件”中直接查看；也支持用环境变量覆盖路径。
PRICE_FILE = os.getenv("MI_BATTERY_PRICE_FILE", "/ql/data/config/mi_battery_strict_prices.json")

HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'origin': 'https://www.mi.com',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def get_series_data(pid):
    url = f"https://api2.order.mi.com/product/view?product_id={pid}&version=2"
    h = HEADERS.copy()
    h['referer'] = f'https://www.mi.com/shop/buy/detail?product_id={pid}'
    try:
        resp = requests.get(url, headers=h, timeout=10)
        data = resp.json()
        if data.get('code') == 200:
            return data.get('data', {}).get('goods_list', [])
    except: pass
    return None

def main():
    # 青龙配置目录在部分新安装中可能尚未创建。
    os.makedirs(os.path.dirname(PRICE_FILE), exist_ok=True)
    old_prices = {}
    if os.path.exists(PRICE_FILE):
        try:
            with open(PRICE_FILE, 'r', encoding='utf-8') as f:
                saved_prices = json.load(f)
            # 兼容旧格式：{"商品ID": 127.2}；新格式为
            # {"商品ID": {"name": "型号名称", "price": 127.2}}。
            if isinstance(saved_prices, dict):
                for saved_gid, saved_value in saved_prices.items():
                    if isinstance(saved_value, dict):
                        old_prices[str(saved_gid)] = saved_value.get("price")
                    else:
                        old_prices[str(saved_gid)] = saved_value
        except Exception as exc:
            print(f"⚠️ 读取历史价格失败，将按首次运行处理：{exc}")

    new_prices = {}
    notifications = []
    
    print(f"{'状态':<4} | {'机型':<35} | {'当前价格':<8} | {'变动'}")
    print("-" * 65)

    for pid, series_name in PRODUCT_SERIES.items():
        goods_list = get_series_data(pid)
        if not goods_list: continue
            
        for item in goods_list:
            info = item.get('goods_info', {})
            name = info.get('name', '')
            gid = str(info.get('goods_id'))
            price = float(info.get('price', 0))
            
            # 严格匹配逻辑
            if WATCH_LIST and name not in WATCH_LIST:
                continue
            
            # 保存型号名称，方便在青龙配置文件中直接识别每个商品 ID。
            new_prices[gid] = {
                "name": name,
                "price": price,
            }
            old_price = old_prices.get(gid)
            
            status_tag = "👀"
            change_msg = ""
            if old_price is not None and old_price != price:
                diff = old_price - price
                status_tag = "🔔"
                change_msg = f"变动: {old_price} -> {price}"
                notifications.append(f"【{name}】价格变动！\n当前: {price}元\n上次: {old_price}元")
            
            print(f"{status_tag:<4} | {name:<35} | {price:<8} | {change_msg}")

    with open(PRICE_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_prices, f, ensure_ascii=False, indent=4)

    if notifications:
        ql_notify("小米电池价格变动预警", "\n\n".join(notifications))

if __name__ == '__main__':
    main()

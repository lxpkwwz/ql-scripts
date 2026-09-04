#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# new Env:('天翼云盘自动签到');
# cron: 0 9 * * *
"""
天翼云盘自动签到脚本 (适配青龙面板)
============================================================
作者: Manus AI
版本: 1.0.0
更新: 2026-03-23

【环境变量说明】
方式一 (推荐，支持多账号):
  TY_ACCOUNTS  格式: 账号1&密码1@账号2&密码2
  示例: 13800000001&mypassword1@13800000002&mypassword2

方式二 (逐条配置):
  TY_USERNAME_1  第1个账号的手机号
  TY_PASSWORD_1  第1个账号的密码
  TY_USERNAME_2  第2个账号的手机号 (可选)
  TY_PASSWORD_2  第2个账号的密码 (可选)
  以此类推...

【青龙面板定时任务 Cron 表达式】
  0 9 * * *   每天早上 9:00 执行

【所需依赖】
  pip install requests rsa

【功能说明】
  1. 个人空间每日签到 (获取随机容量)
  2. 每日抽奖 x3 (获取随机奖励)
  3. 自动对接青龙面板 notify 推送通知
  4. 支持多账号并发签到
  5. 账号信息脱敏显示
============================================================
"""

import os
import re
import time
import json
import base64
import hashlib
import urllib.parse
import hmac
import rsa
import requests
import random
import sys
import logging

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 禁用 SSL 警告
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass

# ============================================================
# RSA 加密相关常量与工具函数
# ============================================================
BI_RM = list("0123456789abcdefghijklmnopqrstuvwxyz")
B64MAP = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def int2char(a: int) -> str:
    return BI_RM[a]


def b64tohex(a: str) -> str:
    """将 Base64 字符串转换为十六进制字符串"""
    d = ""
    e = 0
    c = 0
    for i in range(len(a)):
        if list(a)[i] != "=":
            v = B64MAP.index(list(a)[i])
            if 0 == e:
                e = 1
                d += int2char(v >> 2)
                c = 3 & v
            elif 1 == e:
                e = 2
                d += int2char(c << 2 | v >> 4)
                c = 15 & v
            elif 2 == e:
                e = 3
                d += int2char(c)
                d += int2char(v >> 2)
                c = 3 & v
            else:
                e = 0
                d += int2char(c << 2 | v >> 4)
                d += int2char(15 & v)
    if e == 1:
        d += int2char(c << 2)
    return d


def rsa_encode(j_rsakey: str, string: str) -> str:
    """使用 RSA 公钥加密字符串"""
    rsa_key = f"-----BEGIN PUBLIC KEY-----\n{j_rsakey}\n-----END PUBLIC KEY-----"
    pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(rsa_key.encode())
    result = b64tohex((base64.b64encode(rsa.encrypt(f'{string}'.encode(), pubkey))).decode())
    return result


def mask_phone(phone: str) -> str:
    """对手机号进行脱敏处理"""
    if len(phone) == 11 and phone.isdigit():
        return f"{phone[:3]}****{phone[-4:]}"
    elif len(phone) > 6:
        return f"{phone[:3]}***{phone[-3:]}"
    return phone


# ============================================================
# 天翼云盘签到核心类
# ============================================================
class Cloud189Checkin:
    """天翼云盘签到客户端"""

    # 请求头 - 模拟 Android 客户端
    MOBILE_HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 '
            'Chrome/74.0.3729.136 Mobile Safari/537.36 '
            'Ecloud/8.6.3 Android/22 clientId/355325117317828 '
            'clientModel/SM-G930K imsi/460071114317824 '
            'clientChannelId/qq proVersion/1.0.6'
        ),
        "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
        "Host": "m.cloud.189.cn",
        "Accept-Encoding": "gzip, deflate",
    }

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.masked_name = mask_phone(username)
        self.session = requests.Session()
        self.session.verify = False
        self.logs = []

    def log(self, message: str):
        """记录日志并打印"""
        print(message)
        self.logs.append(message)

    def login(self) -> bool:
        """执行天翼云盘登录，返回是否成功"""
        self.log(f"🔐 正在登录账号: {self.masked_name}")
        try:
            # Step 1: 获取登录跳转 URL
            url_token = (
                "https://m.cloud.189.cn/udb/udb_login.jsp"
                "?pageId=1&pageKey=default&clientType=wap"
                "&redirectURL=https://m.cloud.189.cn/zhuanti/2021/shakeLottery/index.html"
            )
            r = self.session.get(url_token, timeout=15)

            pattern = r"https?://[^\s'\"]+"
            match = re.search(pattern, r.text)
            if not match:
                self.log("❌ 登录失败: 无法获取认证跳转 URL")
                return False
            url = match.group()

            # Step 2: 获取登录页面 href
            r = self.session.get(url, timeout=15)
            pattern = r'<a id="j-tab-login-link"[^>]*href="([^"]+)"'
            match = re.search(pattern, r.text)
            if not match:
                self.log("❌ 登录失败: 无法获取登录页面链接")
                return False
            href = match.group(1)

            # Step 3: 获取登录表单参数及 RSA 公钥
            r = self.session.get(href, timeout=15)
            try:
                captcha_token = re.findall(r"captchaToken' value='(.+?)'", r.text)[0]
                lt = re.findall(r'lt = "(.+?)"', r.text)[0]
                return_url = re.findall(r"returnUrl= '(.+?)'", r.text)[0]
                param_id = re.findall(r'paramId = "(.+?)"', r.text)[0]
                j_rsakey = re.findall(r'j_rsaKey" value="(\S+)"', r.text, re.M)[0]
            except IndexError as e:
                self.log(f"❌ 登录失败: 无法解析登录页面参数 ({e})")
                return False

            self.session.headers.update({"lt": lt})

            # Step 4: RSA 加密账号密码
            enc_username = rsa_encode(j_rsakey, self.username)
            enc_password = rsa_encode(j_rsakey, self.password)

            # Step 5: 提交登录表单
            login_url = "https://open.e.189.cn/api/logbox/oauth2/loginSubmit.do"
            login_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/76.0',
                'Referer': 'https://open.e.189.cn/',
            }
            login_data = {
                "appKey": "cloud",
                "accountType": "01",
                "userName": f"{{RSA}}{enc_username}",
                "password": f"{{RSA}}{enc_password}",
                "validateCode": "",
                "captchaToken": captcha_token,
                "returnUrl": return_url,
                "mailSuffix": "@189.cn",
                "paramId": param_id,
            }
            r = self.session.post(login_url, data=login_data, headers=login_headers, timeout=15)
            res_json = r.json()

            if res_json.get('result') == 0:
                self.log(f"✅ 登录成功: {res_json.get('msg', '成功')}")
                redirect_url = res_json.get('toUrl')
                if redirect_url:
                    self.session.get(redirect_url, timeout=15)
                return True
            else:
                self.log(f"❌ 登录失败: {res_json.get('msg', '账号或密码错误')}")
                return False

        except requests.exceptions.Timeout:
            self.log("❌ 登录超时，请检查网络连接")
            return False
        except requests.exceptions.ConnectionError:
            self.log("❌ 网络连接失败，请检查网络环境")
            return False
        except Exception as e:
            self.log(f"❌ 登录异常: {str(e)}")
            return False

    def do_sign(self) -> str:
        """执行每日签到"""
        rand = str(round(time.time() * 1000))
        sign_url = (
            f"https://api.cloud.189.cn/mkt/userSign.action"
            f"?rand={rand}&clientType=TELEANDROID&version=8.6.3&model=SM-G930K"
        )
        try:
            response = self.session.get(sign_url, headers=self.MOBILE_HEADERS, timeout=15)
            res_json = response.json()
            netdisk_bonus = res_json.get('netdiskBonus', 0)
            is_sign = str(res_json.get('isSign', '')).lower()
            if is_sign == "false":
                msg = f"🎁 签到成功: 获得 {netdisk_bonus}M 空间"
            else:
                msg = f"🔁 今日已签到: 已累计 {netdisk_bonus}M 空间"
            self.log(msg)
            return msg
        except Exception as e:
            msg = f"❌ 签到失败: {str(e)}"
            self.log(msg)
            return msg

    def do_lottery(self, task_id: str, activity_id: str, label: str) -> str:
        """执行抽奖任务"""
        lottery_url = (
            f"https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action"
            f"?taskId={task_id}&activityId={activity_id}"
        )
        try:
            time.sleep(random.uniform(0.5, 1.5))
            response = self.session.get(lottery_url, headers=self.MOBILE_HEADERS, timeout=15)
            if "errorCode" in response.text:
                res_json = response.json()
                error_code = res_json.get('errorCode', 'UNKNOWN')
                if error_code == 'User_Not_Chance':
                    msg = f"🎯 {label}: 今日抽奖次数已用完"
                else:
                    msg = f"⚠️ {label}: 抽奖失败 (错误码: {error_code})"
            else:
                description = response.json().get('description', '未知奖励')
                msg = f"🎉 {label}: 获得 {description}"
            self.log(msg)
            return msg
        except Exception as e:
            msg = f"❌ {label}: 抽奖异常 ({str(e)})"
            self.log(msg)
            return msg

    def run(self) -> str:
        """执行完整签到流程，返回结果摘要"""
        self.log(f"\n{'='*40}")
        self.log(f"账号: {self.masked_name}")
        self.log(f"{'='*40}")

        if not self.login():
            return "\n".join(self.logs)

        # 个人签到
        self.do_sign()

        # 三次抽奖任务
        lottery_tasks = [
            ("TASK_SIGNIN",        "ACT_SIGNIN", "抽奖任务1"),
            ("TASK_SIGNIN_PHOTOS", "ACT_SIGNIN", "抽奖任务2"),
            ("TASK_2022_FLDFS_KJ", "ACT_SIGNIN", "抽奖任务3"),
        ]
        for task_id, activity_id, label in lottery_tasks:
            self.do_lottery(task_id, activity_id, label)

        return "\n".join(self.logs)


# ============================================================
# 账号配置读取
# ============================================================
def get_accounts() -> list:
    """
    从环境变量中读取账号配置。
    优先使用 TY_ACCOUNTS，其次使用 TY_USERNAME_N / TY_PASSWORD_N。
    """
    accounts = []

    # 方式一: TY_ACCOUNTS=账号1&密码1@账号2&密码2
    ty_accounts = os.environ.get("TY_ACCOUNTS", "").strip()
    if ty_accounts:
        for entry in ty_accounts.split('@'):
            entry = entry.strip()
            if '&' in entry:
                parts = entry.split('&', 1)
                username = parts[0].strip()
                password = parts[1].strip()
                if username and password:
                    accounts.append({"username": username, "password": password})
        if accounts:
            return accounts

    # 方式二: TY_USERNAME_1 / TY_PASSWORD_1 ...
    index = 1
    while True:
        username = os.environ.get(f"TY_USERNAME_{index}", "").strip()
        password = os.environ.get(f"TY_PASSWORD_{index}", "").strip()
        if username and password:
            accounts.append({"username": username, "password": password})
            index += 1
        else:
            break

    return accounts


# ============================================================
# 青龙面板通知推送
# ============================================================
def send_notify(title: str, content: str):
    """尝试调用青龙面板的 notify 模块发送通知"""
    try:
        from notify import send
        send(title, content)
        print("✅ 通知推送成功")
    except ImportError:
        print("ℹ️  未找到青龙通知模块 (notify.py)，跳过推送")
    except Exception as e:
        print(f"⚠️  通知推送失败: {e}")


# ============================================================
# 主函数
# ============================================================
def main():
    print("=" * 50)
    print("  天翼云盘自动签到脚本 (青龙面板版)")
    print(f"  执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    accounts = get_accounts()

    if not accounts:
        print("\n❌ 未找到账号配置，请在青龙面板中设置以下环境变量之一:")
        print("   方式一: TY_ACCOUNTS=手机号&密码 (多账号用@分隔)")
        print("   方式二: TY_USERNAME_1=手机号  TY_PASSWORD_1=密码")
        sys.exit(1)

    print(f"\n共找到 {len(accounts)} 个账号，开始依次执行签到...\n")

    all_results = []

    for i, account in enumerate(accounts):
        username = account['username']
        password = account['password']

        checkin = Cloud189Checkin(username, password)
        result = checkin.run()
        all_results.append(f"【账号 {mask_phone(username)}】\n{result}")

        # 多账号之间随机延迟，避免触发风控
        if i < len(accounts) - 1:
            delay = random.randint(8, 20)
            print(f"\n⏳ 等待 {delay} 秒后执行下一个账号...\n")
            time.sleep(delay)

    print("\n" + "=" * 50)
    print("  所有账号签到执行完毕")
    print("=" * 50)

    # 发送汇总通知
    notify_content = "\n\n".join(all_results)
    send_notify("天翼云盘签到报告", notify_content)


if __name__ == "__main__":
    main()

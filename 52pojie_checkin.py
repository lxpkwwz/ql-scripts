# -*- coding: utf-8 -*-
"""
cron: 30 8 * * *
new Env('吾爱破解签到');
"""

import os
import requests
import re
import time
from bs4 import BeautifulSoup

# 尝试导入青龙通知
try:
    from notify import send
except ImportError:
    def send(title, content):
        print(f"通知发送失败，未找到 notify.py。标题: {title}\n内容: {content}")

def checkin(cookie):
    # 模拟更完整的浏览器请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Connection': 'keep-alive',
        'Cookie': cookie,
        'Host': 'www.52pojie.cn',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
    }
    
    session = requests.Session()
    session.headers.update(headers)

    try:
        # 1. 访问论坛首页，模拟真实用户行为
        print("DEBUG: 访问论坛首页...")
        res_home = session.get('https://www.52pojie.cn/', timeout=15)
        if 'waf_slider_verify' in res_home.text or '访问验证' in res_home.text or '<title>访问验证</title>' in res_home.text:
            return "失败：触发了安全验证（WAF），请尝试更新 Cookie 或在常用 IP 运行。"
        if '请先登录' in res_home.text:
            return "失败：Cookie 已失效或不完整。"
        time.sleep(1) # 模拟用户停留

        # 2. 检查任务状态，看是否已经签到过
        print("DEBUG: 检查任务状态...")
        # 访问已完成任务页面
        res_done = session.get('https://www.52pojie.cn/home.php?mod=task&item=done', timeout=15)
        if '每日签到' in res_done.text:
            msg = "签到结果：今日已签到（任务已在完成列表中）。"
        else:
            # 3. 如果没签到，尝试执行签到请求
            print("DEBUG: 执行签到请求...")
            task_apply_url = 'https://www.52pojie.cn/home.php?mod=task&do=apply&id=2'
            res_checkin = session.get(task_apply_url, timeout=15)
            
            # 4. 解析签到结果
            if '恭喜您，任务已成功完成' in res_checkin.text or '您已成功领取' in res_checkin.text:
                msg = "签到成功：任务已成功完成。"
            elif '不是进行中的任务' in res_checkin.text or '本期您已参与' in res_checkin.text:
                msg = "签到结果：任务已完成或不在进行中。"
            elif 'waf_slider_verify' in res_checkin.text or '访问验证' in res_checkin.text or '<title>访问验证</title>' in res_checkin.text:
                # 如果签到接口被拦截，但之前检查过没签到，说明确实被拦截了
                msg = "失败：签到接口触发了安全验证（WAF），请手动签到一次或更换 IP。"
            else:
                # 最后的兜底检查：再次查看已完成列表
                res_final = session.get('https://www.52pojie.cn/home.php?mod=task&item=done', timeout=15)
                if '每日签到' in res_final.text:
                    msg = "签到成功：通过任务列表确认已完成。"
                else:
                    print(f"DEBUG: 未知状态，响应内容片段：{res_checkin.text[:500]}")
                    msg = "未知状态，请检查日志或更新脚本。"
        
        # 5. 获取积分信息
        print("DEBUG: 获取积分信息...")
        user_info_res = session.get('https://www.52pojie.cn/home.php?mod=spacecp&ac=credit&showall=1', timeout=15)
        credit_match = re.search(r'吾爱币: </em>(\d+)', user_info_res.text)
        credit_info = f" | 吾爱币: {credit_match.group(1)}" if credit_match else ""
        
        return f"成功：{msg}{credit_info}"

    except requests.exceptions.Timeout:
        return "失败：请求超时，请检查网络连接或增加超时时间。"
    except requests.exceptions.RequestException as e:
        return f"失败：网络请求错误 - {str(e)}"
    except Exception as e:
        return f"失败：运行出错 - {str(e)}"

def main():
    # 从环境变量获取 Cookie，支持多账号（换行或 @ 分隔）
    cookies = os.getenv('POJIE_COOKIE')
    if not cookies:
        print("未找到环境变量 POJIE_COOKIE，请在青龙面板中添加。")
        return

    cookie_list = cookies.replace('@', '\n').split('\n')
    summary = []
    
    print(f"检测到 {len(cookie_list)} 个账号，开始执行...")
    
    for i, ck in enumerate(cookie_list):
        ck = ck.strip()
        if not ck:
            continue
        
        print(f"--- 账号 {i+1} 开始签到 ---")
        result = checkin(ck)
        print(f"账号 {i+1} 结果: {result}")
        summary.append(f"账号 {i+1}: {result}")
        # 避免请求过快
        time.sleep(2)

    # 发送通知
    if summary:
        content = "\n".join(summary)
        send("吾爱破解签到通知", content)

if __name__ == "__main__":
    main()

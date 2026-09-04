"""
批量查询番号磁力链接
环境变量（在青龙面板中设置）：
  JAV_CODES: 要查询的番号，英文逗号分隔，例如 SSIS-001,ABC-123
  JAV_PROXY: 代理地址，选填，例如 http://192.168.1.100:7890
  JAV_AUTH:   JavBus 的 bus_auth cookie（如果用 JavBus 且搜索失败才需要）
目标站（可选）：
  默认使用 JavDb（方便），如需切换请修改 get_info() 函数
"""
import os
import time
import json
from datetime import datetime

# 尝试导入 jvav，如果失败请检查依赖是否安装成功
try:
    from jvav import JavDbUtil, JavBusUtil
except ImportError:
    print("错误：请先在青龙面板依赖管理 -> Python3 中安装 jvav")

# ========== 配置区域 ==========
# 从青龙环境变量获取番号（用英文逗号分隔）
CODES = os.getenv("JAV_CODES", "").strip()
# 代理地址（如果需要）
PROXY = os.getenv("JAV_PROXY", "").strip()
# JavBus 认证码（如果用 JavBus 才需要）
AUTH = os.getenv("JAV_AUTH", "").strip()
# 查询间隔（秒），避免请求过快被封
DELAY = 1.5
# 结果保存路径（青龙默认数据目录）
OUTPUT_FILE = "/ql/data/jav_magnets_result.txt"
# ==============================

def get_info_by_code(code):
    """
    使用 JavDb 查询番号信息，返回包含磁力的字典。
    如需用 JavBus，请取消下面一行的注释并注释掉 JavDb 相关行。
    """
    # 使用 JavDb（无需 cookie，但要代理）
    if PROXY:
        util = JavDbUtil(proxy_addr=PROXY)
    else:
        util = JavDbUtil()
    try:
        return util.get_info_by_id(code)
    except Exception as e:
        return {"error": str(e)}

    # 如果要用 JavBus：
    # kwargs = {"proxy_addr": PROXY} if PROXY else {}
    # if AUTH:
    #     kwargs["bus_auth"] = AUTH
    # util = JavBusUtil(**kwargs)
    # try:
    #     return util.get_info_by_id(code)
    # except Exception as e:
    #     return {"error": str(e)}

def main():
    if not CODES:
        print("未设置 JAV_CODES 环境变量，请在青龙面板中添加该变量（番号用英文逗号分隔）。")
        return

    codes = [c.strip() for c in CODES.split(",") if c.strip()]
    print(f"即将查询 {len(codes)} 个番号：{codes}")

    results = []
    for idx, code in enumerate(codes, 1):
        print(f"[{idx}/{len(codes)}] 正在查询 {code} ...")
        data = get_info_by_code(code)
        # 提取磁力链接
        magnets = data.get("magnets", [])
        magnet_links = []
        for m in magnets:
            link = m.get("link", "")
            if link:
                magnet_links.append(link)
        result = {
            "code": code,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "magnet_count": len(magnet_links),
            "magnets": magnet_links,
        }
        if "error" in data:
            result["error"] = data["error"]
        results.append(result)
        print(f"   找到 {len(magnet_links)} 条磁力")
        time.sleep(DELAY)  # 休息一会儿

    # 写入文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            line = json.dumps(r, ensure_ascii=False)
            f.write(line + "\n")
    print(f"\n查询完成，结果已保存到 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
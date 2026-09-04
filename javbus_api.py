"""
青龙面板脚本：JAV 番号磁力链接抓取与优选
===========================================
功能：
  1. 根据输入文件中的番号，通过本地 API 获取所有磁力链接。
  2. 缓存到 CSV 文件，避免重复请求。
  3. 可选“优选模式”（环境变量 ENABLE_OPTIMIZE=true）：
     - 优先选择中文字幕
     - 过滤广告水印
     - 选择体积最接近 TARGET 的磁力
     - 输出 Excel 结果
  4. 支持失败计数，避免反复重试失效番号。
  5. 自动发送青龙通知（若 notify 可用）。

优化说明（2024版）：
  - 过滤顺序：先中文字幕 > 再广告过滤 > 最后大小优选。
  - 体积目标调整为 2.5GB，下限 1.1GB，更适合手机观看。
  - 日志输出与过滤顺序保持一致。
"""

import requests, time, re, os, sys, csv, json

# ==================== 1. 目录结构 ====================
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]  # 如 jav_magnet
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(BASE_DIR, SCRIPT_NAME)

INPUT_DIR  = os.path.join(SCRIPT_DIR, "input")   # 存放含番号的 txt 文件
CACHE_DIR  = os.path.join(SCRIPT_DIR, "cache")   # 存放缓存和失败计数
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")  # 存放 Excel 结果（优选模式）

for d in [INPUT_DIR, CACHE_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# ==================== 2. 运行模式 ====================
OPTIMIZE_ENABLED = os.environ.get("ENABLE_OPTIMIZE", "false").strip().lower() == "true"

# ==================== 3. 基本配置 ====================
BASE_URL      = "http://localhost:8922/api"
HEADERS       = {"User-Agent": "Mozilla/5.0"}

# 缓存文件路径（名称已改为 javbus 前缀，便于区分来源）
CACHE_FILE    = os.path.join(CACHE_DIR, "javbus_raw_magnets_cache.csv")
FAIL_COUNT_FILE = os.path.join(CACHE_DIR, "failed_counts.json")

# 重试配置
MAX_RETRIES   = 5
RETRY_DELAY   = 1

# 体积筛选参数（单位：字节）
SIZE_MIN = int(1.1 * 1024**3)   # 1.1 GB（已从 0.8GB 上调，更符合手机观影标准）
SIZE_MAX = int(5.2 * 1024**3)   # 5.2 GB
TARGET   = int(2.5 * 1024**3)   # 2.5 GB（最佳体积，1080P 高画质的黄金平衡点）

# ==================== 广告过滤关键词（最终优化版） ====================
AD_L1 = [
    # —— 网站 / 论坛水印 ——
    '@sis001', '@sexinsex', '第一會所新片', '第一會所', '第一会所',
    '草榴社區', '草榴社区', 't66y', 'olo', 'runbkk',
    'javset', 'javfile', 'javtorrent', 'japanadultvideos',
    'ikujav', 'dioguitar', 'lameizi', '@18p2p', '@91',
    # —— 发布者签名 / 广告 ID ——
    '店長推薦作品', '最新東京熱', '原版首发', '谢谢分享',
    '1024高清移动视频', '踏雪寻笔', '静候轮回', '牛大力',
    '亂花', '公主殿下', '球尔', 'arsenal', 'chikan',
    '212121', '8400327', '3325', '325998', '1064517',
    # —— 高频水印 / 压制组签名 ——
    'tanw或yk', 'tiankong', 'nikeのｂ', 'ichiban',
    '【猪头爱爱】【sex8】', '【ses', '【qj',
    'hjd2048', 'one2048', 'fbfb', 'xxfhd',
    # —— 破解 / 去码组 / 流出 ——
    '破解', '破解版', '无码流出', 'uncen',
    '漏れ', 'モザイク破壊版', '無修正', '流出', 'leaked',
    '-uncensored', '-leak', 'bvpp',
    # —— 广告 / 低质格式标识 ——
    'cavi',
    # —— 广告域名后缀 ——
    '.cc', '.tv', '.xyz', '.top'
]

AD_L2_HEAVY = [
    '.rmvb', '.wmv', '.avi',    # 老旧视频格式
    '.rar', '.zip',              # 压缩包，多数为广告或无效
    'sd'                         # 标清标签
]

AD_L2_LIGHT = [
    '4k', '2k', '6k',
    '60fps',
    '1080p', 'fhd', 'hd', '720p',
    'x264', 'xvid', 'x1080x'
]

# 惩罚值（字节）
PENALTY_LIGHT = 2 * 1024**3   # 2 GB
PENALTY_HEAVY = 5 * 1024**3   # 5 GB

# CSV 缓存和 Excel 输出的字段顺序
FIELDS = ['番号', '磁力ID', '标题', '大小', '字节数', '日期', 'isHD', 'hasSubtitle', '磁力链接']

# ==================== 4. 依赖处理 ====================
try:
    from notify import send as notify_send
    _HAS_NOTIFY = True
except ImportError:
    _HAS_NOTIFY = False

if OPTIMIZE_ENABLED:
    from openpyxl import Workbook

# ==================== 5. 失败计数管理 ====================
def load_fail():
    if not os.path.exists(FAIL_COUNT_FILE):
        return {}
    try:
        with open(FAIL_COUNT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_fail(d):
    try:
        with open(FAIL_COUNT_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f)
    except Exception as e:
        print(f"[!] 保存失败计数失败: {e}")

# ==================== 6. 缓存读写 ====================
def load_cache():
    if not os.path.exists(CACHE_FILE):
        print(f"[💾] 缓存未找到文件 {CACHE_FILE}，将使用 API 查询")
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if set(reader.fieldnames) != set(FIELDS):
                print("[💾] 缓存列名不匹配，忽略缓存")
                return {}
            cache = {}
            for row in reader:
                mid = row['番号'].strip()
                cache.setdefault(mid, []).append({
                    'id': row.get('磁力ID', ''),
                    'title': row.get('标题', ''),
                    'size': row.get('大小', ''),
                    'numberSize': int(row.get('字节数', 0) or 0),
                    'shareDate': row.get('日期', ''),
                    'isHD': row.get('isHD', 'False').strip().lower() == 'true',
                    'hasSubtitle': row.get('hasSubtitle', 'False').strip().lower() == 'true',
                    'link': row.get('磁力链接', '')
                })
        total_magnets = sum(len(v) for v in cache.values())
        print(f"[💾] 缓存已加载 {len(cache)} 个番号，共 {total_magnets} 条磁力数据")
        return cache
    except Exception as e:
        print(f"[💾] 缓存读取失败: {e}")
        return {}

def append_cache(new_items):
    if not new_items:
        return
    exist = os.path.exists(CACHE_FILE)
    try:
        with open(CACHE_FILE, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if not exist:
                writer.writeheader()
            for mid, items in new_items.items():
                for m in items:
                    writer.writerow({
                        '番号': mid,
                        '磁力ID': m.get('id', ''),
                        '标题': m.get('title', ''),
                        '大小': m.get('size', ''),
                        '字节数': m.get('numberSize', 0),
                        '日期': m.get('shareDate', ''),
                        'isHD': m.get('isHD', False),
                        'hasSubtitle': m.get('hasSubtitle', False),
                        '磁力链接': m.get('link', '')
                    })
        total = sum(len(v) for v in new_items.values())
        print(f"[💾] 缓存已追加 {total} 条新磁力")
    except Exception as e:
        print(f"[💾] 缓存追加失败: {e}")

# ==================== 7. API 调用函数 ====================
def api_detail(mid):
    url = f"{BASE_URL}/movies/{mid}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        gid, uc = data.get("gid"), data.get("uc")
        if not gid or not uc:
            return None, None, ('N/A', 'Missing gid/uc', url)
        return gid, uc, None
    except requests.exceptions.HTTPError as e:
        return None, None, (str(e.response.status_code), e.response.reason or 'Unknown', url)
    except requests.exceptions.Timeout:
        return None, None, ('Timeout', 'Request timed out', url)
    except requests.exceptions.ConnectionError:
        return None, None, ('ConnectionError', 'Connection failed', url)
    except Exception as e:
        return None, None, ('Error', str(e), url)

def api_magnets(mid, gid, uc):
    url = f"{BASE_URL}/magnets/{mid}"
    try:
        r = requests.get(url, headers=HEADERS,
                         params={"gid": gid, "uc": uc, "sortBy": "size", "sortOrder": "asc"},
                         timeout=10)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data, None
        else:
            return [], None
    except Exception as e:
        return None, (str(e), url)

# ==================== 8. 工具函数 ====================
def fmt(raw):
    return [{
        'id': m.get('id', ''),
        'title': m.get('title', ''),
        'size': m.get('size', ''),
        'numberSize': int(m.get('numberSize', 0) or 0),
        'shareDate': m.get('shareDate', ''),
        'isHD': m.get('isHD', False),
        'hasSubtitle': m.get('hasSubtitle', False),
        'link': m.get('link', '')
    } for m in raw]

def select_best(mags):
    """
    优选磁力（新顺序：中文字幕 > 广告过滤 > 大小接近 TARGET）。
    返回: (best_magnet, ad_removed, s_cnt, size_cnt, is_cn)
    """
    if not mags:
        return None, 0, 0, 0, False

    # 1. 中文字幕优先（最高优先级）
    sub_mags = [m for m in mags if m.get('hasSubtitle', False)]
    s_cnt = len(sub_mags)                        # 字幕资源总数
    cand_sub = sub_mags if sub_mags else mags    # 有字幕则锁定，没有则全部候选

    # 2. 广告过滤（基于字幕候选池）
    f1 = [m for m in cand_sub if not any(w in m['title'].lower() for w in AD_L1)]
    ad_removed = len(cand_sub) - len(f1)
    cand = f1 if f1 else cand_sub               # 过滤后为空则回退，保证不丢失资源

    # 3. 大小筛选
    ok = [m for m in cand if SIZE_MIN < m['numberSize'] < SIZE_MAX]
    if ok:
        cand = ok
        sz = len(ok)
    else:
        loose = [m for m in cand if m['numberSize'] > SIZE_MIN]
        cand = loose if loose else cand
        sz = len(loose) if loose else 0

    # 4. 惩罚项（L2 标签增加体积，使其在最终比较中靠后）
    def adj(m):
        raw = m.get('numberSize', 0) or 0
        title = m.get('title', '').lower()
        if any(w in title for w in AD_L2_HEAVY):
            return raw + PENALTY_HEAVY
        if any(w in title for w in AD_L2_LIGHT):
            return raw + PENALTY_LIGHT
        return raw

    # 5. 选最接近 TARGET 的一条
    best = min(cand, key=lambda m: abs(adj(m) - TARGET))
    return best, ad_removed, s_cnt, sz, best.get('hasSubtitle', False)

def notify(title, content):
    if _HAS_NOTIFY:
        try:
            notify_send(title, content)
        except:
            print(f"\n{'='*40}\n{title}\n{content}\n{'='*40}")
    else:
        print(f"\n{'='*40}\n{title}\n{content}\n{'='*40}")

def save_results(success, failed, base_name):
    if not OPTIMIZE_ENABLED:
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "磁力链接"
    ws.append(FIELDS)
    for row in success:
        ws.append(row)

    wf = wb.create_sheet("失败番号")
    wf.append(["番号", "错误代码", "错误原因", "错误链接"])
    for r in failed:
        wf.append([r['movie_id'], r['code'], r['reason'], r['url']])

    output_path = os.path.join(OUTPUT_DIR, f"{base_name}.xlsx")
    wb.save(output_path)
    print(f"[✅] 成功记录已写入 {output_path}")

# ==================== 9. 单文件处理流程 ====================
def process_one_file(input_file, cache, fc):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        print(f"[!] 文件 {os.path.basename(input_file)} 内容为空，跳过")
        return None, None

    task_name = lines[0]
    ids = lines[1:]
    total = len(ids)
    if total == 0:
        print(f"[!] 任务 “{task_name}” 没有番号，跳过")
        return None, None

    safe = re.sub(r'[\\/*?:"<>|]', "_", task_name.strip() or "任务")

    new_fetched = {}
    failed = []
    success = []
    cn_cnt = new_mag = cache_hits = api_cnt = 0
    fc_changed_local = False

    print(f"\n{'='*50}")
    print(f"开始处理任务：{task_name}（共 {total} 个番号）")
    print(f"{'='*50}\n")

    for idx, mid in enumerate(ids, 1):
        print(f"[>] 正在处理第 {idx}/{total} 条: {mid}")

        # ---- 缓存 / API 获取磁力列表 ----
        if mid in cache:
            mags = cache[mid]
            cache_hits += 1
            print(f"[💾] 缓存命中 {mid}，从本地获取 {len(mags)} 条磁力")
        else:
            gid, uc, err = api_detail(mid)
            if not gid:
                alr = fc.get(mid, 0)
                remain = max(0, MAX_RETRIES - 1 - alr)
                if remain > 0:
                    print(f"[⚠️] {mid} 首次获取详情失败: {err[1]}，将重试最多 {remain} 次")
                    for att in range(1, remain + 1):
                        time.sleep(RETRY_DELAY)
                        gid, uc, err = api_detail(mid)
                        if gid:
                            break
                        if att < remain:
                            print(f"[⚠️] {mid} 第 {att}/{remain} 次重试失败: {err[1]}，{RETRY_DELAY}秒后重试...")
                        else:
                            print(f"[❌] {mid} 详情获取失败，已达最大重试次数")
                else:
                    print(f"[❌] {mid} 详情获取失败（历史失败 {alr} 次，不再重试）")

            if not gid:
                if OPTIMIZE_ENABLED:
                    failed.append({
                        'movie_id': mid,
                        'code': err[0] if err else '',
                        'reason': err[1] if err else 'Unknown',
                        'url': err[2] if err else BASE_URL
                    })
                fc[mid] = alr + 1
                fc_changed_local = True
                print(f"[📉] 计数 {mid} 累计失败次数更新为 {fc[mid]}")
                print()
                continue

            raw = None
            for att in range(1, MAX_RETRIES + 1):
                raw, merr = api_magnets(mid, gid, uc)
                if raw is not None:
                    break
                if merr and att < MAX_RETRIES:
                    print(f"[⚠️] {mid} 第 {att}/{MAX_RETRIES} 次获取磁力失败: {merr[0]}，{RETRY_DELAY}秒后重试...")
                    time.sleep(RETRY_DELAY)
                elif att < MAX_RETRIES:
                    print(f"[⚠️] {mid} 第 {att}/{MAX_RETRIES} 次获取磁力无数据，{RETRY_DELAY}秒后重试...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"[❌] {mid} 磁力获取重试 {MAX_RETRIES} 次后仍无数据")
                    if OPTIMIZE_ENABLED:
                        failed.append({
                            'movie_id': mid,
                            'code': merr[0] if merr else 'N/A',
                            'reason': merr[1] if merr else 'No magnets',
                            'url': f"{BASE_URL}/magnets/{mid}"
                        })
                    break
            if raw is None:
                print()
                continue

            mags = fmt(raw)
            if len(mags) == 0:
                print(f"[⚠️] {mid} 未获取到任何磁力，丢弃")
                if OPTIMIZE_ENABLED:
                    failed.append({
                        'movie_id': mid,
                        'code': 'N/A',
                        'reason': 'Empty magnet list',
                        'url': f"{BASE_URL}/magnets/{mid}"
                    })
                print()
                continue

            cache[mid] = mags
            new_fetched[mid] = mags
            new_mag += len(mags)
            api_cnt += 1
            print(f"[🌐] API {mid} 获取到 {len(mags)} 条磁力")

        # ---- 优选逻辑（仅在优化模式） ----
        if OPTIMIZE_ENABLED:
            best, ad_r, s_cnt, size_cnt, is_cn = select_best(mags)
            if best is None:
                print(f"[⚠️] {mid} 优选结果为空，跳过")
                continue
            success.append([
                mid,
                best['id'],
                best['title'],
                best['size'],
                best['numberSize'],
                best['shareDate'],
                best['isHD'],
                best['hasSubtitle'],
                best['link']
            ])
            if is_cn:
                cn_cnt += 1
            gb = best['numberSize'] / (1024**3) if best.get('numberSize') else 0
            icon = "[🀄️] " if is_cn else ""
            # 日志输出顺序与过滤顺序一致：先字幕，再广告，再大小
            print(f"{mid} 中文字幕 {s_cnt} 条，广告过滤 {ad_r} 条，"
                  f"文件大小优选剩余 {size_cnt} 条，"
                  f"记录 1 条(最接近 {TARGET/(1024**3):.1f}GB：{icon}{gb:.2f}GB)")
        print()

    if OPTIMIZE_ENABLED:
        save_results(success, failed, safe)
    if new_fetched:
        append_cache(new_fetched)

    stats = {
        'total': total,
        'success': len(success) if OPTIMIZE_ENABLED else 0,
        'failed': len(failed),
        'new_magnets': new_mag,
        'cache_hits': cache_hits,
        'api_cnt': api_cnt,
        'cn_cnt': cn_cnt,
        'fc_changed': fc_changed_local,
        'new_movies': len(new_fetched)
    }
    return task_name, stats

# ==================== 10. 主流程 ====================
def main():
    candidates = sorted([
        f for f in os.listdir(INPUT_DIR)
        if 'id' in f.lower() and os.path.isfile(os.path.join(INPUT_DIR, f))
    ])
    if not candidates:
        print("[!] 输入目录没有包含 'id' 的文件")
        notify("番号磁力任务失败", "输入目录没有包含 'id' 的文件")
        return

    total_files = len(candidates)
    mode_str = "[⭐] 优选" if OPTIMIZE_ENABLED else "[➕] 缓存补全"
    start_msg = f"本次{mode_str}任务共有 {total_files} 个文件：\n" + \
                "\n".join(f"{i}. {fn}" for i, fn in enumerate(candidates, 1))
    print(f"\n{start_msg}")
    notify(f"番号磁力任务开始 - {mode_str}", start_msg)

    cache = load_cache()
    fc = load_fail()
    any_fc_changed = False

    for idx, fname in enumerate(candidates, 1):
        input_file = os.path.join(INPUT_DIR, fname)
        task_name, stats = process_one_file(input_file, cache, fc)
        if task_name is None:
            continue

        any_fc_changed = any_fc_changed or stats['fc_changed']

        total_movies_now = len(cache)
        total_magnets_now = sum(len(v) for v in cache.values())

        if OPTIMIZE_ENABLED:
            title = f'第 {idx}/{total_files} 个任务：“{task_name}” 完成'
            content = (
                f'“{task_name}” 任务模式：\n'
                f'      [⭐] 优选模式（优先字幕→去广告→选 {TARGET/(1024**3):.1f}GB 附近）。\n'
                f'共搜索番号 {stats["total"]} 个：\n'
                f'      [💾] 数据库命中 {stats["cache_hits"]} 个；\n'
                f'      [🌐] API 查询 {stats["api_cnt"]} 个；\n'
                f'      [✅] 成功 {stats["success"]} 个；\n'
                f'      [🀄️] 中文字幕 {stats["cn_cnt"]} 个；\n'
                f'      [❌] 失败 {stats["failed"]} 个。\n'
                f'数据库变动：\n'
                f'      [➕] 新增番号 {stats["new_movies"]} 个；\n'
                f'      [➕] 新增磁力 {stats["new_magnets"]} 条；\n'
                f'      [💾] 总计番号 {total_movies_now} 个；\n'
                f'      [💾] 总计磁力 {total_magnets_now} 条。'
            )
        else:
            title = f'第 {idx}/{total_files} 个任务：“{task_name}” 完成'
            content = (
                f'“{task_name}” 任务模式：\n'
                f'      [➕] 缓存补全模式。\n'
                f'数据库变动：\n'
                f'      [➕] 新增番号 {stats["new_movies"]} 个；\n'
                f'      [➕] 新增磁力 {stats["new_magnets"]} 条；\n'
                f'      [💾] 总计番号 {total_movies_now} 个；\n'
                f'      [💾] 总计磁力 {total_magnets_now} 条。'
            )

        print(content)
        notify(title, content)

    if any_fc_changed:
        save_fail(fc)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = f"脚本运行异常：{str(e)}"
        print(f"\n[!] {err}")
        notify("番号磁力任务失败", err)
        raise
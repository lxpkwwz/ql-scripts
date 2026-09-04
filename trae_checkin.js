/*
 * Trae Work 每日签到 - 青龙 Node.js 脚本
 *
 * 定时示例：0 8 * * *
 *
 * 推荐环境变量：
 * TRAE_ACCOUNTS = JSON 数组，每个元素格式：
 * [
 *   {
 *     "name": "账号1",
 *     "headers": {
 *       "Cookie": "从实际签到请求复制的 Cookie",
 *       "Authorization": "从实际签到请求复制的 authorization Token",
 *       "User-Agent": "可选",
 *       "Origin": "https://work.trae.cn",
 *       "Referer": "https://work.trae.cn/"
 *     }
 *   }
 * ]
 *
 * 单账号也可以只配置：
 * TRAE_HEADERS = {"Authorization":"...","Cookie":"..."}
 *
 * 如果只拿到了 Cookie，可配置 TRAE_COOKIE。推荐把实际签到请求中的完整
 * authorization 请求头值原样放入 TRAE_AUTHORIZATION，不要手动猜测前缀。
 * TRAE_TOKEN 仅作为兼容旧配置的简化写法。
 *
 * 可选环境变量：
 * TRAE_API_HOST       主 API 主机；默认 https://api.trae.cn
 * TRAE_API_HOSTS      多个候选主机，逗号或换行分隔；用于旧域名自动回退
 * TRAE_STATUS_PATH    默认 /trae/api/v2/ug/checkin_credits/status
 * TRAE_CLAIM_PATH     默认 /trae/api/v2/ug/checkin_credits/claim
 * TRAE_CLAIM_BODY     可选；按实际 claim 请求复制的 JSON 请求体，默认发送 `{}`
 * TRAE_USAGE_PATH     默认 /trae/api/v2/pay/ide_user_ent_usage
 * TRAE_BALANCE        是否查询余额，默认 1；设为 0 关闭
 * TRAE_CREDIT_GROUPS  可选；分类 JSON 数组/对象，自动识别不准时手动标记
 * TRAE_RAW_HEADERS    可选；Reqable 原始请求头文本，私下配置，不要公开
 * TRAE_TIMEOUT        请求超时毫秒数，默认 15000
 * TRAE_AUTHORIZATION  实际请求中的完整 authorization 值，优先级高于 TRAE_HEADERS
 * TRAE_NOTIFY         是否通知，默认 1；设为 0 可关闭
 * TRAE_DEBUG          是否输出接口地址诊断，设为 1；不会输出请求头
 */

'use strict';

const path = require('node:path');
const { spawnSync } = require('node:child_process');
const DEFAULT_API_HOST = 'https://api.trae.cn';
const STATUS_PATH = process.env.TRAE_STATUS_PATH || '/trae/api/v2/ug/checkin_credits/status';
const CLAIM_PATH = process.env.TRAE_CLAIM_PATH || '/trae/api/v2/ug/checkin_credits/claim';
const USAGE_PATH = process.env.TRAE_USAGE_PATH || '/trae/api/v2/pay/ide_user_ent_usage';
const BALANCE_ENABLED = process.env.TRAE_BALANCE !== '0';
const TIMEOUT = Number(process.env.TRAE_TIMEOUT || 15000);
const DEBUG = process.env.TRAE_DEBUG === '1';

function normalizeHost(host) {
  return String(host || '').trim().replace(/\/+$/, '');
}

function buildApiHosts() {
  const configured = process.env.TRAE_API_HOSTS || process.env.TRAE_API_HOST || '';
  const candidates = configured
    .split(/[\n,]+/)
    .map(normalizeHost)
    .filter(Boolean);

  // 兼容旧配置：如果青龙里仍保存 api.trae.com.cn，遇到网关 404 时自动尝试当前中国区主机。
  candidates.push(DEFAULT_API_HOST);
  return [...new Set(candidates)];
}

const API_HOSTS = buildApiHosts();

function parseJsonEnv(name, fallback = undefined) {
  const raw = process.env[name];
  if (!raw || !raw.trim()) return fallback;
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`${name} 不是有效的 JSON：${error.message}`);
  }
}

function buildAccounts() {
  const accounts = parseJsonEnv('TRAE_ACCOUNTS');
  if (accounts !== undefined) {
    if (!Array.isArray(accounts) || accounts.length === 0) {
      throw new Error('TRAE_ACCOUNTS 必须是非空 JSON 数组');
    }
    return accounts.map((account, index) => ({
      name: account.name || `账号${index + 1}`,
      headers: account.headers || {},
    }));
  }

  const headers = parseJsonEnv('TRAE_HEADERS', {});
  if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
    throw new Error('TRAE_HEADERS 必须是 JSON 对象');
  }

  if (process.env.TRAE_COOKIE && !headers.Cookie && !headers.cookie) {
    headers.Cookie = process.env.TRAE_COOKIE;
  }
  Object.assign(headers, parseRawHeadersEnv('TRAE_RAW_HEADERS'));
  if (process.env.TRAE_AUTHORIZATION && process.env.TRAE_AUTHORIZATION.trim()) {
    delete headers.authorization;
    headers.Authorization = process.env.TRAE_AUTHORIZATION.trim();
  }
  if (process.env.TRAE_TOKEN && !headers.Authorization && !headers.authorization) {
    const token = process.env.TRAE_TOKEN.trim();
    headers.Authorization = /^Bearer\s+/i.test(token) ? token : `Bearer ${token}`;
  }

  return [{ name: '账号1', headers }];
}

function normalizeHeaders(headers) {
  const result = {
    Accept: 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    Origin: 'https://work.trae.cn',
    Referer: 'https://work.trae.cn/',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
  };

  for (const [key, value] of Object.entries(headers || {})) {
    if (value !== undefined && value !== null && String(value).trim()) {
      result[key] = String(value);
    }
  }
  return result;
}

class HttpError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'HttpError';
    Object.assign(this, details);
  }
}

function parseRawHeadersEnv(name) {
  const raw = process.env[name];
  if (!raw || !raw.trim()) return {};
  const skip = new Set(['host', 'content-length', 'accept-encoding', 'connection', 'transfer-encoding']);
  const headers = {};
  for (const line of raw.split(/\r?\n/)) {
    const separator = line.indexOf(':');
    if (separator <= 0) continue;
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (!key || !value || skip.has(key.toLowerCase())) continue;
    headers[key] = value;
  }
  return headers;
}

function parseOptionalBody(name) {
  const raw = process.env[name];
  if (!raw || !raw.trim()) return undefined;
  try {
    return JSON.stringify(JSON.parse(raw));
  } catch {
    // 兼容少数非 JSON 请求体；不要在这里猜测或改写用户复制的内容。
    return raw;
  }
}

async function requestJson(url, headers, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      ...(body === undefined ? {} : { body }),
      credentials: 'include',
      signal: controller.signal,
    });

    const contentType = response.headers.get('content-type') || '';
    const text = await response.text();
    let data = {};

    if (text.trim()) {
      try {
        data = JSON.parse(text);
      } catch {
        const preview = text.replace(/\s+/g, ' ').slice(0, 220);
        throw new HttpError(
          `HTTP ${response.status}，响应不是 JSON：${preview}`,
          { status: response.status, url, contentType, body: text },
        );
      }
    }

    if (!response.ok) {
      const message = data?.message || data?.msg || `HTTP ${response.status}`;
      throw new HttpError(`${message}（HTTP ${response.status}）`, {
        status: response.status,
        url,
        contentType,
        body: text,
        data,
      });
    }

    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new HttpError(`请求超时（${TIMEOUT} ms）`, { url, cause: error });
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function unwrap(data) {
  if (data && data.data && typeof data.data === 'object') return data.data;
  return data || {};
}

function getErrorMessage(data) {
  const value = unwrap(data);
  return value.message || value.msg || data?.message || data?.msg || '未知错误';
}

function isHtml404(error) {
  if (!error || Number(error.status) !== 404) return false;
  const type = String(error.contentType || '').toLowerCase();
  const body = String(error.body || '').toLowerCase();
  return type.includes('text/html') || body.includes('<html') || body.includes('<!doctype');
}

async function requestStatus(headers) {
  let lastError;

  for (const host of API_HOSTS) {
    const url = `${host}${STATUS_PATH}`;
    if (DEBUG) console.log(`诊断：尝试状态接口 ${url}`);
    try {
      const data = await requestJson(url, headers);
      return { host, data: unwrap(data) };
    } catch (error) {
      lastError = error;
      // 旧域名通常返回网关 HTML 404；只在这种情况下切换候选主机，避免重复请求领取接口。
      if (!isHtml404(error)) throw error;
      if (DEBUG) console.log(`诊断：${host} 返回 HTML 404，尝试下一个 API 主机`);
    }
  }

  throw lastError || new Error('没有可用的 Trae API 主机');
}

function toFiniteNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function formatCredits(value) {
  const number = toFiniteNumber(value);
  if (number === null) return String(value ?? '未知');
  return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}

function dateFromValue(value) {
  if (value === undefined || value === null || value === '') return null;
  const numeric = toFiniteNumber(value);
  const dateValue = numeric === null ? new Date(value) : new Date(numeric < 1e12 ? numeric * 1000 : numeric);
  return Number.isNaN(dateValue.getTime()) ? null : dateValue;
}

function formatExpiry(value) {
  const dateValue = dateFromValue(value);
  if (!dateValue) return value === undefined || value === null || value === '' ? '' : String(value);
  return dateValue.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
}

function formatExpiryDate(value) {
  const dateValue = dateFromValue(value);
  if (!dateValue) return '';
  return dateValue.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
}

function normalizeCreditGroup(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if (/work\s*专属|专属\s*work/i.test(text)) return 'Work 专属积分';
  if (/通用|general|global/i.test(text)) return '通用积分';
  return '';
}

function extractCreditGroup(pack) {
  const candidates = [];
  const walk = (node, key = '') => {
    if (!node || candidates.length >= 30) return;
    if (typeof node === 'string') {
      if (/(work|专属|通用|general|global)/i.test(node)) candidates.push({ key, value: node });
      return;
    }
    if (Array.isArray(node)) {
      node.forEach((item, index) => walk(item, `${key}[${index}]`));
      return;
    }
    if (typeof node === 'object') {
      for (const [childKey, childValue] of Object.entries(node)) {
        walk(childValue, key ? `${key}.${childKey}` : childKey);
      }
    }
  };
  walk(pack);
  for (const candidate of candidates) {
    const group = normalizeCreditGroup(candidate.value);
    if (group) return group;
  }
  if (DEBUG && candidates.length) {
    console.log(`诊断：权益包存在分类候选但无法规范化：${candidates.map(item => `${item.key}=${item.value}`).join(' | ')}`);
  }
  return '';
}

let creditGroupOverrides;

function loadCreditGroupOverrides() {
  if (creditGroupOverrides !== undefined) return creditGroupOverrides;
  creditGroupOverrides = null;
  const raw = process.env.TRAE_CREDIT_GROUPS || process.env.TRAE_GROUP_MAP || '';
  if (!raw.trim()) return creditGroupOverrides;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) || (parsed && typeof parsed === 'object')) creditGroupOverrides = parsed;
  } catch (error) {
    if (DEBUG) console.log(`诊断：TRAE_CREDIT_GROUPS 不是有效 JSON：${error.message}`);
  }
  return creditGroupOverrides;
}

function manualCreditGroup(pack, index, limit, used) {
  const overrides = loadCreditGroupOverrides();
  if (!overrides) return '';
  const name = String(pack?.display_desc || '').trim();
  const keys = [
    String(index),
    `${name}#${limit ?? ''}#${used ?? ''}`,
    name,
  ];
  const value = Array.isArray(overrides)
    ? overrides[index]
    : keys.map(key => overrides[key]).find(item => item !== undefined);
  return normalizeCreditGroup(value);
}

function fallbackCreditGroup(pack, limit, used) {
  const name = String(pack?.display_desc || '').trim();
  if (/每日签到|签到奖励/.test(name)) return 'Work 专属积分';
  if (/每月登录赠送|免费/.test(name)) return '通用积分';
  // 当前网页示例中，老用户福利的 Work 专属额度存在已用积分，通用额度尚未使用。
  if (/老用户福利/.test(name)) {
    const remaining = limit === null ? null : limit - used;
    if (remaining !== null && used > 0 && remaining < limit) return 'Work 专属积分';
    return '通用积分';
  }
  return '';
}

function isDailyCreditRow(row) {
  return /签到/.test(String(row.name || ''));
}

function compactUsageRows(rows) {
  const compacted = [];
  const dailyGroups = new Map();

  for (const row of rows) {
    const remain = row.limit === null ? null : row.limit - row.used;
    // 网页奖励积分列表只展示有明确正数余额的权益；额度未知的元数据项（如“免费”）不展示。
    if (remain === null || remain <= 0) continue;

    if (!isDailyCreditRow(row)) {
      compacted.push(row);
      continue;
    }

    const key = row.group || '未分类';
    let merged = dailyGroups.get(key);
    if (!merged) {
      merged = { ...row, name: '每日签到', expiries: [] };
      dailyGroups.set(key, merged);
      compacted.push(merged);
    }
    if (row.limit !== null) merged.limit = (merged.limit ?? 0) + row.limit;
    merged.used += row.used;
    if (row.expire !== undefined && row.expire !== null && row.expire !== '') merged.expiries.push(row.expire);
  }
  return compacted;
}

function dailyExpiryText(row) {
  const dates = (row.expiries || [])
    .map(dateFromValue)
    .filter(Boolean)
    .sort((a, b) => a - b);
  if (dates.length === 0) return '';
  const first = formatExpiryDate(dates[0]);
  const last = formatExpiryDate(dates[dates.length - 1]);
  return first === last ? `，到期 ${first}` : `，到期 ${first} 至 ${last}`;
}

async function requestUsage(headers, host) {
  const url = `${host}${USAGE_PATH}`;
  const body = JSON.stringify({ require_usage: true, req_source: 2 });
  if (DEBUG) console.log(`诊断：查询积分 usage ${url}`);
  const data = await requestJson(url, headers, body);
  const result = unwrap(data);
  const code = data?.code ?? result?.code;
  if (code !== undefined && Number(code) !== 0) {
    throw new Error(`${getErrorMessage(data)}（code: ${code}）`);
  }

  const packs = Array.isArray(result.user_entitlement_pack_list)
    ? result.user_entitlement_pack_list
    : [];
  const rows = packs.map((pack) => {
    const base = pack?.entitlement_base_info || {};
    const quota = base?.quota || {};
    const usage = pack?.usage || {};
    const packageExtra = base?.product_extra?.package_extra || {};
    const limit = toFiniteNumber(quota.credits_limit);
    const used = toFiniteNumber(usage.credits_amount) ?? 0;
    return {
      name: pack?.display_desc || '未命名权益包',
      group: manualCreditGroup(pack, packs.indexOf(pack), limit, used)
        || extractCreditGroup(pack)
        || fallbackCreditGroup(pack, limit, used),
      limit,
      used,
      expire: base.end_time,
    };
  });

  const numericRows = rows.filter(row => row.limit !== null);
  const totalLimit = numericRows.reduce((sum, row) => sum + row.limit, 0);
  const totalUsed = numericRows.reduce((sum, row) => sum + row.used, 0);
  return { rows, totalLimit, totalUsed, totalRemain: totalLimit - totalUsed };
}

function formatUsageSummary(name, usage) {
  if (!usage) return '';
  const lines = [];
  const rows = compactUsageRows(usage.rows);
  if (rows.length === 0) {
    lines.push(`${name}：未获取到有明确剩余额度的积分权益包`);
  } else {
    lines.push(`${name}：剩余可用总积分 ${formatCredits(usage.totalRemain)}`);
    for (const row of rows) {
      const remain = row.limit === null ? '未知' : formatCredits(row.limit - row.used);
      const group = row.group ? `（${row.group}）` : '';
      const expiry = row.name === '每日签到' ? dailyExpiryText(row) : (() => {
        const formatted = formatExpiry(row.expire);
        return formatted ? `，到期 ${formatted}` : '';
      })();
      lines.push(`  ${row.name}${group}：剩余 ${remain}${expiry}`);
    }
  }
  return `\n${lines.join('\n')}`;
}

async function getUsageSummary(headers, host, name) {
  if (!BALANCE_ENABLED) return '';
  try {
    const usage = await requestUsage(headers, host);
    return formatUsageSummary(name, usage);
  } catch (error) {
    const message = summarizeNotifyError(error);
    if (DEBUG) console.log(`诊断：积分 usage 查询失败：${message}`);
    return `\n${name}：积分余额查询失败（${message}）`;
  }
}

async function checkOne(account) {
  const name = account.name || '未命名账号';
  const headers = normalizeHeaders(account.headers);

  if (!headers.Cookie && !headers.cookie && !headers.Authorization && !headers.authorization) {
    throw new Error('未配置 Cookie 或 Authorization，请先配置 TRAE_HEADERS / TRAE_AUTHORIZATION / TRAE_COOKIE / TRAE_TOKEN');
  }

  const statusResult = await requestStatus(headers);
  const status = statusResult.data;
  const enabled = status.enable ?? status.enabled ?? status.checkin_enabled;
  const checkedIn = status.checked_in ?? status.checkedIn;

  if (enabled === false) {
    const message = getErrorMessage(status);
    if (Number(status.code) === 1001 || /authenticate|认证|登录|token|token/i.test(message)) {
      throw new Error(`认证失败：${message}；请将实际签到请求中的 authorization 原值配置到 TRAE_AUTHORIZATION，不能只填普通 Cookie`);
    }
    throw new Error(`当前账号不满足签到条件：${message}`);
  }
  if (checkedIn === true) {
    const balance = await getUsageSummary(headers, statusResult.host, name);
    return `${name}：今天已经签到${status.credits ? `，积分 ${status.credits}` : ''}${balance}`;
  }

  const claimUrl = `${statusResult.host}${CLAIM_PATH}`;
  // Reqable 抓到的真实桌面端 claim 请求体为 {}（content-length: 2）。
  const claimBody = parseOptionalBody('TRAE_CLAIM_BODY') ?? '{}';
  if (DEBUG) {
    console.log(`诊断：调用领取接口 ${claimUrl}`);
    console.log(`诊断：领取请求体 ${claimBody === '{}' ? '{}（默认）' : '已设置'}`);
  }
  const claim = await requestJson(claimUrl, headers, claimBody);
  const result = unwrap(claim);
  const code = claim?.code ?? result?.code;
  if (code !== undefined && Number(code) !== 0) {
    const message = getErrorMessage(claim);
    if (Number(code) === 9004) {
      throw new Error(`${message}（code: 9004）；领取接口参数与当前账号/客户端状态不匹配。请复制 claim 请求的完整 authorization、Cookie、请求体，并分别配置 TRAE_AUTHORIZATION、TRAE_COOKIE、TRAE_CLAIM_BODY；不要重复重试`);
    }
    throw new Error(`${message}（code: ${code}）`);
  }

  const credits = result.credits ?? result.credit ?? result.granted_credits;
  const balance = await getUsageSummary(headers, statusResult.host, name);
  return `${name}：签到成功${credits ? `，获得 ${credits} 积分` : ''}${balance}`;
}

function resolveNotifier(moduleValue) {
  if (typeof moduleValue === 'function') return moduleValue;
  if (moduleValue && typeof moduleValue.sendNotify === 'function') return moduleValue.sendNotify.bind(moduleValue);
  if (moduleValue?.default) return resolveNotifier(moduleValue.default);
  return null;
}

function summarizeNotifyError(error, depth = 0) {
  if (!error || depth > 2) return '未知通知错误';
  const message = error.message || String(error);
  if (Array.isArray(error.errors) && error.errors.length) {
    const children = error.errors.map(child => summarizeNotifyError(child, depth + 1)).join(' | ');
    return `${message} [${children}]`;
  }
  return message.replace(/(authorization|cookie|token)\s*[:=]\s*[^\s,;]+/gi, '$1=<redacted>');
}

async function withScriptDirectory(callback) {
  const previousCwd = process.cwd();
  try {
    // 兼容 sendNotify.js 内部使用 ./notify.py、./config 等相对路径的通知脚本。
    process.chdir(__dirname);
    return await callback();
  } finally {
    process.chdir(previousCwd);
  }
}

function pythonNotifyRoots() {
  const qlDir = process.env.QL_DIR || '/ql';
  return [...new Set([
    __dirname,
    path.dirname(__dirname),
    path.join(qlDir, 'data/scripts'),
    path.join(qlDir, 'scripts'),
    ...(process.env.TRAE_PYTHON_PATHS || '').split(/[\n,]+/).filter(Boolean),
  ])];
}

function sendWithQinglongPython(title, content) {
  const pythonBin = process.env.TRAE_PYTHON_BIN || process.env.PYTHON_BIN || 'python3';
  const roots = pythonNotifyRoots();
  const pythonPath = [
    ...roots,
    process.env.PYTHONPATH || '',
  ].filter(Boolean).join(path.delimiter);
  const code = [
    'import sys',
    'from utils.notify import send',
    'send(sys.argv[1], sys.argv[2])',
  ].join('\n');
  const result = spawnSync(pythonBin, ['-c', code, title, content], {
    cwd: __dirname,
    env: { ...process.env, PYTHONPATH: pythonPath },
    encoding: 'utf8',
    timeout: Number(process.env.TRAE_NOTIFY_TIMEOUT || 15000),
    maxBuffer: 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || '').trim().slice(-1200);
    throw new Error(`Python 通知退出码 ${result.status}${detail ? `：${detail}` : ''}`);
  }
}

async function sendNotification(title, content) {
  if (process.env.TRAE_NOTIFY === '0') return;

  const errors = [];
  try {
    sendWithQinglongPython(title, content);
    if (DEBUG) console.log('通知：已调用青龙 Python utils.notify.send');
    return;
  } catch (error) {
    errors.push(`青龙 Python 通知失败：${summarizeNotifyError(error)}`);
  }

  try {
    if (typeof global.$notify === 'function') {
      await Promise.resolve(global.$notify(title, '', content));
      return;
    }
  } catch (error) {
    console.log(`系统通知发送失败：${error.message || error}`);
  }

  const candidates = [
    process.env.QL_SEND_NOTIFY,
    path.join(__dirname, 'sendNotify.js'),
    path.join(process.cwd(), 'sendNotify.js'),
    '/ql/scripts/sendNotify.js',
    '/ql/data/scripts/sendNotify.js',
    '/ql/deps/sendNotify.js',
  ].filter(Boolean);

  const tried = new Set();
  let foundNotifier = false;
  for (const candidate of candidates) {
    const modulePath = path.isAbsolute(candidate) ? candidate : path.resolve(__dirname, candidate);
    if (tried.has(modulePath)) continue;
    tried.add(modulePath);

    try {
      const loaded = await withScriptDirectory(() => require(modulePath));
      const notifier = resolveNotifier(loaded);
      if (notifier) {
        foundNotifier = true;
        try {
          await withScriptDirectory(() => Promise.resolve(notifier(title, content)));
          return;
        } catch (error) {
          errors.push(`${modulePath}: 通知函数调用失败：${summarizeNotifyError(error)}`);
          continue;
        }
      }
      errors.push(`${modulePath}: 未导出 sendNotify 函数`);
    } catch (error) {
      errors.push(`${modulePath}: 模块加载失败：${summarizeNotifyError(error)}`);
    }
  }

  if (DEBUG) {
    console.log(`通知模块诊断（工作目录 ${process.cwd()}，脚本目录 ${__dirname}）：${errors.join(' | ')}`);
  }
  if (foundNotifier) {
    console.log('通知模块已找到，但通知函数调用失败，不影响签到结果。');
  } else {
    console.log('青龙通知模块不可用（未找到可调用的 sendNotify 导出），不影响签到结果。');
  }
}

async function main() {
  const accounts = buildAccounts();
  const results = [];
  let failed = false;

  console.log(`Trae Work 签到开始，共 ${accounts.length} 个账号`);
  if (DEBUG) console.log(`诊断：API 主机候选 ${API_HOSTS.join(' , ')}`);

  for (const account of accounts) {
    try {
      const result = await checkOne(account);
      console.log(result);
      results.push(`成功：${result}`);
    } catch (error) {
      failed = true;
      const name = account.name || '未命名账号';
      const message = `${name}：${error.message || error}`;
      console.log(`失败：${message}`);
      results.push(`失败：${message}`);
    }
  }

  const content = results.join('\n');
  await sendNotification('Trae Work 每日签到', content);
  if (failed) process.exitCode = 1;
}

main().catch(async (error) => {
  console.log(`脚本执行失败：${error.message || error}`);
  await sendNotification('Trae Work 每日签到', `脚本执行失败：${error.message || error}`);
  process.exitCode = 1;
});

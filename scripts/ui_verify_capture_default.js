/**
 * 请款弹窗默认值 + 权限门控 P0 修复 —— 浏览器实测验证
 *
 * 验证两件事（都用真实 UI 登录，不注入 localStorage 绕过）：
 *   A. P0 权限门控修复：/deposits 的「请款」按钮必须可点（修复前永久 disabled）
 *   B. 缺陷 C 请款弹窗默认值：打开弹窗后金额输入框必须回填全额授权额度
 *
 * 用法：node scripts/ui_verify_capture_default.js
 * 前置：后端 127.0.0.1:8000、前端 127.0.0.1:5173 已启动
 */
const fs = require("fs");
const path = require("path");
const playwrightCorePath =
  "C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-3/node_modules/@playwright/cli/node_modules/playwright-core";
const { chromium } = require(playwrightCorePath);

const BASE = "http://127.0.0.1:8000";
const UI = "http://127.0.0.1:5173";
const TENANT = "DEMO2026";
const USER = "admin";
const PASS = "admin123";
const OUTDIR = "F:/PMS/deliverables/ui-verify";

const lines = [];
function log(...args) {
  const line = args.join(" ");
  lines.push(line);
  console.log(line);
}
function flush() {
  fs.writeFileSync(path.join(OUTDIR, "_capture-default.out"), lines.join("\n"), "utf8");
}

async function apiJson(token, url, method = "GET", body) {
  const res = await fetch(`${BASE}/api/v1/tenants/${TENANT}${url}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  if (!res.ok) throw new Error(`${method} ${url} -> ${res.status} ${text.slice(0, 300)}`);
  return data;
}

async function apiLogin() {
  const res = await fetch(`${BASE}/api/v1/tenants/${TENANT}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(`login failed: ${JSON.stringify(data)}`);
  return data;
}

(async () => {
  fs.mkdirSync(OUTDIR, { recursive: true });
  let failures = 0;
  const check = (name, ok, detail) => {
    log(`  [${ok ? "PASS" : "FAIL"}] ${name}${detail ? " — " + detail : ""}`);
    if (!ok) failures++;
  };

  const login = await apiLogin();
  const token = login.token;
  const perms = login.permissions || [];
  log(`API 登录 ok · status=${login.status} · 权限数=${perms.length}`);
  check("后端返回 deposit.manage", perms.includes("deposit.manage"), perms.join(","));

  const hotels = await apiJson(token, `/hotels`);
  const hotelId = Array.isArray(hotels) && hotels.length ? hotels[0].id : 1;
  log(`hotels=${Array.isArray(hotels) ? hotels.length : "?"} · 使用 hotel_id=${hotelId}`);

  // 建一笔 300.00 元的预授权，作为本次验证的目标行
  const amountCents = 30000;
  const pre = await apiJson(token, `/deposits`, "POST", {
    hotel_id: hotelId,
    kind: "PREAUTH",
    method: "UNIONPAY",
    amount: amountCents,
    booking_id: null,
    room_no: null,
    ref_no: null,
    operator: "admin",
    note: "UI 验证：请款弹窗默认值",
  });
  log(`已建预授权 ${pre.deposit_no} · amount_cents=${pre.amount_cents} · status=${pre.status}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on("pageerror", (e) => log("  [PAGEERROR]", e.message));

  try {
    // —— 真实 UI 登录（不注入任何 localStorage）——
    await page.goto(`${UI}/login`);
    await page.waitForSelector('button[type="submit"]', { timeout: 15000 });
    await page.locator('input[name="username"], input[placeholder*="用户名"]').first().fill(USER);
    await page.locator('input[type="password"], input[name="password"]').first().fill(PASS);
    await page.click('button[type="submit"]');
    await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
    log(`UI 登录 ok · url=${page.url()}`);

    // 读回浏览器里真实落盘的权限，确认 P0 修复在运行时生效
    const storedPerms = await page.evaluate(() => {
      try {
        return JSON.parse(localStorage.getItem("pms_permissions") || "[]");
      } catch {
        return [];
      }
    });
    log(`浏览器 localStorage 权限数=${storedPerms.length}`);

    await page.goto(`${UI}/deposits`);
    await page.waitForSelector(".ant-table-tbody > tr.ant-table-row", { timeout: 20000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUTDIR, "y1-押金列表.png") });
    log("已进入 /deposits 且表格有数据");

    // 定位刚建的那笔预授权所在行
    const row = page
      .locator(".ant-table-tbody > tr.ant-table-row")
      .filter({ hasText: pre.deposit_no })
      .first();
    if ((await row.count()) === 0) {
      log(`!! 未找到 ${pre.deposit_no} 的行，改用首行`);
    }
    const target = (await row.count()) ? row : page.locator(".ant-table-tbody > tr.ant-table-row").first();
    const rowText = (await target.textContent()).replace(/\s+/g, " ");
    log(`目标行文本：${rowText.slice(0, 160)}`);

    // 按文字定位按钮（比按序号稳）
    // ⚠️ antd 会给「两个汉字」的按钮自动插入空格（"请款" → "请 款"），
    //    所以必须用正则 /请\s*款/，精确 has-text("请款") 会匹配不到。
    const btn = (label) => {
      const re = new RegExp(label.split("").join("\\s*"));
      return target.locator("button").filter({ hasText: re }).first();
    };

    // —— A. 权限门控 P0 ——
    const capBtn = btn("请款");
    await capBtn.waitFor({ timeout: 5000 });
    check("A1「请款」按钮可见", await capBtn.isVisible());
    const capDisabled = await capBtn.isDisabled();
    check("A2「请款」按钮可点（P0 权限门控修复）", !capDisabled, `disabled=${capDisabled}`);

    // —— B. 请款弹窗默认值（缺陷 C）——
    await capBtn.click();
    const modal = page.locator(".ant-modal-wrap:not(.ant-modal-hidden) .ant-modal").first();
    await modal.waitFor({ state: "visible", timeout: 10000 });
    await page.waitForTimeout(1500);
    await modal.screenshot({ path: path.join(OUTDIR, "y2-请款弹窗默认值.png") });

    const input = modal.locator("input.ant-input-number-input").first();
    await input.waitFor({ timeout: 5000 });
    const shown = (await input.inputValue()).trim();
    const expect = (pre.amount_cents / 100).toFixed(2);
    check(
      "B1 请款弹窗金额默认值 = 全额授权额度",
      shown === expect,
      `实际="${shown}" 期望="${expect}"`
    );

    // 上界：不断言 max 属性（antd InputNumber 不在 DOM 上渲染 max，而是在 JS 里钳制），
    // 改为行为断言——输入超过授权额度的值，失焦后应被钳回额度上限。
    await input.fill("999");
    await input.press("Tab");
    await page.waitForTimeout(600);
    const clamped = (await input.inputValue()).trim();
    check("B2 请款金额上界生效（超额输入被钳回授权额度）", clamped === expect, `实际="${clamped}" 期望="${expect}"`);
    await input.fill(expect);
    await page.waitForTimeout(300);

    // 再验证「冲抵/退款」弹窗默认值（同一处代码路径，避免只修了一个分支）
    await page.keyboard.press("Escape");
    await page.waitForTimeout(800);
    const refBtn = btn("退款");
    if ((await refBtn.count()) && !(await refBtn.isDisabled())) {
      await refBtn.click();
      await modal.waitFor({ state: "visible", timeout: 10000 });
      await page.waitForTimeout(1200);
      const rInput = modal.locator("input.ant-input-number-input").first();
      const rShown = (await rInput.inputValue()).trim();
      const rExpect = (pre.available_cents / 100).toFixed(2);
      check(
        "B3「退款」弹窗金额默认值 = 可用余额（同代码路径未漏修）",
        rShown === rExpect,
        `实际="${rShown}" 期望="${rExpect}"`
      );
      await page.keyboard.press("Escape");
    } else {
      log("  [SKIP] B3 退款按钮不可点（该状态下属预期），跳过");
    }
  } catch (e) {
    failures++;
    log("!! 异常中断：" + e.message);
    try {
      await page.screenshot({ path: path.join(OUTDIR, "y9-异常现场.png") });
    } catch {}
  } finally {
    await browser.close();
    log(`\n结果：${failures === 0 ? "全部通过" : failures + " 项失败"}`);
    flush();
    process.exit(failures === 0 ? 0 : 1);
  }
})();

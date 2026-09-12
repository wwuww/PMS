/**
 * 入住登记页「押金 / 预授权」快捷面板 —— 全量 UI 复测
 *
 * 背景：上一轮 UI 验证时该面板「API 返回 3 条、UI 显示为空」，当时全站权限门控
 * （useCan 大小写不匹配）导致按钮全禁用、疑似连带列表不显示。P0 修复后复测。
 *
 * 断言：
 *   A 组 面板数据渲染：不再显示「暂无记录」，行数与 API 一致
 *   B 组 按钮可用性矩阵（对照 web/src/components/deposit/meta.ts 的 canAct 真值）
 *   C 组 面板内真走一遍：请款（默认全额 → 改部分）→ 状态/金额/按钮联动 → 冲抵
 *
 * 用法：node scripts/ui_verify_quickpanel.js
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
const BOOKING_ID = "354986244532338688";
const OUTDIR = "F:/PMS/deliverables/ui-verify";

const lines = [];
function log(...a) {
  const l = a.join(" ");
  lines.push(l);
  console.log(l);
}
function flush() {
  fs.writeFileSync(path.join(OUTDIR, "_quickpanel.out"), lines.join("\n"), "utf8");
}

async function api(pathname, token, method = "GET", body) {
  const res = await fetch(`${BASE}/api/v1/tenants/${TENANT}${pathname}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const t = await res.text();
  let d;
  try {
    d = JSON.parse(t);
  } catch {
    d = t;
  }
  if (!res.ok) throw new Error(`${method} ${pathname} -> ${res.status} ${t.slice(0, 200)}`);
  return d;
}

(async () => {
  fs.mkdirSync(OUTDIR, { recursive: true });
  let fails = 0;
  const check = (name, ok, detail) => {
    log(`  [${ok ? "PASS" : "FAIL"}] ${name}${detail ? " — " + detail : ""}`);
    if (!ok) fails++;
  };

  const login = await api("/auth/login", null, "POST", {
    username: USER,
    password: PASS,
  });
  const token = login.token;
  const apiDeps = (await api("/deposits?limit=100", token)).filter(
    (d) => String(d.booking_id) === BOOKING_ID && d.status === "AUTHORIZED"
  );
  log(`API：该登记单下有 ${apiDeps.length} 笔 AUTHORIZED 预授权`);

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => log("  [PAGEERROR]", e.message));

  // antd 会给两字按钮插空格（"请款"→"请 款"），按字符逐个加 \s* 构造正则
  const btnOf = (row, label) =>
    row.locator("button").filter({ hasText: new RegExp(label.split("").join("\\s*")) }).first();

  try {
    await page.goto(`${UI}/login`);
    await page.waitForSelector('button[type="submit"]', { timeout: 15000 });
    await page.locator('input[name="username"], input[placeholder*="用户名"]').first().fill(USER);
    await page.locator('input[type="password"], input[name="password"]').first().fill(PASS);
    await page.click('button[type="submit"]');
    await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
    log("UI 登录 ok");

    await page.goto(`${UI}/check-in-register?booking_id=${BOOKING_ID}`);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(OUTDIR, "z1-入住登记页.png"), fullPage: true });

    // —— A 组：面板数据渲染 ——
    const bodyText = (await page.textContent("body")).replace(/\s+/g, " ");
    const emptyShown = bodyText.includes("该登记单暂无押金");
    check("A1 面板不再显示「该登记单暂无押金 / 预授权记录」", !emptyShown);

    const allRows = page.locator(".ant-table-tbody > tr.ant-table-row");
    // 逐行核对 deposit_no，只统计属于本登记单押金面板的行
    let panelRowCount = 0;
    const total = await allRows.count();
    for (let i = 0; i < total; i++) {
      const t = await allRows.nth(i).textContent();
      if (apiDeps.some((d) => t.includes(d.deposit_no))) panelRowCount++;
    }
    check(
      "A2 面板渲染出全部押金行",
      panelRowCount === apiDeps.length,
      `UI 行数=${panelRowCount} / API=${apiDeps.length}`
    );

    if (panelRowCount === 0) {
      log("!! 面板仍无数据，后续断言无法进行。页面片段：" + bodyText.slice(0, 500));
      throw new Error("面板无数据");
    }

    // 取第一笔 AUTHORIZED 预授权所在行
    const targetNo = apiDeps[0].deposit_no;
    const row = page
      .locator(".ant-table-tbody > tr.ant-table-row")
      .filter({ hasText: targetNo })
      .first();
    const rowText0 = (await row.textContent()).replace(/\s+/g, " ");
    log(`目标行 ${targetNo}：${rowText0.slice(0, 140)}`);

    // —— B 组：AUTHORIZED 预授权的按钮可用性矩阵（canAct 真值）——
    const st = async (label) => {
      const b = btnOf(row, label);
      if ((await b.count()) === 0) return "缺失";
      return (await b.isDisabled()) ? "禁用" : "可点";
    };
    const bCapture = await st("请款");
    const bApply = await st("冲抵");
    const bRefund = await st("退款");
    const bRelease = await st("释放");
    const bVoid = await st("作废");
    log(`按钮状态：请款=${bCapture} 冲抵=${bApply} 退款=${bRefund} 释放=${bRelease} 作废=${bVoid}`);
    check("B1 预授权[AUTHORIZED] 请款可点", bCapture === "可点");
    check("B2 预授权[AUTHORIZED] 冲抵禁用（未请款不能冲抵）", bApply === "禁用");
    check("B3 预授权[AUTHORIZED] 释放可点", bRelease === "可点");
    check("B4 预授权 作废禁用（仅实收押金可作废）", bVoid === "禁用");

    // —— C 组：面板内真走一遍请款 ——
    await btnOf(row, "请款").click();
    const modal = page.locator(".ant-modal-wrap:not(.ant-modal-hidden) .ant-modal").first();
    await modal.waitFor({ state: "visible", timeout: 10000 });
    await page.waitForTimeout(1200);
    await modal.screenshot({ path: path.join(OUTDIR, "z2-面板请款弹窗.png") });

    const input = modal.locator("input.ant-input-number-input").first();
    await input.waitFor({ timeout: 5000 });
    const expect = (apiDeps[0].amount_cents / 100).toFixed(2);
    const shown = (await input.inputValue()).trim();
    check("C1 面板请款弹窗默认值 = 全额授权额度", shown === expect, `实际="${shown}" 期望="${expect}"`);

    // 改成 100.00 做部分请款
    await input.fill("100.00");
    await page.waitForTimeout(300);
    await modal.locator("button").filter({ hasText: /确\s*定|提\s*交/ }).first().click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(OUTDIR, "z3-面板请款后.png"), fullPage: true });

    // 复核 API 侧状态
    const after = (await api("/deposits?limit=100", token)).find((d) => d.deposit_no === targetNo);
    log(`API 复核 ${targetNo}：status=${after.status} amount=${after.amount_cents} avail=${after.available_cents}`);
    check("C2 请款落库：状态 = CAPTURED", after.status === "CAPTURED");
    check("C3 请款落库：额度收敛为 10000", after.amount_cents === 10000);

    // 面板行联动
    const rowText1 = (await row.textContent()).replace(/\s+/g, " ");
    check("C4 面板状态标签显示中文「已转实收」（非英文 CAPTURED）", rowText1.includes("已转实收"), rowText1.slice(0, 120));
    check("C5 面板金额更新为 ¥100.00", rowText1.includes("100.00"));

    const st2 = async (label) => {
      const b = btnOf(row, label);
      if ((await b.count()) === 0) return "缺失";
      return (await b.isDisabled()) ? "禁用" : "可点";
    };
    const c2 = await st2("请款");
    const a2 = await st2("冲抵");
    const r2 = await st2("释放");
    log(`请款后按钮：请款=${c2} 冲抵=${a2} 释放=${r2}`);
    check("C6 已请款：请款按钮禁用（不可重复请款）", c2 === "禁用");
    check("C7 已请款：冲抵按钮转为可点（核心链路打通）", a2 === "可点");
    check("C8 已请款：释放按钮禁用（钱已收，只能退款）", r2 === "禁用");

    // 冲抵
    if (a2 === "可点") {
      await btnOf(row, "冲抵").click();
      await modal.waitFor({ state: "visible", timeout: 10000 });
      await page.waitForTimeout(1200);
      const aInput = modal.locator("input.ant-input-number-input").first();
      const aShown = (await aInput.inputValue()).trim();
      check("C9 面板冲抵弹窗默认值 = 可用余额 100.00", aShown === "100.00", `实际="${aShown}"`);
      await modal.locator("button").filter({ hasText: /确\s*定|提\s*交/ }).first().click();
      await page.waitForTimeout(2500);
      await page.screenshot({ path: path.join(OUTDIR, "z4-面板冲抵后.png"), fullPage: true });
      const after2 = (await api("/deposits?limit=100", token)).find((d) => d.deposit_no === targetNo);
      log(`API 复核冲抵后：status=${after2.status} applied=${after2.applied_cents}`);
      check("C10 冲抵落库：applied_cents = 10000", after2.applied_cents === 10000);
      check("C11 冲抵后状态为 APPLIED", after2.status === "APPLIED");
    }
  } catch (e) {
    fails++;
    log("!! 异常中断：" + e.message);
    try {
      await page.screenshot({ path: path.join(OUTDIR, "z9-异常现场.png"), fullPage: true });
    } catch {}
  } finally {
    await browser.close();
    log(`\n结果：${fails === 0 ? "全部通过" : fails + " 项失败"}`);
    flush();
    process.exit(fails === 0 ? 0 : 1);
  }
})();

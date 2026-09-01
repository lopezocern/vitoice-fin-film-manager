/* 临时诊断 v2：展开树 → 点击子目录 → 检查列表请求与结果 */
const path = require('node:path');
const wsRoot = 'C:/Users/Administrator/.workbuddy/binaries/node/workspace/node_modules';
const { chromium } = require(path.join(wsRoot, 'playwright-core'));

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage();
  const listCalls = [];
  page.on('request', (req) => {
    const u = req.url();
    // 只记录列表请求（非 thumbnail/poster 子资源）
    if (/\/api\/media\?/.test(u)) listCalls.push(decodeURIComponent(u.split('8765')[1] || u));
  });

  await page.goto('http://localhost:5173/manage?section=files', { waitUntil: 'load' });
  await page.waitForTimeout(3000);

  // 1. 展开"电视剧"库（点它的展开箭头 ▸）
  const libRow = page.locator('.explorer-tree button', { hasText: '电视剧' }).first();
  // 库行的展开箭头是行内第一个按钮；尝试点行内箭头
  const arrow = libRow.locator('xpath=preceding-sibling::button[1] | xpath=../button[1]');
  const tvText = await libRow.textContent();
  console.log('lib row text:', tvText?.trim());
  // 直接点箭头按钮（含 ▸ 文本且在电视剧行附近）
  const arrows = await page.locator('.explorer-tree button', { hasText: '▸' }).count();
  console.log('arrow buttons:', arrows);
  // 电视剧是第 7 个库，点第 7 个箭头（index 6）
  await page.locator('.explorer-tree button', { hasText: '▸' }).nth(6).click();
  await page.waitForTimeout(2000);

  // 2. 点击"庆余年"子目录
  const sub = page.locator('.explorer-tree button', { hasText: '庆余年' }).first();
  console.log('庆余年 node count:', await sub.count());
  if (await sub.count()) {
    listCalls.length = 0;
    await sub.click();
    await page.waitForTimeout(2500);
    console.log('URL:', decodeURIComponent(page.url()));
    console.log('=== 列表请求 ===');
    console.log(listCalls.join('\n') || '(无列表请求!)');
    const emptyCount = await page.locator('.state.empty').count();
    console.log('empty-state count:', emptyCount);
    // 截图留证
    await page.screenshot({ path: '_diag_subdir.png', fullPage: false });
  } else {
    const treeText = await page.locator('.explorer-tree').textContent();
    console.log('tree after expand:', treeText?.slice(0, 300));
  }

  await browser.close();
})().catch((e) => { console.error('FATAL', e.message); process.exit(1); });

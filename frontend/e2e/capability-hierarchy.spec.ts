import { expect, test, type TestInfo } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

async function saveShot(page: import('@playwright/test').Page, info: TestInfo, filename: string) {
  const outPath = info.outputPath(filename);
  await page.screenshot({ path: outPath, fullPage: true });
  const evidenceDir = process.env.CAPABILITY_EVIDENCE_DIR;
  if (evidenceDir) {
    mkdirSync(evidenceDir, { recursive: true });
    copyFileSync(outPath, join(evidenceDir, filename));
  }
}

test('admin two-tier capability tree management, partner editing, and user insights work end to end without model calls', async ({ page, request }, info) => {
  const origin = String(info.project.use.baseURL).replace(/\/$/, '');
  const api = `${origin}/api`;
  const admin = JSON.parse(readFileSync(`${process.env.BANFEI_TEST_ROOT}/visual-session.json`, 'utf8'));
  const adminHeaders = { Authorization: `Bearer ${admin.access_token}` };

  const pageErrors: string[] = [];
  const modelWrites: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));
  page.on('request', (req) => {
    if (req.method() === 'POST' && /\/(profile|batch-profile|agent\/tasks|development\/plans)(?:[?]|$)/.test(new URL(req.url()).pathname)) {
      modelWrites.push(req.url());
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript((session) => {
    localStorage.setItem('banfei:admin:token', session.access_token);
    localStorage.setItem('banfei:admin:user', JSON.stringify(session.user));
  }, admin);

  // 1. Admin /admin/tags: verify 2 top categories, 25 L1, 88 L2, shared L2 names, custom L2 CRUD & toggle.
  await page.goto('/admin/tags');
  await expect(page.getByRole('heading', { name: '能力标签（顶层分组 / 一级 / 二级）', exact: true })).toBeVisible();
  await expect(page.getByText('产品技术能力（一级 10 项 / 二级 42 项）', { exact: true })).toBeVisible();
  await expect(page.getByText('场景化能力（一级 15 项 / 二级 46 项）', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '展开盘古大模型', exact: true }).click();
  await page.getByRole('button', { name: '展开TZ行业大模型', exact: true }).click();
  for (const sharedName of ['调研与规划设计', '数据工程', '模型预训练/微调', '应用工程', '模型实施与运维']) {
    await expect(page.locator('td', { hasText: `↳ ${sharedName}` })).toHaveCount(2);
  }
  await saveShot(page, info, 'admin-tags-tree.png');

  // Create custom L2 tag under 盘古大模型, verify persistence across reload, then disable and verify tree exclusion.
  const customL2Name = `测试二级能力-${randomUUID().slice(0, 6)}`;
  const panguRow = page.locator('tbody tr').filter({ has: page.locator('span', { hasText: /^盘古大模型$/ }) }).first();
  await panguRow.getByRole('button', { name: '+ 二级', exact: true }).click();
  await page.getByPlaceholder('新增“盘古大模型”二级标签').fill(customL2Name);
  const createResp = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith('/admin/capability-tags'));
  await page.getByRole('button', { name: '保存', exact: true }).click();
  expect((await createResp).status()).toBe(201);

  await page.reload();
  await page.getByRole('button', { name: '展开盘古大模型', exact: true }).click();
  const customRow = page.locator('tbody tr').filter({ hasText: `↳ ${customL2Name}` });
  await expect(customRow).toBeVisible();
  const toggleResp = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/admin/capability-tags/') && r.url().endsWith('/enable'));
  await customRow.getByRole('button', { name: '停用', exact: true }).click();
  expect((await toggleResp).status()).toBe(200);
  await expect(customRow.getByText('停用', { exact: true })).toBeVisible();

  const publicTreeRes = await request.get(`${api}/partners/capability-tree`, { headers: adminHeaders });
  expect(publicTreeRes.status()).toBe(200);
  const publicTree: Array<{ tags: Array<{ name: string; children: Array<{ name: string }> }> }> = await publicTreeRes.json();
  const panguPublic = publicTree.flatMap((c) => c.tags).find((t) => t.name === '盘古大模型');
  expect(panguPublic?.children.some((c) => c.name === customL2Name)).toBe(false);

  // Switch to 顶层分类 subtab and verify both top groups render.
  await page.getByRole('button', { name: '顶层分类', exact: true }).click();
  await expect(page.getByRole('heading', { name: '顶层分类配置', exact: true })).toBeVisible();
  await expect(page.locator('tbody tr').filter({ hasText: '产品技术能力' })).toBeVisible();
  await expect(page.locator('tbody tr').filter({ hasText: '场景化能力' })).toBeVisible();

  // 2. Admin /admin/partners & /admin/partners/[id]: filter groups, partner creation & L1/L2 tree editing.
  await page.goto('/admin/partners');
  const toolbar = page.getByRole('region', { name: '伙伴筛选', exact: true });
  await toolbar.getByRole('button', { name: '能力标签筛选', exact: true }).click();
  const filterPopover = page.getByRole('group', { name: '能力标签选项', exact: true });
  await expect(filterPopover.locator('fieldset > legend', { hasText: /^产品技术能力$/ })).toBeVisible();
  await expect(filterPopover.locator('fieldset > legend', { hasText: /^场景化能力$/ })).toBeVisible();
  await saveShot(page, info, 'admin-partners-filter.png');

  const partnerName = `二层能力验收伙伴-${randomUUID().slice(0, 8)}`;
  const partnerCreateRes = await request.post(`${api}/partners`, {
    headers: adminHeaders,
    data: { name: partnerName },
  });
  expect(partnerCreateRes.status()).toBe(201);
  const partner = await partnerCreateRes.json();

  await page.goto(`/admin/partners/${partner.id}`);
  const treeGroup = page.getByRole('group', { name: '能力标签（一二级多选）', exact: true });
  const panguCard = treeGroup.locator('.capability-l1-card').filter({ has: page.locator('.capability-l1-label > span', { hasText: /^盘古大模型$/ }) });
  const modernCard = treeGroup.locator('.capability-l1-card').filter({ has: page.locator('.capability-l1-label > span', { hasText: /^应用现代化$/ }) });

  await panguCard.locator('.capability-expand-btn').click();
  await modernCard.locator('.capability-expand-btn').click();
  await panguCard.locator('.capability-l2-label', { hasText: /^模型预训练\/微调$/ }).getByRole('checkbox').check();
  await panguCard.locator('.capability-l2-label', { hasText: /^数据工程$/ }).getByRole('checkbox').check();
  await modernCard.locator('.capability-l2-label', { hasText: /^开发现代化$/ }).getByRole('checkbox').check();

  await expect(panguCard.locator('.capability-l1-label').getByRole('checkbox')).toBeChecked();
  await expect(modernCard.locator('.capability-l1-label').getByRole('checkbox')).toBeChecked();
  await expect(treeGroup).toContainText('已选一级 2 项、二级 3 项');

  await page.getByRole('button', { name: '保存伙伴信息', exact: true }).click();
  await expect(page.getByText('伙伴信息已保存。', { exact: true })).toBeVisible();
  await page.reload();

  const reloadedGroup = page.getByRole('group', { name: '能力标签（一二级多选）', exact: true });
  const reloadedPangu = reloadedGroup.locator('.capability-l1-card').filter({ has: page.locator('.capability-l1-label > span', { hasText: /^盘古大模型$/ }) });
  const reloadedModern = reloadedGroup.locator('.capability-l1-card').filter({ has: page.locator('.capability-l1-label > span', { hasText: /^应用现代化$/ }) });
  await expect(reloadedPangu.locator('.capability-l1-label').getByRole('checkbox')).toBeChecked();
  await expect(reloadedModern.locator('.capability-l1-label').getByRole('checkbox')).toBeChecked();
  await expect(reloadedPangu.locator('.capability-l2-label', { hasText: /^模型预训练\/微调$/ }).getByRole('checkbox')).toBeChecked();
  await expect(reloadedPangu.locator('.capability-l2-label', { hasText: /^数据工程$/ }).getByRole('checkbox')).toBeChecked();
  await expect(reloadedModern.locator('.capability-l2-label', { hasText: /^开发现代化$/ }).getByRole('checkbox')).toBeChecked();
  await saveShot(page, info, 'admin-partner-edit-tree.png');

  // Verify unchecking parent L1 clears its L2 selections cleanly, and rechecking L2 restores both.
  await reloadedModern.locator('.capability-l1-label').getByRole('checkbox').uncheck();
  await expect(reloadedGroup).toContainText('已选一级 1 项、二级 2 项');
  await reloadedModern.locator('.capability-expand-btn').click();
  await reloadedModern.locator('.capability-l2-label', { hasText: /^开发现代化$/ }).getByRole('checkbox').check();
  await expect(reloadedModern.locator('.capability-l1-label').getByRole('checkbox')).toBeChecked();
  await expect(reloadedGroup).toContainText('已选一级 2 项、二级 3 项');
  await page.getByRole('button', { name: '保存伙伴信息', exact: true }).click();
  await expect(page.getByText('伙伴信息已保存。', { exact: true })).toBeVisible();

  // Also test Level-2 disambiguation & filter: TZ行业大模型/数据工程 vs 盘古大模型/数据工程 + OR/AND filter semantics.
  const tzPartnerName = `TZ数据工程伙伴-${randomUUID().slice(0, 8)}`;
  const tzCreateRes = await request.post(`${api}/partners`, {
    headers: adminHeaders,
    data: {
      name: tzPartnerName,
      identities: ['服务合作伙伴'],
      capabilities: 'TZ行业大模型',
      sub_capabilities: [{ parent: 'TZ行业大模型', name: '数据工程' }],
    },
  });
  expect(tzCreateRes.status()).toBe(201);
  const tzPartner = await tzCreateRes.json();

  // Re-open /admin/partners/[id] for tzPartner and verify duplicate-named 数据工程 checks only under TZ行业大模型.
  await page.goto(`/admin/partners/${tzPartner.id}`);
  const tzPageGroup = page.getByRole('group', { name: '能力标签（一二级多选）', exact: true });
  const tzCard = tzPageGroup.locator('.capability-l1-card').filter({ has: page.locator('.capability-l1-label > span', { hasText: /^TZ行业大模型$/ }) });
  const panguCardOnTz = tzPageGroup.locator('.capability-l1-card').filter({ has: page.locator('.capability-l1-label > span', { hasText: /^盘古大模型$/ }) });
  await expect(tzCard.locator('.capability-l2-label', { hasText: /^数据工程$/ }).getByRole('checkbox')).toBeChecked();
  await expect(panguCardOnTz.locator('.capability-l1-label').getByRole('checkbox')).not.toBeChecked();

  // Filter /admin/partners using 细分能力 ("TZ行业大模型/数据工程" vs "盘古大模型/数据工程").
  await page.goto('/admin/partners');
  const adminToolbar = page.getByRole('region', { name: '伙伴筛选', exact: true });
  await adminToolbar.getByRole('button', { name: '细分能力筛选', exact: true }).click();
  const subPopover = page.getByRole('group', { name: '细分能力选项', exact: true });
  await subPopover.getByRole('checkbox', { name: 'TZ行业大模型/数据工程', exact: true }).check();
  const tableRows = page.locator('.data-table tbody tr');
  await expect(tableRows).toHaveCount(1);
  await expect(tableRows.first()).toContainText(tzPartnerName);
  // Adding 盘古大模型/数据工程 acts as OR within capability filters -> shows both partners.
  await subPopover.getByRole('checkbox', { name: '盘古大模型/数据工程', exact: true }).check();
  await expect(tableRows).toHaveCount(2);
  // Adding 伙伴身份 filter acts as AND across dimensions -> narrows back to tzPartnerName.
  await adminToolbar.getByRole('button', { name: '伙伴身份筛选', exact: true }).click();
  await page.getByRole('group', { name: '伙伴身份选项', exact: true }).getByRole('checkbox', { name: '服务合作伙伴', exact: true }).check();
  await expect(tableRows).toHaveCount(1);
  await expect(tableRows.first()).toContainText(tzPartnerName);

  // 3. User-side /partners & /partners/[id]: verify Level-2 search and grouped display.
  const identityRes = await page.request.post(`${api}/auth/identity/session`, {
    headers: { Origin: origin },
    data: { create: true },
  });
  expect(identityRes.status()).toBe(200);
  const member = await identityRes.json();
  await page.addInitScript((session) => {
    localStorage.setItem('banfei:user:token', session.access_token);
    localStorage.setItem('banfei:user:user', JSON.stringify(session.user));
    localStorage.setItem('banfei:user:device-secret', session.device_secret);
  }, member);

  await page.goto('/partners');
  await page.getByLabel('搜索伙伴', { exact: true }).fill('模型预训练/微调');
  const matchingCard = page.locator('.partner-insight-card').filter({ has: page.getByRole('heading', { name: partnerName, exact: true }) });
  await expect(matchingCard).toHaveCount(1);

  await page.goto(`/partners/${partner.id}`);
  await expect(page.getByRole('heading', { name: partnerName, exact: true })).toBeVisible();
  const capSummary = page.getByRole('list', { name: '正式能力标签', exact: true });
  await expect(capSummary.locator('.partner-capability-l1-badge')).toHaveText(['盘古大模型', '应用现代化']);
  await expect(capSummary.locator('.partner-capability-summary-item').filter({ hasText: '盘古大模型' })).toContainText('模型预训练/微调');
  await expect(capSummary.locator('.partner-capability-summary-item').filter({ hasText: '盘古大模型' })).toContainText('数据工程');
  await expect(capSummary.locator('.partner-capability-summary-item').filter({ hasText: '应用现代化' })).toContainText('开发现代化');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await saveShot(page, info, 'user-partner-detail-tree.png');

  expect(pageErrors).toEqual([]);
  expect(modelWrites).toEqual([]);
});

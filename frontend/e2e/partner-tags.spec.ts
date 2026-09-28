import { expect, test } from '@playwright/test';

const longTag = '超长能力标签用于确认窄屏内自然换行并完整保留而不会省略或挤出卡片边界';
const capabilities = ['CodeArts 应用交付', 'TCP/IP', '数据库迁移', '系统集成', '数据分析', '数据分析', longTag];
const industries = ['金融', '制造', '能源电力', '交通物流', '部委与公共事业', '医疗健康'];
const regions = ['北京', '上海', '广东', '江苏', '四川', '陕西', '湖北', '浙江'];
const partner = {
  id: 'pill-preview', name: '合成标签伙伴', intro: '用于隔离界面验证。',
  capabilities: ` ${capabilities[0]},${capabilities[1]}，${capabilities[2]}、${capabilities[3]};${capabilities[4]}；${capabilities[5]}\n${longTag} `,
  industries: industries.join(','), service_areas: regions.join(','), ai_profile: null,
  created_at: '2026-09-01', case_count: 0, deliverable_count: 0,
  classification_pending: { industries: ['待确认示例'] },
};

for (const width of [1366, 1920, 390]) test(`partner pills preserve labels and navigation ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: width === 1920 ? 1080 : width === 390 ? 844 : 768 });
  await page.addInitScript(() => localStorage.setItem('banfei:user:token', 'synthetic-pill-user'));
  const unexpected: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace(/^\/api/, '');
    if (!url.pathname.startsWith('/api/') && url.port !== '8000') {
      return ['localhost', '127.0.0.1'].includes(url.hostname) ? route.continue() : route.abort();
    }
    if (request.method() !== 'GET') { unexpected.push(request.method() + ' ' + path); return route.abort(); }
    let json: unknown;
    if (path === '/auth/me') json = { id: 'pill-user', username: 'pill-user', role: 'user', status: 'active', must_change_password: false };
    else if (path === '/health') json = { status: 'ok' };
    else if (path === '/agent/tasks') json = { items: [], total: 0, page: 1, pageSize: 20, totalPages: 0 };
    else if (path === '/partners/profiles') json = [partner,
      { ...partner, id: 'empty-preview', name: '空标签伙伴', capabilities: null, industries: '', service_areas: '  ' },
      { ...partner, id: 'short-preview', name: '少量标签伙伴', capabilities: '云,AI' },
      { ...partner, id: 'long-preview', name: '长标签伙伴', capabilities: longTag },
    ];
    else if (path === '/partners/pill-preview') json = partner;
    else if (path === '/enablement/resources') json = { items: [], total: 0 };
    else { unexpected.push(path); return route.abort(); }
    return route.fulfill({ json });
  });

  await page.goto('/partners');
  await page.evaluate(() => document.fonts.ready);
  const card = page.locator('.partner-insight-card').first();
  const list = card.getByRole('list', { name: '能力标签', exact: true });
  const visibleTags = list.locator('[data-partner-tag]:visible');
  await expect(visibleTags.first()).toBeVisible();
  const count = await visibleTags.count();
  expect(count).toBeLessThan(capabilities.length);
  await expect(visibleTags).toHaveText(capabilities.slice(0, count));
  await expect(list.locator('.partner-tag-count')).toHaveText(`+${capabilities.length - count} 个能力标签`);
  await expect(list).toHaveCSS('height', '24px');
  const short = page.locator('.partner-insight-card').nth(2).getByRole('list', { name: '能力标签', exact: true });
  await expect(short.getByRole('listitem')).toHaveText(['云', 'AI']);
  const long = page.locator('.partner-insight-card').nth(3).getByRole('list', { name: '能力标签', exact: true });
  await expect(long.getByRole('listitem')).toHaveText(['+1 个能力标签']);
  await expect(card.locator('.partner-field > span')).toHaveText(['能力标签', '行业', '区域']);
  for (const [label, tags] of [['行业', industries], ['区域', regions]] as const) {
    const field = card.getByRole('list', { name: label, exact: true });
    const shown = field.locator('[data-partner-tag]:visible');
    await expect(shown.first()).toBeVisible();
    const length = await shown.count();
    expect(length).toBeLessThan(tags.length);
    await expect(shown).toHaveText(tags.slice(0, length));
    await expect(field.locator('.partner-tag-count')).toHaveText(`+${tags.length - length} 个${label}`);
    await expect(field).toHaveCSS('height', '24px');
  }
  const empty = page.locator('.partner-insight-card').nth(1);
  await expect(empty.locator('.partner-tag-list')).toHaveCount(0);
  await expect(empty.locator('.partner-tag-empty')).toHaveText(['暂无正式能力标签', '暂无行业信息', '暂无区域信息']);
  const checkFit = async () => {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expect(await page.locator('.partner-tag-list li:visible').evaluateAll(items => items.every(item => {
      const rect = item.getBoundingClientRect(), parent = item.parentElement!.getBoundingClientRect();
      return rect.left >= parent.left - 1 && rect.right <= parent.right + 1 && item.scrollWidth <= item.clientWidth && item.scrollHeight <= item.clientHeight;
    }))).toBeTruthy();
  };
  await checkFit();
  // Resize the card without remounting it: the count must reflect actual available width.
  await card.evaluate(element => { element.style.maxWidth = '220px'; });
  await expect(visibleTags).toHaveCount(0);
  await expect(list.locator('.partner-tag-count')).toHaveText(`+${capabilities.length} 个能力标签`);
  await card.evaluate(element => { element.style.removeProperty('max-width'); });
  await expect(visibleTags).toHaveCount(count);
  await checkFit();
  // A hidden capability remains searchable in the original data.
  await page.getByPlaceholder('搜索伙伴名称、能力、行业或区域').fill('数据库迁移');
  await expect(page.locator('.partner-insight-card')).toHaveCount(1);
  // The summary is not an inline expander: it follows the existing full-card detail link.
  const pill = list.locator('.partner-tag-count');
  await pill.scrollIntoViewIfNeeded();
  const box = (await pill.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page).toHaveURL(/\/partners\/pill-preview$/);
  await expect(page.getByRole('heading', { name: partner.name })).toBeVisible();
  await expect(page.getByRole('list', { name: '正式能力标签', exact: true }).getByRole('listitem')).toHaveText(capabilities);
  await expect(page.getByRole('list', { name: '行业经验', exact: true }).getByRole('listitem')).toHaveText(industries);
  await expect(page.getByRole('list', { name: '服务区域', exact: true }).getByRole('listitem')).toHaveText(regions);
  await expect(page.getByText(/待确认分类：待确认示例/)).toBeVisible();
  await checkFit();
  await page.getByRole('link', { name: '返回伙伴洞察', exact: true }).click();
  await expect(page).toHaveURL(/\/partners$/);
  expect(unexpected).toEqual([]);
  expect(errors).toEqual([]);
});

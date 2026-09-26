import {test, expect, type Page} from '@playwright/test';

// Every backend request is intercepted: these UI checks never mutate runtime data.
async function setup(page: Page) {
  const rows = [
    {source_id: 'course-a', metadata: {resource_type: 'course', title: '完整课程'}, revision: 4, status: 'draft', published_version: null},
    {source_id: 'lab-b', metadata: {resource_type: 'lab', title: '完整实验'}, revision: 7, status: 'published', published_version: 2},
  ];
  const calls: {action: string; items: {source_id: string; base_revision: number}[]}[] = [];
  const unhandled: string[] = [];
  let importFails = false;
  let importCount = 0;
  await page.addInitScript(() => localStorage.setItem('banfei:admin:token', 'isolated-ui-fixture'));
  await page.route('http://localhost:8000/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/health') return route.fulfill({json: {status: 'ok'}});
    if (path === '/auth/me') return route.fulfill({json: {id: 'admin', role: 'admin', username: '合成管理员', status: 'active', must_change_password: false}});
    if (path === '/admin/enablement/resources') return route.fulfill({json: rows});
    if (path === '/admin/enablement/resource-categories') return route.fulfill({json: []});
    if (path === '/admin/enablement/resources/batch') {
      const body = route.request().postDataJSON(); calls.push(body);
      for (const item of body.items) {
        const row = rows.find(r => r.source_id === item.source_id)!;
        row.status = body.action === 'publish' ? 'published' : 'unpublished'; row.revision += 1;
      }
      return route.fulfill({json: {changed: body.items.length, skipped: 0}});
    }
    if (path === '/admin/enablement/resources/export') return route.fulfill({contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', body: 'synthetic-workbook'});
    if (path === '/admin/enablement/resources/import') {
      importCount += 1;
      expect(route.request().headers()['content-type']).toContain('multipart/form-data');
      return importFails ? route.fulfill({status: 422, json: {detail: '“课程与实验”第3行：跳转链接无效'}}) : route.fulfill({json: {created: 1, updated: 1, unchanged: 0, categories_added: 0}});
    }
    unhandled.push(path); return route.abort();
  });
  await page.goto('/admin/resources');
  await expect(page.getByText('完整课程', {exact: true})).toBeVisible();
  return {calls, unhandled, failImport: () => { importFails = true; }, importCount: () => importCount};
}

test('resource filters, cancel, batch publication and removal pass selected revisions', async ({page}) => {
  const state = await setup(page);
  await expect(page.getByRole('button', {name: '批量上架', exact: true})).toBeDisabled();
  await page.getByLabel('筛选资源类型').selectOption('lab');
  await page.getByLabel('选择当前筛选的全部资源').check();
  await expect(page.getByText('已选 1 条')).toBeVisible();
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', {name: '批量上架', exact: true}).click();
  expect(state.calls).toHaveLength(0);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: '批量上架', exact: true}).click();
  await expect(page.getByRole('status')).toContainText('已上架 1 条');
  expect(state.calls[0]).toEqual({action: 'publish', items: [{source_id: 'lab-b', base_revision: 7}]});
  await expect(page.getByLabel('选择当前筛选的全部资源')).not.toBeChecked();
  await page.getByLabel('选择资源 完整实验').check();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: '批量下架', exact: true}).click();
  await expect(page.getByRole('status')).toContainText('已下架 1 条');
  expect(state.calls[1].items).toEqual([{source_id: 'lab-b', base_revision: 8}]);
  expect(state.unhandled).toEqual([]);
});

test('Excel download, import success and actionable row error', async ({page}) => {
  const state = await setup(page);
  const downloadReady = page.waitForEvent('download');
  await page.getByRole('button', {name: '导出全部 Excel'}).click();
  const download = await downloadReady;
  expect(download.suggestedFilename()).toBe('伴飞课程与实验.xlsx');
  expect(await download.failure()).toBeNull();
  const file = {name: 'resources.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('synthetic-workbook')};
  page.once('dialog', dialog => dialog.accept());
  await page.getByLabel('导入课程与实验文件').setInputFiles(file);
  await expect(page.getByRole('status')).toContainText('新增 1 条，更新 1 条');
  state.failImport();
  page.once('dialog', dialog => dialog.accept());
  await page.getByLabel('导入课程与实验文件').setInputFiles(file);
  await expect(page.getByRole('alert').filter({hasText: '第3行'})).toContainText('跳转链接无效');
  expect(state.importCount()).toBe(2);
  expect(state.unhandled).toEqual([]);
});

test('resource maintenance toolbar fits mobile and supports keyboard selection', async ({page}) => {
  const state = await setup(page);
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.getByRole('button', {name: '导入 Excel', exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByLabel('选择当前筛选的全部资源').focus();
  await page.keyboard.press('Space');
  await expect(page.getByText('已选 2 条')).toBeVisible();
  expect(state.unhandled).toEqual([]);
});

test('partner Excel and resource template download entries', async ({page}) => {
  const unhandled: string[] = [];
  let imported = false;
  await page.addInitScript(() => localStorage.setItem('banfei:admin:token', 'isolated-ui-fixture'));
  await page.route('http://localhost:8000/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/auth/me') return route.fulfill({json: {id: 'admin', role: 'admin', status: 'active', must_change_password: false}});
    if (path === '/health') return route.fulfill({json: {status: 'ok'}});
    if (['/partners/template', '/partners/export', '/admin/enablement/resources/template'].includes(path)) return route.fulfill({body: 'synthetic-excel', contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
    if (path === '/partners/import') {
      imported = true;
      expect(route.request().headers()['content-type']).toContain('multipart/form-data');
      return route.fulfill({json: {created: 1, updated: 0, unchanged: 0}});
    }
    if (['/partners', '/admin/enablement/resources', '/admin/enablement/resource-categories'].includes(path)) return route.fulfill({json: []});
    unhandled.push(path); return route.abort();
  });
  await page.goto('/admin/partners');
  async function download(label: string, filename: string) {
    const ready = page.waitForEvent('download');
    await page.getByRole('button', {name: label, exact: true}).click();
    expect((await ready).suggestedFilename()).toBe(filename);
  }
  await download('下载导入模板', '伴飞伙伴导入模板.xlsx');
  await download('导出全部 Excel', '伴飞伙伴信息.xlsx');
  page.once('dialog', dialog => dialog.accept());
  await page.getByLabel('导入伙伴Excel文件').setInputFiles({name: 'partners.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('synthetic-excel')});
  await expect(page.getByText('导入完成：新增 1 家，更新 0 家，未变化 0 家。')).toBeVisible();
  expect(imported).toBe(true);
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.goto('/admin/resources');
  await download('下载导入模板', '伴飞课程与实验导入模板.xlsx');
  expect(unhandled).toEqual([]);
});

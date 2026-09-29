import { test, expect, type Page } from '@playwright/test';

async function setup(page: Page, failSave = false) {
  let saved = { timeoutSeconds: 300, timeoutRetries: 3 };
  const writes: object[] = [];
  await page.addInitScript(() => localStorage.setItem('banfei:admin:token', 'synthetic-timeout-admin'));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) return route.continue();
    const path = url.pathname.replace(/^\/api/, '');
    if (path === '/auth/me') return route.fulfill({ json: { id: 'admin', role: 'admin', status: 'active', must_change_password: false } });
    if (path === '/health') return route.fulfill({ json: { status: 'ok' } });
    if (path === '/admin/model-configs' || path === '/admin/model-configs/usage') return route.fulfill({ json: [] });
    if (path === '/admin/model-configs/timeout-settings') {
      if (route.request().method() === 'PUT') {
        writes.push(route.request().postDataJSON());
        if (failSave) return route.fulfill({ status: 500, json: { detail: '服务异常，请联系管理员。' } });
        saved = route.request().postDataJSON();
      }
      return route.fulfill({ json: saved });
    }
    return route.abort();
  });
  await page.goto('/admin/models');
  await expect(page.getByRole('heading', { name: '超时与重试', exact: true })).toBeVisible();
  await expect(page.getByLabel('单次超时（秒）')).toHaveValue('300');
  return { writes };
}

test('timeout form saves, reloads and takes effect immediately', async ({ page }, testInfo) => {
  const { writes } = await setup(page);
  await page.getByLabel('单次超时（秒）').fill('420');
  await page.getByLabel('超时重试次数').fill('0');
  await page.getByRole('button', { name: '保存超时设置', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('设置已保存，新发起的模型调用立即生效。');
  expect(writes).toEqual([{ timeoutSeconds: 420, timeoutRetries: 0 }]);
  await page.reload();
  await expect(page.getByLabel('单次超时（秒）')).toHaveValue('420');
  await expect(page.getByLabel('超时重试次数')).toHaveValue('0');
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: testInfo.outputPath('timeout-settings.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.reload();
});

test('timeout save failure preserves input and releases the save button', async ({ page }) => {
  const { writes } = await setup(page, true);
  await page.getByLabel('单次超时（秒）').fill('600');
  await page.getByLabel('超时重试次数').fill('1');
  await page.getByRole('button', { name: '保存超时设置', exact: true }).click();
  await expect(page.getByRole('region', { name: '超时与重试', exact: true }).getByRole('alert')).toHaveText('服务异常，请联系管理员。');
  await expect(page.getByLabel('单次超时（秒）')).toHaveValue('600');
  await expect(page.getByLabel('超时重试次数')).toHaveValue('1');
  await expect(page.getByRole('button', { name: '保存超时设置', exact: true })).toBeEnabled();
  expect(writes).toHaveLength(1);
});

test('timeout form rejects zero seconds and fractional retries without saving', async ({ page }) => {
  const { writes } = await setup(page);
  await page.getByLabel('单次超时（秒）').fill('0');
  await page.getByRole('button', { name: '保存超时设置', exact: true }).click();
  await expect(page.getByRole('region', { name: '超时与重试', exact: true }).getByRole('alert')).toContainText('超时时间须大于 0');
  await page.getByLabel('单次超时（秒）').fill('300');
  await page.getByLabel('超时重试次数').fill('1.5');
  await page.getByRole('button', { name: '保存超时设置', exact: true }).click();
  expect(await page.getByLabel('超时重试次数').evaluate((input: HTMLInputElement) => input.validity.valid)).toBeFalsy();
  expect(writes).toHaveLength(0);
});

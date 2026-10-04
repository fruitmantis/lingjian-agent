import { test, expect, type Page } from '@playwright/test';

async function setup(page: Page, failSave = false) {
  let saved = { modelConfigId:'model-1', thinking:true, timeoutSeconds: 300, timeoutRetries: 3 };
  const settings=()=>({agents:{partner_match:{...saved,name:'伙伴匹配',description:'合成匹配',icon:'users',enabled:true},partner_development:{...saved,name:'伙伴发展',description:'合成发展',icon:'trend',enabled:true}},processing:saved});
  const writes: object[] = [];
  await page.addInitScript(() => localStorage.setItem('banfei:admin:token', 'synthetic-timeout-admin'));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) return route.continue();
    const path = url.pathname.replace(/^\/api/, '');
    if (path === '/auth/me') return route.fulfill({ json: { id: 'admin', role: 'admin', status: 'active', must_change_password: false } });
    if (path === '/health') return route.fulfill({ json: { status: 'ok' } });
    if (path === '/admin/model-configs') return route.fulfill({ json: [{id:'model-1',name:'合成连接',modelName:'synthetic',enabled:true,maxTokens:1024,temperature:.3,provider:'Synthetic',baseUrl:'https://model.invalid',apiKeyConfigured:true}] });
    if (path === '/admin/agents') return route.fulfill({json:settings()});
    if (path === '/admin/agents/processing') {
      if (route.request().method() === 'PUT') {
        writes.push(route.request().postDataJSON());
        if (failSave) return route.fulfill({ status: 500, json: { detail: '服务异常，请联系管理员。' } });
        saved = route.request().postDataJSON();
      }
      return route.fulfill({ json: settings() });
    }
    return route.abort();
  });
  await page.goto('/admin/models');
  await expect(page.getByRole('heading', { name: '基础配置', exact: true })).toBeVisible();
  await expect(page.getByTestId('agent-processing').getByLabel('请求超时（秒）')).toHaveValue('300');
  return { writes };
}

test('timeout form saves, reloads and takes effect immediately', async ({ page }, testInfo) => {
  const { writes } = await setup(page);
  await page.getByTestId('agent-processing').getByLabel('请求超时（秒）').fill('420');
  await page.getByTestId('agent-processing').getByRole('button', { name: '保存配置', exact: true }).click();
  await expect(page.getByTestId('agent-processing').getByRole('status')).toHaveText('已保存');
  expect(writes).toEqual([{ modelConfigId:'model-1', thinking:true, timeoutSeconds:420, timeoutRetries:3 }]);
  await page.reload();
  await expect(page.getByTestId('agent-processing').getByLabel('请求超时（秒）')).toHaveValue('420');
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: testInfo.outputPath('timeout-settings.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.reload();
});

test('timeout save failure preserves input and releases the save button', async ({ page }) => {
  const { writes } = await setup(page, true);
  await page.getByTestId('agent-processing').getByLabel('请求超时（秒）').fill('600');
  await page.getByTestId('agent-processing').getByRole('button', { name: '保存配置', exact: true }).click();
  await expect(page.getByTestId('agent-processing').getByRole('status')).toHaveText('服务异常，请联系管理员。');
  await expect(page.getByTestId('agent-processing').getByLabel('请求超时（秒）')).toHaveValue('600');
  await expect(page.getByTestId('agent-processing').getByRole('button', { name: '保存配置', exact: true })).toBeEnabled();
  expect(writes).toHaveLength(1);
});

test('processing form rejects zero seconds without saving', async ({ page }) => {
  const { writes } = await setup(page);
  const card=page.getByTestId('agent-processing');
  await card.getByLabel('请求超时（秒）').fill('0');
  await expect(card.getByRole('button',{name:'保存配置',exact:true})).toBeDisabled();
  expect(writes).toHaveLength(0);
});

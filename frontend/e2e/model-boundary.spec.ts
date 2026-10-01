import {test, expect} from '@playwright/test';

test('model deletion supports cancel, success and server errors', async ({page}) => {
  const configs = ['unused', 'referenced'].map(id => ({
    id, name: id === 'unused' ? '默认首选模型' : '待删除模型', provider: 'Synthetic',
    baseUrl: 'https://model.invalid/v1', modelName: 'synthetic', maxTokens: 1024,
    temperature: 0.3, enabled: true, isDefault: id === 'unused', apiKeyConfigured: true,
  }));
  const deleted: string[] = [];
  const unexpected: string[] = [];
  await page.addInitScript(() => localStorage.setItem('banfei:admin:token', 'isolated-model-ui'));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) return route.continue();
    const path = url.pathname.replace(/^\/api/, '');
    if (path === '/health') return route.fulfill({json:{status:'ok'}});
    if (path === '/auth/me') return route.fulfill({json: {id:'admin',role:'admin',status:'active',must_change_password:false}});
    if (path === '/admin/model-configs') return route.fulfill({json: configs.filter(c => !deleted.includes(c.id))});
    if (path === '/admin/model-configs/timeout-settings') return route.fulfill({json:{timeoutSeconds:300,timeoutRetries:3}});
    if (path === '/admin/model-configs/usage') return route.fulfill({json: []});
    if (route.request().method() === 'DELETE' && path === '/admin/model-configs/unused') {
      deleted.push('unused'); return route.fulfill({status:204});
    }
    if (route.request().method() === 'DELETE' && path === '/admin/model-configs/referenced') {
      return route.fulfill({status:500,json:{detail:'删除失败，请稍后重试。'}});
    }
    unexpected.push(path); return route.abort();
  });
  await page.goto('/admin/models');
  const unused = page.getByRole('row').filter({hasText:'默认首选模型'});
  page.once('dialog', dialog => dialog.dismiss());
  await unused.getByRole('button', {name:'删除',exact:true}).click();
  await expect(unused).toBeVisible();
  expect(deleted).toEqual([]);
  page.once('dialog', async dialog => {
    expect(dialog.message()).toContain('请确认仍有可用的场景首选或系统默认');
    await dialog.accept();
  });
  await unused.getByRole('button', {name:'删除',exact:true}).click();
  await expect(unused).toHaveCount(0);
  expect(deleted).toEqual(['unused']);
  page.once('dialog', dialog => dialog.accept());
  const referenced = page.getByRole('row').filter({hasText:'待删除模型'});
  await referenced.getByRole('button', {name:'删除',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'服务异常'})).toContainText('请联系管理员');
  await expect(referenced).toBeVisible();
  expect(unexpected).toEqual([]);
});

test('UI tests do not require a model: login, navigation and resource browsing', async ({page}) => {
  await page.goto('/admin/login');
  await page.getByLabel('用户名', {exact:true}).fill('admin1');
  await page.getByLabel('密码', {exact:true}).fill('ValidationPass123');
  await page.getByRole('button', {name:'登录', exact:true}).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.getByRole('link', {name:'返回伴飞 Agent', exact:true}).click();
  await page.getByRole('dialog', {name:'保存你的身份 Key'}).getByRole('button', {name:'稍后保存',exact:true}).click();
  const identity=await page.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null'));
  expect(identity?.role).toBe('user');
  await expect(page.getByRole('link', {name:'资源中心', exact:true})).toBeVisible();
  await page.getByRole('link', {name:'资源中心', exact:true}).click();
  await expect(page.getByRole('heading', {name:'资源中心', exact:true})).toBeVisible();
  await page.getByRole('link', {name:'开启新任务', exact:true}).click();
  await expect(page.getByRole('tablist', {name:'任务模式'}).getByRole('tab', {name:'伙伴发展', exact:true})).toBeVisible();
});

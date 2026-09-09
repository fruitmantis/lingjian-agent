import {test, expect} from '@playwright/test';

test('UI tests do not require a model: login, navigation and resource browsing', async ({page}) => {
  await page.goto('/login');
  await page.getByLabel('用户名', {exact:true}).fill('admin1');
  await page.getByLabel('密码', {exact:true}).fill('ValidationPass123');
  await page.getByRole('button', {name:'登录', exact:true}).click();
  await expect(page.getByRole('link', {name:'资源中心', exact:true})).toBeVisible();
  await page.getByRole('link', {name:'资源中心', exact:true}).click();
  await expect(page.getByRole('heading', {name:'资源中心', exact:true})).toBeVisible();
  await page.getByRole('link', {name:'开启新任务', exact:true}).click();
  await expect(page.getByRole('tablist', {name:'任务模式'}).getByRole('tab', {name:'能力发展', exact:true})).toBeVisible();
});

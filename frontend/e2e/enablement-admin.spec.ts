import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
const API='http://127.0.0.1:8100';

async function login(page:Page,request:APIRequestContext,username='admin1'){
  const response=await request.post(`${API}/auth/login`,{data:{username,password:'ValidationPass123'}});
  expect(response.ok()).toBeTruthy();const session=await response.json();
  await page.addInitScript(session=>{localStorage.setItem('token',session.access_token);localStorage.setItem('user',JSON.stringify(session.user));},session);
  return {Authorization:`Bearer ${session.access_token}`};
}
async function grant(page:Page){
  await page.getByLabel('系统内可见',{exact:true}).check();
  await page.getByLabel('允许发送模型',{exact:true}).check();
  await page.getByLabel('允许对伙伴外发',{exact:true}).check();
  await page.getByLabel('授权或下架原因').fill('合成资源授权核验，仅用于自动化测试');
  await page.getByRole('button',{name:'保存用途授权',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('用途授权已保存');
}
async function reviewAndPublish(page:Page){
  await page.getByLabel('链接检查状态').selectOption('available');
  await page.getByLabel(/已核验内容与能力映射/).check();
  await page.getByLabel('已核验上述用途授权依据').check();
  await page.getByRole('button',{name:'记录人工核验',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('人工核验记录已保存');
  await page.getByRole('button',{name:'发布新版本',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('已发布新的独立版本');
}

for(const resourceType of ['course','lab']){
 test(`RES-01/05/07 ${resourceType} metadata review publication and removal`,async({page,request})=>{
  await login(page,request);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/admin/resources');
  await page.getByRole('button',{name:'新增资源',exact:true}).click();
  await page.getByLabel('资源类型',{exact:true}).selectOption(resourceType);
  await page.getByLabel('资源名称',{exact:true}).fill(resourceType==='course'?'课程发布合成验证':'实验发布合成验证');
  await page.getByLabel('内容摘要',{exact:true}).fill('合成资源摘要，无真实业务资料');
  await page.getByLabel('目标能力与用途').fill('数据库迁移实践');
  await page.getByLabel('来源平台',{exact:true}).fill('合成平台');
  await page.getByLabel('来源链接',{exact:true}).fill(`https://example.com/${resourceType}`);
  await page.getByLabel('数据库',{exact:true}).check();
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await expect(page.getByRole('heading',{name:'用途授权',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'发布新版本',exact:true})).toBeDisabled();
  await expect(page.getByLabel('允许对伙伴外发',{exact:true})).not.toBeChecked();
  await grant(page);await reviewAndPublish(page);
  await expect(page.getByRole('heading',{name:'当前发布快照',exact:true})).toBeVisible();
  await page.getByLabel('资源名称',{exact:true}).fill('尚未发布的修改');
  await expect(page.getByRole('button',{name:'发布新版本',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('草稿已保存');
  await expect(page.getByRole('button',{name:'发布新版本',exact:true})).toBeDisabled();
  await page.getByLabel('授权或下架原因').fill('合成下架测试');
  await page.getByRole('button',{name:'普通下架',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('已下架');
  expect(errors).toEqual([]);
 });
}

test('CASE-01/02 sharing is configured from existing case and separately versioned',async({page,request})=>{
  await login(page,request);
  await page.goto('/admin/partners/partner-1');
  await page.getByRole('link',{name:'共享设置',exact:true}).click();
  await expect(page.getByRole('heading',{name:'案例共享配置',exact:true})).toBeVisible();
  await expect(page.getByLabel('共享标题',{exact:true})).toHaveValue('');
  await page.getByLabel('共享标题',{exact:true}).fill('合成共享学习版本');
  await page.getByLabel('内容摘要',{exact:true}).fill('已脱敏共享摘要');
  await page.getByLabel('可学习的方法',{exact:true}).fill('迁移验证与复盘');
  await page.getByLabel('贡献伙伴实际角色',{exact:true}).fill('承担迁移验证，不代表全部项目能力');
  await page.getByLabel('来源平台',{exact:true}).fill('合成案例平台');
  await page.getByLabel('来源链接',{exact:true}).fill('https://example.com/case');
  await page.getByLabel('数据库',{exact:true}).check();
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('草稿已保存');
  await grant(page);await reviewAndPublish(page);
  await page.getByLabel('授权或下架原因').fill('合成敏感撤权');
  await page.getByRole('button',{name:'敏感内容撤权',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('授权已撤销');
  await expect(page.getByText('已撤销授权 · 编辑修订',{exact:false})).toBeVisible();
  await page.getByRole('link',{name:'返回伙伴案例',exact:true}).click();
  await expect(page.getByRole('heading',{name:'制造知识库案例',exact:true})).toBeVisible();
});

test('SEC-03 user cannot access resource or sharing admin pages/API',async({page,request})=>{
 const headers=await login(page,request,'user_a');
 for(const url of ['/admin/enablement/resources','/admin/cases/case-1/sharing']){
  expect((await request.get(API+url,{headers})).status()).toBe(403);
 }
 await page.goto('/admin/resources');await expect(page).toHaveURL(/\/403$/);
});

for(const width of [1366,1920]){
 test(`ACC-02/03 Phase A screenshots ${width}`,async({page,request})=>{
  await login(page,request);await page.setViewportSize({width,height:width===1366?768:1080});
  const directory=path.resolve('../.isolation/evidence/phase-a-regression');await mkdir(directory,{recursive:true});
  for(const [name,url] of [['resource-list','/admin/resources'],['case-sharing','/admin/partners/partner-1/cases/case-1/sharing']]){
    await page.goto(url);await expect(page.getByRole('heading',{level:1})).toBeVisible();
    await expect(page.getByText('加载配置中…')).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.screenshot({path:path.join(directory,`${name}-${width}.png`),fullPage:true});
  }
  await page.goto('/admin/resources');await page.getByRole('button',{name:'管理资源',exact:true}).first().click();
  await expect(page.getByRole('heading',{name:'用途授权',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:path.join(directory,`resource-editor-${width}.png`),fullPage:true});
 });
}

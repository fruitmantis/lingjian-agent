import {test,expect,type Page} from '@playwright/test';
const origin=process.env.PLAYWRIGHT_HTTP_ORIGIN||'http://localhost';
async function capture(page:Page,name:string){
 await page.evaluate(()=>document.fonts.ready);
 await page.screenshot({path:test.info().outputPath(name+'.png'),fullPage:false,style:".identity-key-value, #identity-switch-target { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; } .admin-identity-key-hint { visibility: hidden !important; }"});
}
async function closeWelcome(page:Page){
 await page.goto('/');const d=page.getByRole('dialog',{name:'欢迎使用伴飞'});
 await expect(d.getByRole('button',{name:'复制登录链接',exact:true,includeHidden:true})).toBeEnabled();
 await d.getByRole('button',{name:'开始使用伴飞',exact:true}).click();await expect(d).toHaveCount(0);
 return page.evaluate(()=>({user:JSON.parse(localStorage.getItem('banfei:user:user')!),token:localStorage.getItem('banfei:user:token')!}));
}
for(const width of [1366,390]){
 test('followup: welcome copy, account gap and ordinary switch '+width,async({page})=>{
  await page.setViewportSize({width,height:width===390?844:900});
  await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(t:string)=>{(window as any).lastCopied=t;}}});});
  await page.goto('/');const welcome=page.getByRole('dialog',{name:'欢迎使用伴飞'});
  await expect(welcome.getByRole('heading',{name:'收藏链接，下次继续使用',exact:true})).toBeVisible();
  await expect(welcome.getByText('请勿分享给他人',{exact:false})).toBeVisible();
  await expect(welcome.getByRole('button',{name:'复制登录链接',exact:true,includeHidden:true})).toBeEnabled();
  const preview=welcome.getByTestId('identity-key');await expect(preview).toBeVisible();
  expect(await preview.evaluate(el=>getComputedStyle(el).textOverflow==='ellipsis'&&getComputedStyle(el).whiteSpace==='nowrap')).toBe(true);
  await capture(page,'welcome-'+width);
  await welcome.getByRole('button',{name:'复制登录链接',exact:true}).click();
  await expect(welcome.getByRole('button',{name:'已复制',exact:true})).toBeVisible();
  expect(await preview.evaluate(el=>(window as any).lastCopied===el.textContent)).toBe(true);
  await page.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('synthetic clipboard denial');}}});document.execCommand=()=>false;});
  await welcome.getByRole('button',{name:'已复制',exact:true}).click();
  await expect(welcome.getByRole('alert')).toContainText('登录链接已选中');
  expect(await preview.evaluate(el=>window.getSelection()?.toString()===el.textContent)).toBe(true);
  await capture(page,'copy-fallback-'+width);
  await welcome.getByRole('button',{name:'开始使用伴飞',exact:true}).click();await expect(welcome).toHaveCount(0);
  await page.goto('/account');
  const switcher=page.locator('main').getByRole('button',{name:'切换身份',exact:true});
  await expect(switcher).toBeEnabled();
  const owner=await page.evaluate(()=>localStorage.getItem('banfei:user:user'));
  await capture(page,'account-actions-'+width);
  let logout=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/auth/identity/logout'))logout++;});
  if(width===390)await page.getByRole('button',{name:'展开导航',exact:true}).click();
  const footer=page.locator('.sidebar-footer');await expect(footer.getByRole('button',{name:'退出',exact:true})).toHaveCount(0);
  await footer.getByRole('button',{name:'切换身份',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'切换身份',exact:true});await expect(dialog).toBeVisible();
  const input=dialog.getByRole('textbox',{name:'目标登录链接'});await input.fill('http://localhost/#k=synthetic-preview-only');
  expect(await input.evaluate(el=>parseFloat(getComputedStyle(el).paddingLeft)>=12&&parseFloat(getComputedStyle(el).borderRadius)>=6)).toBe(true);
  await capture(page,'switch-input-'+width);
  await dialog.getByRole('button',{name:'取消',exact:true}).click();await expect(dialog).toHaveCount(0);
  expect(logout).toBe(0);
  expect(await page.evaluate(()=>localStorage.getItem('banfei:user:user'))).toBe(owner);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 });
 test('followup: admin employee saved/null, read-only edit and admin logout '+width,async({page,browser})=>{
  await page.setViewportSize({width,height:width===390?844:900});const first=await closeWelcome(page);
  const update=await page.request.patch(origin+'/api/auth/me',{headers:{Authorization:'Bearer '+first.token},data:{employee_number:'000-QA-7'}});expect(update.ok()).toBe(true);
  const extra=await browser.newContext({baseURL:origin});const extraPage=await extra.newPage();const empty=await closeWelcome(extraPage);await extra.close();
  const response=await page.request.post(origin+'/api/auth/admin/login',{data:{username:'admin1',password:'ValidationPass123'}});expect(response.ok()).toBe(true);const admin=await response.json();
  await page.evaluate(data=>{localStorage.setItem('banfei:admin:token',data.access_token);localStorage.setItem('banfei:admin:user',JSON.stringify(data.user));},admin);
  await page.goto('/admin/users');
  const table=page.locator('.admin-users-table');await expect(table.getByRole('columnheader',{name:'工号',exact:true})).toBeVisible();
  const row=table.getByRole('row').filter({has:page.locator('a[href="/admin/users/'+first.user.id+'"]')});
  const nullRow=table.getByRole('row').filter({has:page.locator('a[href="/admin/users/'+empty.user.id+'"]')});
  await expect(row.getByRole('cell',{name:'000-QA-7',exact:true})).toBeVisible();
  await expect(nullRow.getByRole('cell',{name:'未填写',exact:true})).toBeVisible();
  await table.getByRole('columnheader',{name:'工号',exact:true}).scrollIntoViewIfNeeded();await capture(page,'admin-employee-list-'+width);
  await row.getByRole('button',{name:'编辑',exact:true}).click();
  const edit=page.locator('.modal-card');await expect(edit).toContainText('工号：000-QA-7');
  await expect(edit.locator('input')).toHaveCount(2);await capture(page,'admin-employee-edit-'+width);
  await edit.getByRole('button',{name:'取消',exact:true}).click();await expect(edit).toHaveCount(0);
  await page.goto('/admin/users/'+first.user.id);
  await expect(page.locator('.detail-grid > div').filter({has:page.getByText('工号',{exact:true})})).toContainText('000-QA-7');
  await page.goto('/admin/users/'+empty.user.id);
  await expect(page.locator('.detail-grid > div').filter({has:page.getByText('工号',{exact:true})})).toContainText('未填写');
  if(width===390)await page.getByRole('button',{name:'展开导航',exact:true}).click();
  await page.locator('.sidebar-footer').getByRole('button',{name:'退出登录',exact:true}).click();
  await expect(page.getByRole('heading',{name:'管理员登录'})).toBeVisible();
  expect(await page.evaluate(()=>localStorage.getItem('banfei:admin:token'))).toBeNull();
  expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token')!==null)).toBe(true);
 });
}

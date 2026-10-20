import {test,expect,type Page} from '@playwright/test';
const origin=process.env.PLAYWRIGHT_HTTP_ORIGIN||'http://localhost';
test.use({deviceScaleFactor:1});
const who=(page:Page)=>page.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null'));
async function image(page:Page,name:string){
 await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>getSelection()?.removeAllRanges());
 await page.screenshot({path:test.info().outputPath(name+'.png'),fullPage:false,style:'.identity-key-value {position:relative;color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important} .identity-key-value::after {content:"http://…/#k=••••••";position:absolute;left:0;top:0;color:#707987!important;-webkit-text-fill-color:#707987!important;white-space:nowrap} .identity-key-value::selection {color:transparent!important;background:transparent!important}'});
}
for(const width of [1366,390])test('welcome-card: visible link, measured geometry, optional number and restoration '+width,async({page,browser})=>{
 await page.setViewportSize({width,height:width===390?844:900});
 await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(v:string)=>{(window as any).compactCopied=v;}}}));
 let patches=0;page.on('request',r=>{if(r.method()==='PATCH'&&r.url().endsWith('/auth/me'))patches++;});
 await page.goto('/');const d=page.getByRole('dialog',{name:'欢迎使用伴飞'}),input=d.getByRole('textbox',{name:'工号（可选）'}),start=d.getByRole('button',{name:'开始使用伴飞',exact:true}),copy=d.getByRole('button',{name:'复制登录链接',exact:true});
 await expect(d).toBeVisible();await expect(copy).toBeEnabled();await expect(copy).toBeVisible();await expect(d.getByRole('heading',{name:'换电脑也能用',exact:true})).toBeVisible();
 await expect(d.locator('details')).toHaveCount(0);await expect(input).toHaveValue('');
 expect(await input.getAttribute('required')).toBeNull();expect(await input.getAttribute('placeholder')).not.toContain('姓名');
 const metrics=await d.evaluate(el=>({width:el.getBoundingClientRect().width,transform:getComputedStyle(el).transform,zoom:getComputedStyle(el).zoom,dpr:devicePixelRatio,overflow:el.scrollWidth>el.clientWidth,bottom:el.getBoundingClientRect().bottom,viewport:innerHeight}));
 expect(metrics.width).toBe(Math.min(900,width-32));expect(metrics.transform).toBe('none');expect(metrics.zoom).toBe('1');expect(metrics.dpr).toBe(1);expect(metrics.overflow).toBe(false);expect(metrics.bottom<=metrics.viewport).toBe(true);
 expect((await start.boundingBox())!.height).toBe(44);
 expect(await d.locator('.identity-copy-strip').evaluate(el=>getComputedStyle(el).backgroundColor)).toBe('rgb(255, 255, 255)');
 const title=(await d.locator('h2').boundingBox())!,subtitle=(await d.locator('.identity-welcome-subtitle').boundingBox())!;expect(Math.abs(title.x-subtitle.x)).toBeLessThan(1);
 expect(await page.evaluate(()=>(window as any).compactCopied===undefined)).toBe(true);
 await d.locator('h2').click();await image(page,'compact-empty-'+width);
 await input.fill('00123456');await d.locator('h2').click();await image(page,'compact-filled-'+width);
 const original=await who(page),link=(await d.getByTestId('identity-key').textContent())!;
 await copy.click();await expect(d.getByRole('button',{name:'已复制',exact:true})).toBeVisible();
 expect(await d.getByTestId('identity-key').evaluate(el=>(window as any).compactCopied===el.textContent)).toBe(true);
 await page.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('synthetic clipboard failure');}}});document.execCommand=()=>false;});
 await d.getByRole('button',{name:'已复制',exact:true}).click();await expect(d.getByRole('alert')).toContainText('Ctrl+C');
 expect(await d.getByTestId('identity-key').evaluate(el=>getSelection()?.toString()===el.textContent)).toBe(true);
 await input.fill('');await start.click();await expect(d).toHaveCount(0);
 expect(patches).toBe(0);expect((await who(page)).id).toBe(original.id);expect((await who(page)).employee_number).toBeNull();
 const restore=await browser.newContext({baseURL:origin}),fresh=await browser.newContext({baseURL:origin});
 try{
  const p=await restore.newPage();let creates=0;p.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});await p.goto(link);await expect(p.locator('.sidebar')).toBeVisible();expect((await who(p)).id).toBe(original.id);expect(creates).toBe(0);
  const f=await fresh.newPage();await f.goto('/');const dialog=f.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(dialog).toBeVisible();const user=await who(f);await dialog.getByRole('textbox',{name:'工号（可选）'}).fill('00123456');await dialog.getByRole('button',{name:'开始使用伴飞',exact:true}).click();await expect(dialog).toHaveCount(0);expect((await who(f)).id).toBe(user.id);expect((await who(f)).employee_number).toBe('00123456');
 }finally{await restore.close();await fresh.close();}
});

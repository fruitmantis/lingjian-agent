import {expect,test} from '@playwright/test';
const origin=process.env.PLAYWRIGHT_HTTP_ORIGIN;
test.use({screenshot:'off',trace:'off'});
test('actual-IP HTTP keeps welcome, complete-link fallback and cross-tab switching',async({browser,request})=>{
 test.skip(!origin||new URL(origin).hostname==='localhost','Explicit actual-IP HTTP origin required');
 expect((await request.get(origin+'/api/health',{maxRedirects:0})).status()).toBe(200);expect((await request.get(origin+'/icon.svg',{maxRedirects:0})).status()).toBe(200);
 const context=await browser.newContext({baseURL:origin}),first=await context.newPage(),second=await context.newPage();const endpoints:string[]=[];
 for(const page of [first,second])page.on('request',r=>endpoints.push(r.url()));
 await context.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});Object.defineProperty(document,'execCommand',{value:()=>false,configurable:true});});
 try{await Promise.all([first.goto('/'),second.goto('/')]);await expect(first.locator('.sidebar')).toBeVisible();await expect(second.locator('.sidebar')).toBeVisible();
 const id=await first.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null')?.id);expect(await second.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null')?.id)).toBe(id);expect(await first.evaluate(()=>isSecureContext)).toBe(false);
 const cookie=(await context.cookies()).find(c=>c.name==='banfei_http_identity_session')!;expect(cookie.httpOnly).toBe(true);expect(cookie.secure).toBe(false);expect(cookie.sameSite).toBe('Strict');
 const dialog=first.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(dialog.getByRole('button',{name:'复制登录链接',includeHidden:true})).toBeEnabled();const link=(await dialog.getByTestId('identity-key').textContent())!;
 await first.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});Object.defineProperty(document,'execCommand',{value:()=>false,configurable:true});});
 await dialog.getByRole('button',{name:'复制登录链接'}).click();await expect(dialog.getByTestId('identity-key')).toBeVisible();await expect(dialog.locator('[role=alert]')).toContainText('Ctrl+C');expect(await first.evaluate(()=>getSelection()?.toString())).toBe(link);
 await first.screenshot({path:test.info().outputPath('http-welcome-copy-fallback.png')});await dialog.getByRole('button',{name:'开始使用伴飞'}).click();
 await first.goto('/account');await expect(first.getByTestId('identity-key')).toHaveText(link);await first.getByRole('button',{name:'复制登录链接'}).click();await expect(first.locator('.identity-credential [role=alert]')).toContainText('Ctrl+C');expect(await first.evaluate(()=>getSelection()?.toString())).toBe(link);
 const other=await browser.newContext({baseURL:origin});try{const third=await other.newPage();await third.goto('/');const welcome=third.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(welcome.getByRole('button',{name:'复制登录链接',includeHidden:true})).toBeEnabled();
 const target=(await welcome.getByTestId('identity-key').textContent())!,otherId=await third.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null')?.id);
 await first.goto(target);const change=first.getByRole('dialog',{name:'切换身份',exact:true});await expect(change).toBeVisible();await change.getByRole('button',{name:'复制登录链接'}).click();await expect(change.getByTestId('identity-key')).toBeVisible();expect(await first.evaluate(()=>getSelection()?.toString())).toBe(link);
 await first.screenshot({path:test.info().outputPath('http-switch-copy-fallback.png')});await change.getByRole('button',{name:'切换',exact:true}).click();await expect.poll(()=>first.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null')?.id)).toBe(otherId);await expect.poll(()=>second.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null')?.id)).toBe(otherId);
 }finally{await other.close();}
 expect((await request.post(origin+'/api/auth/identity/session',{headers:{Origin:'http://untrusted.invalid'},data:{create:true}})).status()).toBe(403);expect(endpoints.filter(url=>['3000','8000'].includes(new URL(url).port))).toEqual([]);
 }finally{await context.close();}
});

import {test,expect} from '@playwright/test';
const API='http://localhost:8000';
for(const width of [1366,1920])test(`administrator temporary password remains isolated ${width}`,async({page,request})=>{
 const admin=await(await request.post(API+'/auth/admin/login',{data:{username:'admin1',password:'ValidationPass123'}})).json();
 const created=await(await request.post(API+'/admin/users',{headers:{Authorization:`Bearer ${admin.access_token}`},data:{username:`temp_${width}_${Date.now()}`,display_name:'临时管理员',role:'admin'}})).json();
 await page.setViewportSize({width,height:900});await page.addInitScript(()=>{localStorage.setItem('banfei:user:token','unchanged-ordinary-session');sessionStorage.setItem('lingjian:pending-tasks:residual',JSON.stringify([{id:'00000000-0000-0000-0000-000000000001',createdAt:'2026-09-01'}]));});
 const business:string[]=[];page.on('request',r=>{if(r.url().includes('/agent/tasks'))business.push(r.url());});
 await page.goto('/admin/login');await page.getByLabel('用户名',{exact:true}).fill(created.user.username);await page.getByLabel('密码',{exact:true}).fill(created.temporaryPassword);await page.getByRole('button',{name:'登录',exact:true}).click();
 await expect(page).toHaveURL(/\/admin\/change-password$/);await expect(page.locator('.sidebar')).toHaveCount(0);
 await page.getByLabel('当前密码',{exact:true}).fill(created.temporaryPassword);await page.getByLabel('新密码',{exact:true}).fill('NewAdminPass123');await page.getByLabel('确认新密码',{exact:true}).fill('NewAdminPass123');await page.getByRole('button',{name:'修改密码并进入'}).click();
 await expect(page).toHaveURL(/\/admin$/);expect(business).toHaveLength(0);expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token'))).toBe('unchanged-ordinary-session');
});

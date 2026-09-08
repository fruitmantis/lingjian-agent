import {test,expect} from '@playwright/test';
const API='http://127.0.0.1:8100';
for(const width of [1366,1920])test(`V1.2 no legacy assumption gate ${width}`,async({page,request})=>{
 const s=await (await request.post(API+'/auth/login',{data:{username:'user_a',password:'ValidationPass123'}})).json();
 await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},s);
 await page.setViewportSize({width,height:width===1366?768:1080});await page.goto('/enablement');
 await page.getByRole('button',{name:'生成能力发展建议',exact:true}).click();await expect(page.locator('main').getByRole('alert')).toContainText('请选择目标伙伴');
 await expect(page.getByTestId('clarification')).toHaveCount(0);await expect(page.getByText('我明确确认该项存在能力差距')).toHaveCount(0);
 await page.getByRole('link',{name:'资源中心',exact:true}).click();await expect(page.getByRole('tab',{name:'实验',exact:true})).toBeVisible();await expect(page.getByLabel('选择目标伙伴')).toHaveCount(0);
});

import {fixtureLogin} from "./identity-fixture";
import {test,expect} from '@playwright/test';
const API='http://localhost/api';
for(const width of [1366,1920])test(`V1.2 no legacy assumption gate ${width}`,async({page,request})=>{
 const s=await (await fixtureLogin(request, 'user_a', 'ValidationPass123')).json();
 await page.addInitScript(s=>{localStorage.setItem(`banfei:${s.user.role}:token`, s.access_token); localStorage.setItem(`banfei:${s.user.role}:user`, JSON.stringify(s.user));},s);
 await page.setViewportSize({width,height:width===1366?768:1080});await page.goto('/enablement');
 await page.getByRole('button',{name:'开始',exact:true}).click();await expect(page.locator('main').getByRole('region',{name:'任务未完成说明',exact:true})).toContainText('请描述发展需求');
 await expect(page.getByTestId('clarification')).toHaveCount(0);await expect(page.getByText('我明确确认该项存在能力差距')).toHaveCount(0);
 await page.getByRole('link',{name:'资源中心',exact:true}).click();await expect(page.getByRole('tab',{name:'实验',exact:true})).toBeVisible();await expect(page.getByLabel('关联已有伙伴资料（可选）',{exact:true})).toHaveCount(0);
});

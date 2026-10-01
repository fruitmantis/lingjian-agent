import {test,expect} from '@playwright/test';

const chapters=['公司概况','公司规模与收入情况','与头部科技企业（华为/阿里/字节）合作情况','华为认证与资质情况','AI技术能力与解决方案','重点行业案例','负向事件与合规风险排查','适合开展合作的领域建议','合作注意事项','数据来源与免责声明'];
const report=chapters.map((title,i)=>`## ${i+1}. ${title}\n\n来源日期2026-09-24；本公司口径，企业自述，待核实。\n\n${[0,3,5].includes(i)?'| 项目 | 信息 |\n| --- | --- |\n| 限定 | 本公司 \\| 未核验<br>现有资料未提供 |\n':''}`).join('\n');

for(const legacy of [false,true])test(`admin profile renders ${legacy?'legacy text':'ten chapters and tables'} safely`,async({page})=>{
  const unexpected:string[]=[];
  const injection='<script>window.profileInjected=1</script><img src="https://example.invalid/leak">';
  await page.addInitScript(()=>localStorage.setItem('banfei:admin:token','synthetic-ui-only'));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.hostname==='example.invalid'){unexpected.push(url.href);return route.abort();}
    if(url.port!=='8000'&&!url.pathname.startsWith('/api/'))return route.continue();
    const path=url.pathname.replace(/^\/api/,'');
    if(path==='/health')return route.fulfill({json:{status:'ok'}});
    if(path==='/auth/me')return route.fulfill({json:{id:'admin',role:'admin',status:'active',must_change_password:false}});
    if(path==='/partners/profile-ui')return route.fulfill({json:{id:'profile-ui',name:'合成伙伴',ai_profile:(legacy?'旧纯文本画像\n保留原有换行':report)+'\n\n'+injection,profile_needs_update:false}});
    if(path==='/admin/capability-tags'||path==='/partners/profile-ui/documents')return route.fulfill({json:[]});
    unexpected.push(path);return route.abort();
  });
  await page.goto('/admin/partners/profile-ui');
  const body=page.getByTestId('partner-profile-report');
  await expect(body).toBeVisible();
  if(legacy){await expect(body).toContainText('旧纯文本画像\n保留原有换行');await expect(body.locator('table')).toHaveCount(0);}
  else{
    await expect(body.getByRole('heading',{level:3})).toHaveCount(10);
    await expect(body.getByRole('table')).toHaveCount(3);
    await expect(body.getByRole('cell',{name:'本公司 | 未核验 现有资料未提供',exact:true})).toHaveCount(3);
    await page.screenshot({path:'/tmp/banfei-profile-report.png',fullPage:true});
  }
  await expect(body).toContainText(injection);
  await expect(body.locator('script,img,iframe,a')).toHaveCount(0);
  await page.getByText('画像原件',{exact:true}).click();
  await expect(page.getByText('导入 DOCX 画像',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'更新伙伴画像',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(unexpected).toEqual([]);
});

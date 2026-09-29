import {selectPartner} from './partner-select-helper';
import {test, expect, type Page} from '@playwright/test';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fixture, match, plan, partner} from './coze-fixtures';
import {createFontVerification} from './font-verification';

const phase = process.env.COZE_POLISH_PHASE || 'after';
const root = path.resolve(process.env.COZE_POLISH_EVIDENCE_DIR || '../artifacts/coze-polish');
const baseline = process.env.COZE_POLISH_BASELINE_DIR;

for (const [width, height] of [[1366,768], [1920,1080], [390,844]]) {
  test(`visual refinement and system fonts ${width}x${height}`, async ({page, context}) => {
    await page.setViewportSize({width,height});
    const typography=phase==='after' ? await createFontVerification(page) : null;
    const {requests, unexpected} = await fixture(page);
    const cdp = await context.newCDPSession(page);
    await cdp.send('DOM.enable'); await cdp.send('CSS.enable');
    await cdp.send('Network.setCacheDisabled', {cacheDisabled:true});
    await cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor:1});
    const errors:string[] = [], fontResponses:{url:string;status:number}[] = [], evidence:any[] = [];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('response', r=>{if(r.request().resourceType()==='font')fontResponses.push({url:r.url(),status:r.status()});});
    const directory = path.join(root, phase); await mkdir(directory, {recursive:true});
    async function rendered(selector:string) {
      // CDP reports immediate text nodes, so inspect a visible text leaf within the crop.
      await page.locator(selector).first().evaluate(root=>{
        const node=[root,...root.querySelectorAll('*')].find(e=>e.getBoundingClientRect().height && [...e.childNodes].some(n=>n.nodeType===Node.TEXT_NODE && /[\u3400-\u9fffA-Za-z0-9]/.test(n.textContent||'')));
        node?.setAttribute('data-rendered-font-check','true');
      });
      const {root:doc}=await cdp.send('DOM.getDocument');
      const {nodeId}=await cdp.send('DOM.querySelector', {nodeId:doc.nodeId,selector:'[data-rendered-font-check]'});
      const fonts=nodeId ? (await cdp.send('CSS.getPlatformFontsForNode', {nodeId})).fonts : [];
      await page.locator('[data-rendered-font-check]').evaluateAll(nodes=>nodes.forEach(n=>n.removeAttribute('data-rendered-font-check')));
      return fonts;
    }
    async function capture(name:string, crop?:string) {
      await page.evaluate(()=>document.fonts.ready);
      await page.addStyleTag({content:'nextjs-portal{display:none}'});
      await page.evaluate(()=>window.scrollTo(0,0));
      const measure=await page.evaluate(()=>({
        width:innerWidth, height:innerHeight, zoom:visualViewport?.scale,
        deviceScale:devicePixelRatio, scrollWidth:document.documentElement.scrollWidth,
        text:document.querySelector('main')?.textContent,
        controls:[...document.querySelectorAll('main input, main button, main select, main textarea')].map(e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return {tag:e.tagName,text:e.textContent?.trim().slice(0,25),width:r.width,height:r.height,fontSize:s.fontSize,fontWeight:s.fontWeight};}),
      }));
      expect(measure.zoom).toBe(1); expect(measure.deviceScale).toBe(1);
      if(phase==='after') {
        expect(measure.scrollWidth, `${name}: document overflow`).toBeLessThanOrEqual(width);
        if(baseline){
          const before=JSON.parse(await readFile(path.join(baseline,`${name}-${width}.json`),'utf8'));
          expect(measure.text, `${name}: content must stay identical`).toBe(before.text);
        }
      }
      await writeFile(path.join(directory,`${name}-${width}.json`),JSON.stringify(measure,null,2));
      const mask=[page.locator('.identity-key-value'),page.locator('input[type=password]')];
      await page.screenshot({path:path.join(directory,`${name}-${width}-viewport.png`),mask});
      await page.screenshot({path:path.join(directory,`${name}-${width}-full.png`),fullPage:true,mask});
      if(crop) {
        const target=page.locator(crop).first(); await expect(target).toBeVisible(); await target.screenshot({timeout:10000,path:path.join(directory,`${name}-${width}-detail.png`)});
        const actual=await rendered(crop); evidence.push({name,selector:crop,actual});
        if(phase==='after')expect(actual.some(f=>!f.isCustomFont),`${name}: actual system font`).toBeTruthy();
      }
    }
    await page.goto('/'); await expect(page.getByRole('tab',{name:'伙伴匹配',exact:true})).toHaveAttribute('aria-selected','true');
    await page.locator('#requirement').fill(match.requirement); await capture('01-home','.assistant-composer');
    await page.goto('/?mode=development'); await selectPartner(page, partner.id);
    await expect(page.getByText('当前伙伴画像摘要',{exact:true})).toBeVisible();
    await page.getByLabel('发展方向',{exact:true}).fill(plan.request.development_direction);await capture('02-development','.development-composer');
    await page.goto('/?task=coze-match'); await expect(page.getByRole('heading',{name:'本次项目需求'})).toBeVisible();
    await capture('03-home-result','.ui-match-result');
    await page.goto('/tasks/coze-plan');await expect(page.getByTestId('advisor-main-answer')).toContainText('小范围验证');
    await capture('04-answer','.advisor-answer-body');await capture('04-resource-card','.advisor-resource');
    await page.getByLabel('消息',{exact:true}).fill('先验证哪些环节？');
    await expect(page.getByRole('button',{name:'发送',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'发送',exact:true}).scrollIntoViewIfNeeded();
    await page.goto('/tasks/coze-match');await expect(page.getByText('风险或缺口',{exact:true})).toBeVisible();await capture('05-match','.recommendation-item');
    for(const type of ['course','lab','case']) {
      await page.goto(`/resources?resource_type=${type}`);await expect(page.locator('.enablement-resource-grid article')).toHaveCount(6);
      await capture(`06-resources-${type}`,'.enablement-resource-grid article');
    }
    await page.locator('.enablement-resource-card').first().getByRole('link',{name:'查看详情'}).click();
    await expect(page.locator('main')).toContainText('企业级 Agent');await capture('07-resource-detail','main .card');
    // Exercise shared table, fields, buttons and dialog styles on administration pages.
    const admin={id:'ui-admin',username:'ui-admin',display_name:'合成管理员',role:'admin',status:'active',must_change_password:false};
    await page.addInitScript(admin=>{localStorage.setItem('banfei:admin:token','synthetic-admin-only');localStorage.setItem('banfei:admin:user',JSON.stringify(admin));},admin);
    await page.route('**/auth/me',r=>r.fulfill({json:admin}));
    await page.route('**/admin/model-configs/timeout-settings',r=>r.fulfill({json:{timeoutSeconds:300,timeoutRetries:3}}));
    await page.route(/\/admin\/model-configs(?:\/usage)?$/,r=>r.fulfill({json: r.request().url().includes('/usage') ? [] : [{id:'synthetic-config',name:'界面验收配置',provider:'示例供应商',modelName:'example-model',maxTokens:8192,baseUrl:'https://example.com/v1',apiKeyConfigured:true,enabled:true,isDefault:true}]}));
    await page.goto('/admin/models');await expect(page.getByRole('button',{name:'编辑',exact:true})).toBeVisible();
    await capture('08-admin-models','.data-table');
    await page.getByRole('button',{name:'编辑',exact:true}).click();await expect(page.getByRole('button',{name:'取消',exact:true})).toBeVisible();
    await capture('09-admin-fields','.data-table');await page.getByRole('button',{name:'取消',exact:true}).click();
    await page.route(/\/admin\/users\?/,r=>r.fulfill({json:{items:[{...admin,id:'synthetic-other',username:'demo-admin',department:'合成部门',auth_methods:['password'],identity_key_hint:null,created_at:'2026-09-28T02:30:00Z',last_login_at:null,locked_until:null}],total:1,page:1}}));
    await page.goto('/admin/users');await expect(page.getByRole('button',{name:'编辑',exact:true})).toBeVisible();
    await capture('10-admin-users','.admin-users-table');await page.getByRole('button',{name:'编辑',exact:true}).click();
    await expect(page.locator('.modal-card')).toBeVisible();await capture('11-admin-dialog','.modal-card');await page.getByRole('button',{name:'取消',exact:true}).click();
    // Separate language/weight probes establish actual glyph fonts, not only font-family CSS.
    for(const weight of [400,500])for(const [kind,text] of Object.entries({chinese:'伙伴能力发展课程实验案例风险证据数据库迁移',latin:'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',digits:'0123456789'})) {
      await page.evaluate(async({weight,text})=>{const node=document.createElement('p');node.id='local-font-probe';node.textContent=text;node.style.cssText=`position:fixed;left:0;bottom:0;font: ${weight} 16px/26px var(--font-body)`;document.body.append(node);await document.fonts.ready;},{weight,text});
      const actual=await rendered('#local-font-probe');evidence.push({kind,weight,actual});
      if(phase==='after') {expect(actual).toHaveLength(1);expect(actual[0].isCustomFont).toBe(false);}
      await page.locator('#local-font-probe').evaluate(e=>e.remove());
    }
    if(typography){await typography.inspect('admin-users');await writeFile(path.join(directory,`shared-fonts-${width}.json`),JSON.stringify(typography.evidence(),null,2));}
    expect(unexpected,'All external origins blocked; no external font requests').toEqual([]);
    expect(errors).toEqual([]);expect(requests.filter(r=>r.method!=='GET')).toEqual([]);
    if(phase==='after')expect(fontResponses).toEqual([]);expect(fontResponses.every(r=>r.status===200 && ['localhost','127.0.0.1'].includes(new URL(r.url).hostname))).toBe(true);
    await writeFile(path.join(directory,`fonts-${width}.json`),JSON.stringify({externalOriginsBlocked:true,cacheDisabled:true,fontResponses,evidence},null,2));
  });
}

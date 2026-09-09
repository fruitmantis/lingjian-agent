import {test, expect, type Page} from "@playwright/test";
const user = {id:"ui-admin", username:"ui-admin", display_name:"测试管理员", role:"admin", status:"active", must_change_password:false};
const opportunity = {id:"opportunity-fixture", matchRecordId:"match-fixture", projectName:"合成验收：互联网医院云灾备项目", customerName:"合成客户", industry:"教育医疗", region:"上海,北京,广东", projectStage:"方案评估", supplyStatus:"partial", completenessScore:70, requirementText:"需要跨区域容灾，并结合现有系统制定实施方案。", businessNeeds:"保证业务连续性", technicalNeeds:"数据库容灾与恢复演练", deliveryNeeds:"实施与培训", qualificationRequirements:null, caseRequirements:"同类项目经验", onsiteRequirement:null, timelineRequirement:"未知", cloudPlatformPreference:"未知", matchedCapabilityTags:"数据库", unmatchedCapabilitySignals:"异地容灾经验待核实", recommendedPartnerNames:"合成验收伙伴", missingFields:"驻场要求", followUpQuestions:JSON.stringify(["是否需要驻场？"])};
async function fixture(page:Page) {
  const queries:URLSearchParams[]=[];
  await page.addInitScript(user=>{localStorage.setItem("token","isolated-ui");localStorage.setItem("user",JSON.stringify(user));},user);
  await page.route("**/*",async route=>{
    const url=new URL(route.request().url());
    if(!url.pathname.startsWith("/api/") && url.port!=="8000") return route.continue();
    expect(route.request().method()).toBe("GET");
    const path=url.pathname.replace(/^\/api/,"");
    if(path==="/auth/me") return route.fulfill({json:user});
    if(path==="/health") return route.fulfill({json:{status:"ok"}});
    if(path==="/admin/demand-profiles") return route.fulfill({json:{profiles:[]}});
    if(path==="/admin/opportunities") {queries.push(url.searchParams);return route.fulfill({json:[opportunity]});}
    return route.fulfill({status:404,json:{detail:"Unexpected isolated request"}});
  });
  return queries;
}
for (const width of [1366,1920]) test(`opportunity details and aligned compact filters ${width}`,async({page})=>{
  await page.setViewportSize({width,height:width===1366?768:1080});
  await fixture(page);await page.goto("/admin/opportunities");
  await expect(page.getByRole("heading",{name:"项目机会库",exact:true})).toHaveCount(1);
  await expect(page.getByRole("listbox")).toHaveCount(0);
  const detail=page.getByRole("button",{name:"详情",exact:true});await detail.click();
  const region=page.getByRole("region",{name:"项目详情"});await expect(region).toBeVisible();
  await expect(region).toContainText(opportunity.requirementText);await expect(region).toContainText(opportunity.technicalNeeds);
  await expect(region).toContainText("是否需要驻场？");
  await expect(region.locator("div").filter({has:page.locator("dt",{hasText:"资质要求"})})).toContainText("未知");
  await expect(region.getByRole("link",{name:"查看原始匹配任务"})).toHaveAttribute("href","/tasks/match-fixture");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const search=await page.getByRole("searchbox").boundingBox();
  const industry=await page.getByLabel("行业筛选").boundingBox();
  expect(Math.abs(search!.y-industry!.y)).toBeLessThan(2);expect(Math.abs(search!.height-industry!.height)).toBeLessThan(2);
  if(process.env.OPPORTUNITY_SCREENSHOTS)await page.screenshot({path:`${process.env.OPPORTUNITY_SCREENSHOTS}/opportunity-${width}.png`,fullPage:true});
  await page.getByRole("button",{name:"收起",exact:true}).click();await expect(region).toHaveCount(0);
});
test("industry and region allow multiple choices, close with Escape, and reset",async({page})=>{
 const queries=await fixture(page);await page.goto("/admin/opportunities");
 await page.getByLabel("行业筛选").click();await page.getByRole("checkbox",{name:"金融",exact:true}).check();await page.getByRole("checkbox",{name:"互联网",exact:true}).check();
 await expect.poll(()=>queries.at(-1)?.get("industry")).toBe("金融,互联网");
 await page.keyboard.press("Escape");await expect(page.getByRole("group",{name:"行业选项"})).toBeHidden();
 await page.getByLabel("区域筛选").click();await page.getByRole("checkbox",{name:"广东",exact:true}).check();await page.getByRole("checkbox",{name:"亚太",exact:true}).check();
 await expect.poll(()=>queries.at(-1)?.get("region")).toBe("广东,亚太");
 await page.keyboard.press("Escape");await page.getByRole("searchbox").fill("容灾");
 await page.getByLabel("项目阶段",{exact:true}).fill("评估");
 await expect.poll(()=>queries.at(-1)?.get("stage")).toBe("评估");
 await page.getByRole("button",{name:"重置",exact:true}).click();await expect.poll(()=>queries.at(-1)?.toString()).toBe("");
 await expect(page.getByRole("searchbox")).toHaveValue("");await expect(page.getByLabel("行业筛选")).toContainText("全部行业");
});

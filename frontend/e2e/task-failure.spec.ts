import {test,expect,type Page} from "@playwright/test";
const stamp="2026-09-09T08:00:00Z";
const user={id:"fixture-user",username:"fixture",display_name:"验收用户",department:"测试",role:"user",status:"active",must_change_password:false,created_at:stamp};
const reason={stage:"project_opportunity",stageLabel:"项目机会",code:"timeout",message:"模型响应超时，本次处理未完成",action:"稍后重试"};
const presentation={state:"available",current_version:1,current_available:true,latest_run_status:"failed",latest_run_type:"revise"};
const summary={id:"partial-fixture",requirement:"合成验收：部分完成",task_type:"partner_match",taskStatus:"partial",lastErrorStage:"project_opportunity",failureDetails:[reason],topPartner:"合成伙伴",partnerCount:1,createdAt:stamp,archivedAt:null,ownerName:"验收用户",department:"测试",completenessScore:null};
async function fixture(page:Page){
 await page.addInitScript(({user})=>{localStorage.setItem(`banfei:${user.role}:token`, "isolated-fixture"); localStorage.setItem(`banfei:${user.role}:user`, JSON.stringify(user));},{user});
 const writes:{path:string;body:Record<string,unknown>}[]=[];
 await page.route("**/*",async route=>{
  const request=route.request(),url=new URL(request.url());
  if(!url.pathname.startsWith("/api/") && url.port!=="8000")return route.continue();
  const path=url.pathname.replace(/^\/api/,"");
  if(request.method()!=="GET"){writes.push({path,body:request.postDataJSON()||{}});return route.fulfill({status:202,json:{plan_id:"plan-fixture",run_id:"retry-fixture",replayed:false}});}
  let json:unknown={};
  if(path==="/auth/me")json=user;
  else if(path==="/health")json={status:"ok"};
  else if(path==="/agent/tasks")json={items:[summary,{...summary,id:"legacy-fixture",requirement:"合成验收：历史失败",taskStatus:"failed",failureDetails:[],partnerCount:0},{...summary,id:"plan-fixture",requirement:"合成验收：旧建议可用",task_type:"development_plan",planPresentation:presentation,taskStatus:"failed"}],page:1,pageSize:20,total:3,totalPages:1};
  else if(path==="/agent/tasks/failed-fixture")json={...summary,id:"failed-fixture",taskStatus:"failed",lastErrorStage:"partner_match",failureDetails:[{...reason,stage:"partner_match",stageLabel:"伙伴匹配",code:"authentication",message:"模型服务认证失败",action:"联系管理员检查模型访问凭据"}],recommendations:[],demandProfile:null,opportunity:null};
  else if(path.startsWith("/agent/tasks/"))json={...summary,id:path.split("/").pop(),task_type:path.endsWith("plan-fixture")?"development_plan":"partner_match",recommendations:[{partnerId:"fixture-partner",partnerName:"合成伙伴",matchScore:"80",matchedCapabilities:"测试",matchedIndustries:"金融",matchedRegions:"广东",recommendationReason:"仅限隔离验收",evidenceCases:"",evidenceDeliverables:"",riskNotes:""}],demandProfile:null,opportunity:null};
  else if(path==="/development/plans/plan-fixture")json={presentation,plan:{id:"plan-fixture",current_version_id:"v1",status:"active",active_run_id:null},partner_name:"合成伙伴",request:{development_direction:"合成验收方向"},conversation:[],payload:{overview:{development_direction:"合成验收方向"},stages:[],limitations:[],resource_gaps:[]},hidden:false,notice:null,versions:[{id:"v1",version_no:1}],runs:[{id:"failed-run",run_type:"revise",status:"failed",created_at:stamp,safe_error_message:reason.message}],failureDetails:[{...reason,stage:"generation",stageLabel:"建议生成"}]};
  else return route.fulfill({status:404,json:{detail:"Unexpected fixture request"}});
  return route.fulfill({json});
 });
 return writes;
}

test("ordinary list shows simple messages including legacy failures",async({page})=>{
 await fixture(page);await page.goto("/tasks");
 const row=page.getByRole("row").filter({hasText:"合成验收：部分完成"});
 await expect(row).toContainText("本次处理失败，请重试。");
 await expect(row).not.toContainText("模型响应超时");
 await expect(row.getByRole("link",{name:"查看任务",exact:true})).toHaveAttribute("href","/tasks/partial-fixture");
 await expect(page.getByRole("row").filter({hasText:"合成验收：历史失败"})).toContainText("本次处理失败，请重试。");
 await expect(page.getByRole("button",{name:"查看原因"})).toHaveCount(0);
});

for(const width of [1366,1920])test(`partial and failed revise preserve useful results at ${width}`,async({page})=>{
 await page.setViewportSize({width,height:width===1366?768:1080});const writes=await fixture(page);
 await page.goto("/tasks/partial-fixture");const notice=page.getByRole("region",{name:"任务未完成说明"});
 await expect(notice).toContainText("已保存的伙伴推荐可继续查看");await expect(notice).toContainText("本次处理失败，请重试。");await expect(notice).not.toContainText("模型响应超时");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 if(process.env.TASK_FAILURE_SCREENSHOTS)await page.screenshot({path:`${process.env.TASK_FAILURE_SCREENSHOTS}/partial-${width}.png`});
 await page.goto("/tasks/plan-fixture");await expect(page.getByRole("heading",{name:"能力发展建议",exact:true})).toBeVisible();
 await expect(page.getByTestId("advisor-status")).toContainText("建议可用");await expect(page.getByTestId("advisor-run-notice")).toContainText("未生成新版本");
 await page.getByTestId("advisor-run-notice").getByRole("button",{name:"重试",exact:true}).click();
 await expect.poll(()=>writes.length).toBe(1);expect(writes[0].path).toBe("/development/plans/plan-fixture/retry");expect(writes[0].body.based_on_version_id).toBe("v1");expect(writes[0].body.run_id).toBe("failed-run");
 await expect(page.getByTestId("advisor-status")).toContainText("建议可用");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 if(process.env.TASK_FAILURE_SCREENSHOTS)await page.screenshot({path:`${process.env.TASK_FAILURE_SCREENSHOTS}/failed-revise-${width}.png`});
});


test("configuration failure asks for admin without technical detail",async({page})=>{
 await fixture(page);await page.goto("/tasks/failed-fixture");
 const notice=page.getByRole("region",{name:"任务未完成说明"});
 await expect(notice).toContainText("服务异常，请联系管理员。");
 await expect(notice).not.toContainText("模型服务认证失败");
 await expect(notice).toContainText("项目需求已保留");
 await expect(notice).not.toContainText("伙伴推荐可用");
});

test("failed refresh preserves existing development advice",async({page})=>{
 await fixture(page);await page.goto("/tasks/plan-fixture");
 await expect(page.getByRole("heading",{name:"能力发展建议",exact:true})).toBeVisible();
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({status:503,json:{detail:"synthetic internal failure"}}));
 await expect(page.locator(".advisor-detail").getByRole("alert")).toHaveText("服务异常，请联系管理员。");
 await expect(page.getByRole("heading",{name:"能力发展建议",exact:true})).toBeVisible();
 await expect(page.getByTestId("advisor-status")).toContainText("建议可用");
 await expect(page.locator("body")).not.toContainText("synthetic internal failure");
});

test("empty match is a normal outcome",async({page})=>{
 await fixture(page);
 await page.route("**/agent/tasks/empty-fixture",route=>route.fulfill({json:{...summary,id:"empty-fixture",taskStatus:"ready",failureDetails:[],recommendations:[],demandProfile:null,opportunity:null}}));
 await page.goto("/tasks/empty-fixture");
 await expect(page.getByText("没有匹配项，可调整需求后重新匹配。")).toBeVisible();
 await expect(page.getByRole("region",{name:"任务未完成说明"})).toHaveCount(0);
});

test("unconfirmed submission uses simple wording and keeps pending task",async({page})=>{
 await fixture(page);
 await page.route("**/agent/tasks",route=>route.request().method()==="POST"?route.abort():route.fallback());
 await page.route(/\/agent\/tasks\/[a-f0-9-]{36}$/,route=>route.fulfill({status:404,json:{detail:"not yet confirmed"}}));
 await page.goto("/");
 await page.getByPlaceholder(/例如：寻找/).fill("隔离验证需求");
 await page.getByRole("button",{name:/开始匹配|匹配伙伴|开始分析/}).click();
 await expect(page.getByText("暂未确认结果，请刷新查看。",{exact:true})).toBeVisible();
 await expect(page.getByRole("button",{name:"核对任务"})).toBeVisible();
});

test("admin recent errors expand and copy redacted details",async({page,context})=>{
 const admin={...user,id:"fixture-admin",role:"admin"};
 await page.addInitScript(({admin})=>{localStorage.setItem("banfei:admin:token","isolated-admin");localStorage.setItem("banfei:admin:user",JSON.stringify(admin));},{admin});
 const latest={id:"error-latest",time:"2026-09-25T01:02:00Z",request_id:"req-2",task_id:"task-2",run_id:null,stage:"partner_match",exception_type:"ValueError",message:"推荐第 1 项 matchScore 无法解析为数字 <script>alert(1)</script>",model:"test-model",http_status:200,response_excerpt:'{"api_key":"[REDACTED]","matchScore":"92分"}',traceback:"File match.py: parse\nValueError: invalid matchScore"};
 await page.route("**/*",route=>{
  const url=new URL(route.request().url());if(!url.pathname.startsWith("/api/")&&url.port!=="8000")return route.continue();
  const path=url.pathname.replace(/^\/api/,"");
  if(path==="/auth/me")return route.fulfill({json:admin});
  if(path==="/health")return route.fulfill({json:{status:"ok"}});
  if(path==="/admin/system/errors")return route.fulfill({json:{items:[latest,{...latest,id:"error-older",time:"2026-09-25T01:01:00Z",task_id:null,request_id:"req-1",message:"database is unavailable",stage:"submission"}]}});
  if(path==="/admin/system/status")return route.fulfill({json:{overallStatus:"unknown",checkedAt:stamp,summary:{normalCount:0,warningCount:0,errorCount:0,unknownCount:0,abnormalModules:[]},services:[],database:[],llm:[],businessCapabilities:[],recentErrors:[]}});
  return route.fulfill({status:404,json:{detail:"Fixture route not defined"}});
 });
 await context.grantPermissions(["clipboard-read","clipboard-write"]);
 await page.goto("/admin/system");
 const panel=page.getByRole("region",{name:"最近错误"});
 const entries=panel.locator("details");await expect(entries).toHaveCount(2);
 await expect(entries.first()).toContainText("matchScore 无法解析为数字");
 await expect(entries.first().getByLabel("错误完整详情")).toBeHidden();
 await entries.first().locator("summary").click();
 const detail=entries.first().getByLabel("错误完整详情");
 await expect(detail).toContainText("task-2");await expect(detail).toContainText("test-model");await expect(detail).toContainText("HTTP 状态码：200");await expect(detail).toContainText("[REDACTED]");
 await entries.first().getByRole("button",{name:"复制错误详情"}).click();
 await expect(panel.getByRole("status")).toContainText("已复制错误详情");
 expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(await detail.textContent());
 await entries.nth(1).locator("summary").click();await expect(entries.nth(1)).toContainText("请求 req-1");
 for(const width of [1366,390]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();if(process.env.TASK_FAILURE_SCREENSHOTS)await page.screenshot({path:`${process.env.TASK_FAILURE_SCREENSHOTS}/admin-errors-${width}.png`,fullPage:true});}
});

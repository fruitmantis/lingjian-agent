import {test,expect,type Page} from "@playwright/test";
const stamp="2026-09-09T08:00:00Z";
const user={id:"fixture-user",username:"fixture",display_name:"验收用户",department:"测试",role:"user",status:"active",must_change_password:false,created_at:stamp};
const reason={stage:"project_opportunity",stageLabel:"项目机会",code:"timeout",message:"模型响应超时，本次处理未完成",action:"稍后重试"};
const presentation={state:"available",current_version:1,current_available:true,latest_run_status:"failed",latest_run_type:"revise"};
const summary={id:"partial-fixture",requirement:"合成验收：部分完成",task_type:"partner_match",taskStatus:"partial",lastErrorStage:"project_opportunity",failureDetails:[reason],topPartner:"合成伙伴",partnerCount:1,createdAt:stamp,archivedAt:null,ownerName:"验收用户",department:"测试",completenessScore:null};
const developmentDetail={presentation,plan:{id:"plan-fixture",current_version_id:"v1",status:"active",active_run_id:null},partner_name:"合成伙伴",request:{development_direction:"合成验收方向"},conversation:[],payload:{overview:{development_direction:"合成验收方向"},stages:[],limitations:[],resource_gaps:[]},hidden:false,notice:null,versions:[{id:"v1",version_no:1}],runs:[{id:"failed-run",run_type:"revise",status:"failed",created_at:stamp,safe_error_message:reason.message}],failureDetails:[{...reason,stage:"generation",stageLabel:"建议生成"}]};
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
  else if(path==="/model-timeout-settings")json={timeoutSeconds:300,timeoutRetries:3};
  else if(path==="/agent/tasks")json={items:[summary,{...summary,id:"legacy-fixture",requirement:"合成验收：历史失败",taskStatus:"failed",failureDetails:[],partnerCount:0},{...summary,id:"plan-fixture",requirement:"合成验收：旧建议可用",task_type:"development_plan",planPresentation:presentation,taskStatus:"failed"}],page:1,pageSize:20,total:3,totalPages:1};
  else if(path==="/agent/tasks/failed-fixture")json={...summary,id:"failed-fixture",taskStatus:"failed",lastErrorStage:"partner_match",failureDetails:[{...reason,stage:"partner_match",stageLabel:"伙伴匹配",code:"authentication",message:"模型服务认证失败",action:"联系管理员检查模型访问凭据"}],recommendations:[],demandProfile:null,opportunity:null};
  else if(path.startsWith("/agent/tasks/"))json={...summary,id:path.split("/").pop(),task_type:path.endsWith("plan-fixture")?"development_plan":"partner_match",recommendations:[{partnerId:"fixture-partner",partnerName:"合成伙伴",matchScore:"80",matchedCapabilities:"测试",matchedIndustries:"金融",matchedRegions:"广东",recommendationReason:"仅限隔离验收",evidenceCases:"",evidenceDeliverables:"",riskNotes:""}],demandProfile:null,opportunity:null};
  else if(path==="/development/plans/plan-fixture")json=developmentDetail;
  else return route.fulfill({status:404,json:{detail:"Unexpected fixture request"}});
  return route.fulfill({json});
 });
 return writes;
}

test("ordinary list shows simple messages including legacy failures",async({page})=>{
 await fixture(page);await page.goto("/tasks");
 await expect(page.getByRole("button",{name:"任务报错",exact:true})).toHaveCount(0);
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
 await expect(page.getByTestId("advisor-status")).toContainText("建议可用");await expect(page.getByTestId("advisor-run-notice")).toContainText("本次调整失败，请重试。");
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

for(const outcome of ["disconnect","commit-error"])test(`uncertain ${outcome} uses simple wording and keeps original pending task`,async({page})=>{
 await fixture(page);
 let posts=0;
 await page.route("**/agent/tasks",route=>{if(route.request().method()!=="POST")return route.fallback();posts++;return outcome==="disconnect"?route.abort():route.fulfill({status:500,json:{detail:"synthetic commit failure"}});});
 await page.route(/\/agent\/tasks\/[a-f0-9-]{36}$/,route=>route.fulfill({status:404,json:{detail:"not yet confirmed"}}));
 await page.goto("/");
 await page.getByPlaceholder(/例如：寻找/).fill("隔离验证需求");
 await page.getByRole("button",{name:/开始|匹配伙伴|开始分析/}).click();
 await expect(page.getByText("暂未确认结果，请刷新查看。",{exact:true})).toBeVisible();
 const navigation=page.getByRole("button",{name:"展开导航",exact:true});
 if(await navigation.isVisible())await navigation.click();
 await expect(page.getByRole("button",{name:"刷新查看"})).toBeVisible();
 await page.getByRole("button",{name:"刷新查看"}).click();
 expect(posts).toBe(1);
 await expect(page.locator("body")).not.toContainText(/提交未确认|核对任务/);
});

for(const status of [202,502,500])test(`accepted matching timeout recovers original task after HTTP ${status}`,async({page})=>{
 await fixture(page);let identifier="",posts=0,retries=0;
 const failed=()=>({...summary,id:identifier,taskStatus:"failed",failureDetails:[{...reason,stage:"understanding"}],recommendations:[],demandProfile:null,opportunity:null});
 await page.route("**/agent/tasks",route=>{if(route.request().method()!=="POST")return route.fallback();posts++;identifier=route.request().postDataJSON().requestId;return route.fulfill({status,json:status===202?{recordId:identifier,taskStatus:"failed"}:{detail:"本次处理失败，请重试。",...(status===502?{failureCode:"timeout"}:{})}});});
 await page.route(/\/agent\/tasks\/[a-f0-9-]{36}$/,route=>route.fulfill({json:failed()}));
 await page.route(/\/agent\/tasks\/[a-f0-9-]{36}\/retry$/,route=>{retries++;expect(route.request().url()).toContain(identifier);return route.fulfill({status:502,json:{detail:"本次处理失败，请重试。",failureCode:"timeout"}});});
 await page.goto("/");
 await page.getByPlaceholder(/例如：寻找/).fill("合成超时恢复需求");
 await page.getByRole("button",{name:/开始|匹配伙伴|开始分析/}).click();
 // Recovery now navigates automatically; do not race its transient home-page link.
 await expect(page).toHaveURL(new RegExp(`/tasks/${identifier}$`));
 const selected=page.locator(`.sidebar-task-item[data-task-id="${identifier}"]`);
 await expect(selected).toHaveAttribute("aria-current","page");
 await expect(selected).toContainText("生成失败，可重试");
 await expect(page.locator(".pending-task")).toHaveCount(0);
 expect(await page.evaluate(()=>sessionStorage.getItem("lingjian:pending-tasks:fixture-user"))).toBe("[]");
 page.on("dialog",dialog=>dialog.accept());
 await page.getByRole("button",{name:"重试",exact:true}).click();
 await expect.poll(()=>retries).toBe(1);
 await expect(page.getByRole("region",{name:"任务未完成说明"})).toContainText("项目需求已保留");
 await expect(page.locator("body")).not.toContainText(/提交未确认|核对任务/);
 expect(posts).toBe(1);
});

test("restored pending matching task resolves failed record without another submission",async({page})=>{
 const writes=await fixture(page),id="00000000-0000-4000-8000-000000000001";
 await page.addInitScript(({id,stamp})=>sessionStorage.setItem("lingjian:pending-tasks:fixture-user",JSON.stringify([{id,createdAt:stamp}])),{id,stamp});
 await page.route(`**/agent/tasks/${id}`,route=>route.fulfill({json:{...summary,id,taskStatus:"failed",recommendations:[],demandProfile:null,opportunity:null}}));
 await page.goto(`/tasks/${id}`);
 await expect(page.getByRole("button",{name:"重试",exact:true})).toBeEnabled();
 await expect.poll(()=>page.evaluate(()=>sessionStorage.getItem("lingjian:pending-tasks:fixture-user"))).toBe("[]");
 await expect(page.locator("body")).not.toContainText(/提交未确认|核对任务/);
 expect(writes).toHaveLength(0);
});

test("accepted development timeout opens the saved failed plan with retry available",async({page})=>{
 await fixture(page);let posts=0;
 await page.route("**/partners",route=>route.fulfill({json:[{id:"fixture-partner",name:"合成伙伴"}]}));
 await page.route("**/enablement/context?**",route=>route.fulfill({json:{partner:null,source_task:null,shared_case:null,evidence:[]}}));
 await page.route("**/development/plans",route=>{posts++;return route.fulfill({status:202,json:{plan_id:"plan-fixture",run_id:"failed-run",status:"failed"}});});
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({json:{...developmentDetail,plan:{...developmentDetail.plan,current_version_id:null},presentation:{...presentation,current_available:false},payload:null,runs:[{...developmentDetail.runs[0],run_type:"generate"}]}}));
 await page.goto("/?mode=development&partner_id=fixture-partner");
 await page.getByLabel("发展方向",{exact:true}).fill("合成发展诉求");
 await page.getByRole("button",{name:"开始",exact:true}).click();
 await expect(page).toHaveURL(/tasks\/plan-fixture/);
 await expect(page.getByTestId("advisor-status")).toContainText("生成失败，可重试");
 await expect(page.getByRole("button",{name:"重试",exact:true})).toBeEnabled();
 expect(await page.evaluate(()=>sessionStorage.getItem("development:pending-create:fixture-user:fixture-partner"))).toBeNull();
 expect(posts).toBe(1);
});

test("failed development task clears old pending marker and retries same plan only once",async({page})=>{
 await fixture(page);
 const key="development:pending:fixture-user:plan-fixture";
 await page.addInitScript(key=>sessionStorage.setItem(key,"legacy-unresolved-request"),key);
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({json:{...developmentDetail,plan:{...developmentDetail.plan,current_version_id:null},presentation:{...presentation,current_available:false},payload:null,runs:[{...developmentDetail.runs[0],run_type:"generate",submission_id:"original-failed-submission"}]}}));
 let release:()=>void=()=>{},posts=0;
 const response=new Promise<void>(resolve=>release=resolve);
 await page.route("**/development/plans/plan-fixture/retry",async route=>{posts++;expect(route.request().postDataJSON()).toMatchObject({run_id:"failed-run",based_on_version_id:null});await response;await route.fulfill({status:202,json:{plan_id:"plan-fixture",run_id:"retry-run",status:"failed"}});});
 await page.goto("/tasks/plan-fixture");
 await expect(page.getByTestId("advisor-status")).toContainText("生成失败，可重试");
 await expect(page.getByRole("button",{name:"重试",exact:true})).toBeEnabled();
 expect(await page.evaluate(key=>sessionStorage.getItem(key),key)).toBeNull();
 await page.getByRole("button",{name:"重试",exact:true}).click();
 await page.waitForResponse(r=>r.url().endsWith("/development/plans/plan-fixture")&&r.request().method()==="GET");
 // A poll of the old failed Run must not clear the request still in flight.
 expect(await page.evaluate(key=>sessionStorage.getItem(key),key)).toBeTruthy();
 await expect(page.getByRole("button",{name:"重试",exact:true})).toBeDisabled();
 release();
 await expect(page.getByRole("button",{name:"重试",exact:true})).toBeEnabled();
 await expect(page.locator("body")).not.toContainText(/提交未确认|核对任务/);
 expect(posts).toBe(1);
});

test("admin task errors tab expands and copies redacted details",async({page,context})=>{
 const admin={...user,id:"fixture-admin",role:"admin"};
 await page.addInitScript(({admin})=>{localStorage.setItem("banfei:admin:token","isolated-admin");localStorage.setItem("banfei:admin:user",JSON.stringify(admin));},{admin});
 const latest={id:"error-latest",time:"2026-09-25T01:02:00Z",request_id:"req-2",task_id:"task-2",run_id:null,stage:"partner_match",exception_type:"ValueError",message:"推荐第 1 项 matchScore 无法解析为数字 <script>alert(1)</script>",model:"test-model",http_status:200,response_excerpt:'{"api_key":"[REDACTED]","matchScore":"92分"}',traceback:"File match.py: parse\nValueError: invalid matchScore"};
 await page.route("**/*",route=>{
  const url=new URL(route.request().url());if(!url.pathname.startsWith("/api/")&&url.port!=="8000")return route.continue();
  const path=url.pathname.replace(/^\/api/,"");
  if(path==="/auth/me")return route.fulfill({json:admin});
  if(path==="/health")return route.fulfill({json:{status:"ok"}});
  if(path==="/admin/tasks")return route.fulfill({json:{items:[],page:1,pageSize:20,total:0,totalPages:0}});
  if(path==="/admin/system/errors")return route.fulfill({json:{items:[latest,{...latest,id:"error-older",time:"2026-09-25T01:01:00Z",task_id:null,request_id:"req-1",message:"database is unavailable",stage:"submission"}]}});
  if(path==="/admin/system/status")return route.fulfill({json:{overallStatus:"unknown",checkedAt:stamp,summary:{normalCount:0,warningCount:0,errorCount:0,unknownCount:0,abnormalModules:[]},services:[],database:[],llm:[],businessCapabilities:[],recentErrors:[]}});
  return route.fulfill({status:404,json:{detail:"Fixture route not defined"}});
 });
 await context.grantPermissions(["clipboard-read","clipboard-write"]);
 await page.goto("/admin/system");
 await expect(page.getByRole("heading",{name:"系统状态",exact:true})).toBeVisible();
 await expect(page.getByRole("region",{name:"最近错误",exact:true})).toContainText(latest.message);
 await page.goto("/admin/tasks");
 await expect(page.getByRole("button",{name:"进行中",exact:true})).toHaveAttribute("aria-pressed","true");
 await page.getByRole("button",{name:"已归档",exact:true}).click();
 await expect(page.getByRole("heading",{name:"暂无已归档任务"})).toBeVisible();
 await page.getByRole("button",{name:"任务报错",exact:true}).click();
 await expect(page.getByRole("button",{name:"任务报错",exact:true})).toHaveAttribute("aria-pressed","true");
 await expect(page.getByRole("button",{name:"已归档",exact:true})).toHaveAttribute("aria-pressed","false");
 await expect(page.getByPlaceholder("搜索需求内容")).toHaveCount(0);
 const panel=page.getByRole("region",{name:"任务报错"});
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
 await page.getByRole("button",{name:"进行中",exact:true}).click();
 await expect(panel).toHaveCount(0);
 await expect(page.getByPlaceholder("搜索需求内容")).toBeVisible();
 await expect(page.getByRole("heading",{name:"暂无任务",exact:true})).toBeVisible();
});


test("development service failure has no retry and no false usable advice claim",async({page})=>{
 await fixture(page);
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({json:{...developmentDetail,presentation:{...presentation,current_available:false},hidden:true,payload:null,failureDetails:[{...reason,code:"configuration"}]}}));
 await page.goto("/tasks/plan-fixture");
 const notice=page.getByTestId("advisor-run-notice");
 await expect(notice).toContainText("服务异常，请联系管理员。");
 await expect(notice).toContainText("发展诉求已保留。");
 await expect(notice).not.toContainText("当前建议仍可使用");
 await expect(notice.getByRole("button",{name:"重试",exact:true})).toHaveCount(0);
});

test("initial generation failure preserves request without claiming old advice",async({page})=>{
 await fixture(page);
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({json:{...developmentDetail,plan:{...developmentDetail.plan,current_version_id:null},presentation:{...presentation,current_available:false},payload:null,runs:[{...developmentDetail.runs[0],run_type:"generate"}]}}));
 await page.goto("/tasks/plan-fixture");
 const notice=page.getByTestId("advisor-run-notice");
 await expect(notice).toContainText("本次建议未生成，请重试。");
 await expect(notice).toContainText("发展诉求已保留。");
 await expect(notice).not.toContainText("当前建议仍可使用");
 await expect(page.getByRole("button",{name:"重试",exact:true})).toHaveCount(1);
 await expect(page.getByRole("button",{name:"重新生成",exact:true})).toHaveCount(0);
});

test("answer failure survives polling and can retry only after response ends",async({page})=>{
 const writes=await fixture(page);
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({json:{...developmentDetail,runs:[],failureDetails:[]}}));
 let release:()=>void=()=>{};
 const response=new Promise<void>(resolve=>release=resolve);
 await page.route("**/development/plans/plan-fixture/conversation",async route=>{await response;await route.fulfill({status:422,json:{detail:"本次处理失败，请重试。"}});});
 await page.goto("/tasks/plan-fixture");
 await page.getByLabel("消息",{exact:true}).fill("请解释推荐依据");
 await page.getByRole("button",{name:"发送",exact:true}).click();
 await expect(page.getByRole("button",{name:"正在回复…",exact:true})).toBeDisabled();
 await expect(page.getByRole("button",{name:"重试",exact:true})).toHaveCount(0);
 release();
 const notice=page.getByRole("region",{name:"任务未完成说明"});
 await expect(notice).toContainText("本次回答失败，请重试。");
 await expect(notice).toContainText("当前建议仍可使用。");
 await expect(notice).not.toContainText("发展诉求已保留");
 await page.waitForResponse(r=>r.url().includes('/development/plans/plan-fixture')&&r.request().method()==='GET');
 await expect(notice).toContainText("本次回答失败，请重试。");
 await expect(notice.getByRole("button",{name:"重试",exact:true})).toBeEnabled();
 expect(writes).toHaveLength(0);
});

test("lost development retry response only queries original run even after reload",async({page})=>{
 await fixture(page);let posts=0,submission="",confirmed=false;
 await page.route("**/development/plans/plan-fixture/retry",route=>{posts++;submission=route.request().postDataJSON().submission_id;return route.abort();});
 await page.route("**/development/plans/plan-fixture",route=>route.fulfill({json:confirmed?{...developmentDetail,plan:{...developmentDetail.plan,active_run_id:"original-run"},runs:[{...developmentDetail.runs[0],id:"original-run",submission_id:submission,status:"running"}],failureDetails:[]}:developmentDetail}));
 await page.goto("/tasks/plan-fixture");
 await page.getByRole("button",{name:"重试",exact:true}).click();
 await expect(page.getByText("暂未确认结果，请刷新查看。",{exact:true})).toBeVisible();
 await page.reload();
 await expect(page.getByRole("button",{name:"刷新查看",exact:true})).toBeVisible();
 await expect(page.getByRole("button",{name:"重试",exact:true})).toHaveCount(0);
 confirmed=true;
 await page.getByRole("button",{name:"刷新查看",exact:true}).click();
 await expect(page.getByText("伴飞正在整理建议，你可以继续查看已有内容。",{exact:true})).toBeVisible();
 await expect(page.getByText("暂未确认结果，请刷新查看。",{exact:true})).toHaveCount(0);
 expect(posts).toBe(1);
});

test("lost create response queries submission and never claims the demand was saved",async({page})=>{
 await fixture(page);let posts=0,submission="",found=false;
 await page.route("**/partners",route=>route.fulfill({json:[{id:"fixture-partner",name:"合成伙伴"}]}));
 await page.route("**/enablement/context?**",route=>route.fulfill({json:{partner:null,source_task:null,shared_case:null,evidence:[]}}));
 await page.route("**/development/plans",route=>{posts++;submission=route.request().postDataJSON().submission_id;return route.abort();});
 await page.route("**/development/submissions/*",route=>{expect(route.request().url()).toContain(submission);return found?route.fulfill({json:{plan_id:"plan-fixture",status:"pending"}}):route.fulfill({status:404,json:{detail:"暂未确认结果，请刷新查看。"}});});
 await page.goto("/?mode=development&partner_id=fixture-partner");
 await page.getByLabel("发展方向",{exact:true}).fill("合成发展诉求");
 await page.getByRole("button",{name:"开始",exact:true}).click();
 const notice=page.getByRole("region",{name:"任务未完成说明"});
 await expect(notice).toContainText("暂未确认结果，请刷新查看。");
 await expect(notice).not.toContainText("发展诉求已保留");
 await page.reload();
 await expect(page.getByRole("button",{name:"开始",exact:true})).toBeDisabled();
 await page.getByRole("button",{name:"刷新查看",exact:true}).click();
 await expect(notice).toContainText("暂未确认结果，请刷新查看。");
 found=true;
 await page.getByRole("button",{name:"刷新查看",exact:true}).click();
 await expect(page).toHaveURL(/tasks\/plan-fixture/);
 expect(posts).toBe(1);
});

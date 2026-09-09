import {test,expect,type Page} from "@playwright/test";
const stamp="2026-09-09T08:00:00Z";
const user={id:"fixture-user",username:"fixture",display_name:"验收用户",department:"测试",role:"user",status:"active",must_change_password:false,created_at:stamp};
const reason={stage:"project_opportunity",stageLabel:"项目机会",code:"timeout",message:"模型响应超时，本次处理未完成",action:"稍后重试"};
const presentation={state:"available",current_version:1,confirmed_version:1,current_is_confirmed:true,current_available:true,confirmed_available:true,latest_run_status:"failed",latest_run_type:"revise"};
const summary={id:"partial-fixture",requirement:"合成验收：部分完成",task_type:"partner_match",taskStatus:"partial",lastErrorStage:"project_opportunity",failureDetails:[reason],topPartner:"合成伙伴",partnerCount:1,createdAt:stamp,archivedAt:null,ownerName:"验收用户",department:"测试",completenessScore:null};
async function fixture(page:Page){
 await page.addInitScript(({user})=>{localStorage.setItem("token","isolated-fixture");localStorage.setItem("user",JSON.stringify(user));},{user});
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
  else if(path==="/development/plans/plan-fixture")json={presentation,plan:{id:"plan-fixture",current_version_id:"v1",confirmed_version_id:"v1",status:"active",active_run_id:null},partner_name:"合成伙伴",request:{development_direction:"合成验收方向"},conversation:[],payload:{overview:{development_direction:"合成验收方向"},stages:[],limitations:[],resource_gaps:[]},hidden:false,notice:null,versions:[{id:"v1",version_no:1}],runs:[{id:"failed-run",run_type:"revise",status:"failed",created_at:stamp,safe_error_message:reason.message}],failureDetails:[{...reason,stage:"generation",stageLabel:"建议生成"}]};
  else return route.fulfill({status:404,json:{detail:"Unexpected fixture request"}});
  return route.fulfill({json});
 });
 return writes;
}

test("list reasons work by click, keyboard and legacy fallback",async({page})=>{
 await fixture(page);await page.goto("/tasks");
 const row=page.getByRole("row").filter({hasText:"合成验收：部分完成"});
 await row.getByRole("button",{name:"查看原因"}).click();
 const dialog=page.getByRole("dialog",{name:"任务失败原因"});
 await expect(dialog).toBeVisible();await expect(dialog).toContainText("模型响应超时");await expect(dialog.getByRole("link",{name:"进入任务详情"})).toHaveAttribute("href","/tasks/partial-fixture");
 await page.keyboard.press("Escape");await expect(dialog).toBeHidden();
 const legacy=page.getByRole("row").filter({hasText:"合成验收：历史失败"}).getByRole("button",{name:"查看原因"});
 await legacy.focus();await page.keyboard.press("Enter");await expect(page.getByRole("dialog",{name:"任务失败原因"})).toContainText("具体原因未记录");
});

for(const width of [1366,1920])test(`partial and failed revise preserve useful results at ${width}`,async({page})=>{
 await page.setViewportSize({width,height:width===1366?768:1080});const writes=await fixture(page);
 await page.goto("/tasks/partial-fixture");const notice=page.getByRole("region",{name:"任务未完成说明"});
 await expect(notice).toContainText("伙伴推荐可用");await expect(notice).toContainText("项目机会未完成");await expect(notice).toContainText("模型响应超时");
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


test("initial failure explains cause without claiming recommendations are available",async({page})=>{
 await fixture(page);await page.goto("/tasks/failed-fixture");
 const notice=page.getByRole("region",{name:"任务未完成说明"});
 await expect(notice).toContainText("本次匹配未完成");
 await expect(notice).toContainText("模型服务认证失败");
 await expect(notice).not.toContainText("伙伴推荐可用");
 await notice.getByRole("button",{name:"查看原因"}).click();
 await expect(page.getByRole("dialog",{name:"任务失败原因"})).toContainText("联系管理员");
 await page.getByRole("heading",{name:"任务详情",exact:true}).click();
 await expect(page.getByRole("dialog",{name:"任务失败原因"})).toBeHidden();
});

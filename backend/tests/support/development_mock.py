"""Synthetic deterministic behavior for local development, never a real model benchmark."""
import json,re

def response(messages):
 data=json.loads(messages[-1]['content']);system=messages[0]['content'];request=data.get('request',data)
 partner=request.get('target_partner_id',data.get('target_partner_id'))
 direction=request.get('development_direction',request.get('development_goal',''))
 adjustment=request.get('adjustment','');text=direction+' '+adjustment
 if 'C_FAIL' in text or '模拟调整失败' in text:return {'invented_url':'https://example.com/invalid'}
 if 'converse' in system:
  message=data['message'];resources=data['current']['resources']
  if '实验' in message:resources=[r for r in resources if r['source_type']=='lab']
  modify=bool(re.search(r'不要|多给|再加|改为|改成|重点放|缩短|去掉|替换|增加|减少|优先|放后|先做|展开建议|模拟调整失败',message)) and not re.search(r'为什么|为何|有什么区别|如何比较|哪个.*更难|为什么适合|有没有更进阶',message)
  refs=[{k:r[k] for k in ('source_type','source_id','source_version')} for r in resources[:2]]
  if re.search(r'区别|比较|更难|更进阶',message):
   answer='当前可比较资源：\n'+'\n'.join(f"{r['title']}：用途为{r.get('target_capability') or r.get('summary','实践参考')}；难度{r.get('difficulty','未知')}；先修{r.get('prerequisites','未知')}；费用{r.get('cost','未知')}。" for r in resources[:2])
   if len(resources)>=2 and resources[0].get('difficulty')==resources[1].get('difficulty'):answer+='\n这两项标注难度相同；请结合用途、先修与账号环境选择，不能仅凭名称认定哪个更难。'
   if len(resources)<2:answer+='\n当前不足两项资源，请指出希望比较的资源。'
  else:
   analysis=data['current'].get('analysis',{})
   focuses=analysis.get('priorities',[])
   chosen=[f for f in focuses if any(word in message.lower() for word in f.get('search_terms',[])) or ('RAG' in message and 'RAG' in f['name'])]
   reasons=[f["name"]+'：'+f['reason'] for f in (chosen or focuses)[:3]]
   answer='本次方向来自你的发展诉求。'+ '；'.join(reasons+analysis.get('reusable_basis',[]))+'。资源数量不决定方向优先级，这些建议用于学习与项目准备，需要真实项目验证。'
  answer=answer.replace('advanced','高级').replace('intermediate','进阶').replace('beginner','入门').replace('unknown','未知')
  return {'target_partner_id':partner,'kind':'revise' if modify else 'explain','answer':'' if modify else answer,'references':refs}
 if 'analyze' in system:
  profile=data.get('profile',{});profile_text=json.dumps(profile,ensure_ascii=False);tags=data['formal_tags']
  exploratory=bool(re.search(r'往哪|什么方向|下一步适合',adjustment or direction));agent=bool(re.search(r'agent|rag|AI|人工智能',text,re.I)) or exploratory
  lab_only=bool(re.search(r'只.{0,8}实验|不要基础课.{0,8}多给实验',text))
  database='数据库' in text or not agent
  priorities=[]
  def focus(name,words,tagname,why):
   tag=next((t['id'] for t in tags if t['name']==tagname),None)
   priorities.append({'name':name,'reason':why,'reusable_basis':[profile['capabilities']] if profile.get('capabilities') else [],'capability_tag_id':tag,'search_terms':words})
  if agent:
   established=bool(re.search(r'数据库|云基础|系统集成|数据库交付',profile_text))
   if not established:focus('应用集成与云服务基础',['API','云服务','集成'],'上云规划实施','围绕应用交付打通 API 与云服务接入，可根据已有项目经验选择或跳过这项集成基础实践。')
   focus('RAG 与知识库工程',['RAG','知识库','检索'],'盘古大模型','将行业和数据经验迁移到知识检索与评估。')
   focus('Agent 系统集成与 POC 调优',['Agent','系统集成','POC'],'盘古大模型','围绕应用交付目标验证接口集成、工具调用和上线可用性。')
  if re.search(r'系统集成.*(优先|先)|先做系统集成|RAG.*放后',text,re.I):priorities.sort(key=lambda f:0 if 'Agent 系统集成' in f['name'] else 1)
  if database:focus('数据库迁移与回退验证',['数据库','迁移','回退'],'数据库','围绕数据交付经验深化迁移校验和回退实践。')
  if '容器' in text:priorities=[];focus('容器进阶实践',['容器','Kubernetes'],'云原生','根据用户只要进阶实验的意图选择实践资源。')
  basis=[]
  if profile.get('capabilities'):basis.append('已有可复用能力：'+profile['capabilities'])
  if profile.get('industries'):basis.append('已有行业经验：'+profile['industries'])
  if profile.get('ai_profile'):basis.append('结合当前画像：'+profile['ai_profile'])
  assessment=('当前可复用的基础包括'+profile.get('capabilities','已有业务经验')+'，行业经验涉及'+profile.get('industries','现有业务场景')+'。这些基础可以用于新方向的业务理解、数据接入与系统实施，建议围绕目标进一步发展'+ '、'.join(f['name'] for f in priorities)+'。') if profile.get('capabilities') else '当前画像依据有限，以下方向主要结合你的目标提出，不据此认定伙伴缺少能力。'
  return {'partner_assessment':assessment,'target_partner_id':partner,'intent':'resources' if lab_only else 'explore' if exploratory else 'development','interpretation':'按你的要求选择进阶实验。' if lab_only else '结合当前基础，可以先讨论以下发展方向。' if exploratory else 'Agent 应用交付与数据库迁移' if agent and database else '企业级 Agent 应用交付' if agent else '数据库迁移与回退验证','reusable_basis':basis,'priorities':priorities,'basis_limitations':['当前画像对本次方向的支撑有限，建议主要依据现有资料和发展目标形成。'] if profile.get('basis_limited',True) else [],'resource_types':['lab'] if lab_only else [],'excluded_difficulties':['beginner'] if '不要基础' in text or '进阶实验' in text or (agent and established) else []}
 analysis=data['analysis'];items=[]
 if 'C_GAP' not in text:
  for r in data['candidates'][:8]:
   haystack=' '.join(str(r.get(k,'')) for k in ('title','target_capability','summary','product_direction')).lower()
   f=max(analysis['priorities'],key=lambda f:sum(len(w) for w in f['search_terms'] if w.lower() in haystack),default={'name':'相关实践'})
   items.append({k:r[k] for k in ('source_type','source_id','source_version')}|{'capability_tag_id':r['capability_tag_ids'][0],'focus':f['name'],'reason':'围绕'+f['name']+'，结合当前可复用基础选择该资源。','estimated_hours':max((r.get('duration_minutes') or 60)/60,.5),'note':''})
 gaps=[]
 if not any(i['source_type']=='lab' for i in items):gaps.append('当前资源库未找到匹配实验，可先使用现有资源。')
 elif any('RAG' in f['name'] for f in analysis['priorities']) and not any(r['source_type']=='lab' and 'rag' in json.dumps(r,ensure_ascii=False).lower() for r in data['candidates']):gaps.append('当前资源库未找到 RAG 知识库工程匹配实验，可先使用课程和现有集成实践。')
 return {'target_partner_id':partner,'stages':[{'title':'进阶实验' if analysis['intent']=='resources' else '围绕发展重点选择资源','items':items}] if items else [],'answer':'以下是与你的诉求相关的资源。' if analysis['intent']=='resources' else '', 'limitations':[], 'resource_gaps':gaps,'next_steps':[] if analysis['intent']=='resources' else ['由伙伴自主判断准备程度，结合真实项目试跑；新的案例与交付件经既有机制进入画像后，再调整发展建议。']}

"""Synthetic deterministic behavior for local development, never a real model benchmark."""
import json,re

def response(messages):
 data=json.loads(messages[-1]['content']);system=messages[0]['content'];request=data.get('request',data)
 partner=request.get('target_partner_id',data.get('target_partner_id'))
 direction=request.get('development_direction',request.get('development_goal',''))
 adjustment=request.get('adjustment','');text=direction+' '+adjustment
 if 'C_FAIL' in text:return {'invented_url':'https://example.com/invalid'}
 if 'converse' in system:
  message=data['message'];resources=data['current']['resources']
  if '实验' in message:resources=[r for r in resources if r['source_type']=='lab']
  modify=bool(re.search(r'不要|多给|再加|改为|改成|重点放|缩短|去掉|替换|增加|减少',message)) and not re.search(r'为什么|为何|有什么区别|如何比较',message)
  refs=[{k:r[k] for k in ('source_type','source_id','source_version')} for r in resources[:2]]
  if re.search(r'区别|比较',message):
   answer='当前可比较资源：\n'+'\n'.join(f"{r['title']}：用途为{r.get('target_capability') or r.get('summary','实践参考')}；难度{r.get('difficulty','未知')}；先修{r.get('prerequisites','未知')}；费用{r.get('cost','未知')}。" for r in resources[:2])
   if len(resources)<2:answer+='\n当前不足两项资源，请指出希望比较的资源。'
  else:
   analysis=data['current'].get('analysis',{})
   reasons=[f["name"]+'：'+f['reason'] for f in analysis.get('priorities',[])[:3]]
   answer='本次方向来自你的发展诉求。'+ '；'.join(reasons+analysis.get('reusable_basis',[]))+'。资源数量不决定方向优先级，这些建议用于学习与项目准备，需要真实项目验证。'
  answer=answer.replace('advanced','高级').replace('intermediate','进阶').replace('beginner','入门').replace('unknown','未知')
  return {'target_partner_id':partner,'kind':'revise' if modify else 'explain','answer':'' if modify else answer,'references':refs}
 if 'analyze' in system:
  profile=data.get('profile',{});profile_text=json.dumps(profile,ensure_ascii=False);tags=data['formal_tags']
  exploratory=bool(re.search(r'往哪|什么方向|下一步适合',text));agent=bool(re.search(r'agent|rag|AI|人工智能',text,re.I)) or exploratory
  lab_only=bool(re.search(r'只.{0,8}实验|不要基础课.{0,8}多给实验',text))
  database='数据库' in text or not agent
  priorities=[]
  def focus(name,words,tagname,why):
   tag=next((t['id'] for t in tags if t['name']==tagname),None)
   priorities.append({'name':name,'reason':why,'capability_tag_id':tag,'search_terms':words})
  if agent:
   established=bool(re.search(r'数据库|云基础|系统集成|数据库交付',profile_text))
   if not established:focus('应用集成与云服务基础',['API','云服务','集成'],'上云规划实施','当前可用基础信息有限，先选择与目标直接相关的集成准备，不据此认定能力不足。')
   focus('RAG 与知识库工程',['RAG','知识库','检索'],'盘古大模型','将行业和数据经验迁移到知识检索与评估。')
   focus('Agent 系统集成与 POC 调优',['Agent','系统集成','POC'],'盘古大模型','围绕应用交付目标验证接口集成、工具调用和上线可用性。')
  if database:focus('数据库迁移与回退验证',['数据库','迁移','回退'],'数据库','围绕数据交付经验深化迁移校验和回退实践。')
  if '容器' in text:priorities=[];focus('容器进阶实践',['容器','Kubernetes'],'云原生','根据用户只要进阶实验的意图选择实践资源。')
  basis=[]
  if profile.get('capabilities'):basis.append('已有可复用能力：'+profile['capabilities'])
  if profile.get('industries'):basis.append('已有行业经验：'+profile['industries'])
  if profile.get('ai_profile'):basis.append('结合当前画像：'+profile['ai_profile'])
  return {'target_partner_id':partner,'intent':'resources' if lab_only else 'explore' if exploratory else 'development','interpretation':direction,'reusable_basis':basis,'priorities':priorities,'basis_limitations':['当前画像对本次方向的支撑有限，建议主要依据现有资料和发展目标形成。'] if profile.get('basis_limited',True) else [],'resource_types':['lab'] if lab_only else [],'excluded_difficulties':['beginner'] if '不要基础' in text or '进阶实验' in text or (agent and established) else []}
 analysis=data['analysis'];items=[]
 if 'C_GAP' not in text:
  for r in data['candidates'][:8]:
   f=next((f for f in analysis['priorities'] if f['capability_tag_id'] in r['capability_tag_ids']),analysis['priorities'][0] if analysis['priorities'] else {'name':'相关实践'})
   items.append({k:r[k] for k in ('source_type','source_id','source_version')}|{'capability_tag_id':r['capability_tag_ids'][0],'focus':f['name'],'reason':'围绕'+f['name']+'，结合当前可复用基础选择该资源。','estimated_hours':max((r.get('duration_minutes') or 60)/60,.5),'note':''})
 gaps=[]
 if not any(i['source_type']=='lab' for i in items):gaps.append('当前资源库未找到匹配实验，可先使用现有资源。')
 elif any('RAG' in f['name'] for f in analysis['priorities']) and not any(r['source_type']=='lab' and 'rag' in json.dumps(r,ensure_ascii=False).lower() for r in data['candidates']):gaps.append('当前资源库未找到 RAG 知识库工程匹配实验，可先使用课程和现有集成实践。')
 return {'target_partner_id':partner,'stages':[{'title':'进阶实验' if analysis['intent']=='resources' else '围绕发展重点选择资源','items':items}] if items else [],'answer':'以下是与你的诉求相关的资源。' if analysis['intent']=='resources' else '', 'limitations':[], 'resource_gaps':gaps,'next_steps':[] if analysis['intent']=='resources' else ['由伙伴自主判断准备程度，结合真实项目试跑；新的案例与交付件经既有机制进入画像后，再调整发展建议。']}

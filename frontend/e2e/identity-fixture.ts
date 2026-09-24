// Synthetic fixture sessions for business tests. Real identity ceremonies are tested separately.
import {readFileSync} from 'node:fs';
import {type APIRequestContext,type APIResponse} from '@playwright/test';
export async function fixtureLogin(request:APIRequestContext,username:string,password='ValidationPass123'):Promise<APIResponse>{
 if(username.startsWith('admin'))return request.post('http://localhost:8000/auth/admin/login',{data:{username,password}});
 const sessions=JSON.parse(readFileSync('/tmp/lingjian-enablement-e2e/identity-sessions.json','utf8'));
 const session=sessions[username];if(!session)throw new Error('Unknown synthetic identity');
 return {ok:()=>true,status:()=>200,json:async()=>session,text:async()=>JSON.stringify(session)} as APIResponse;
}

'use strict';
// Compiled worker test using synthetic official OneComme events and isolated data.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
async function main(){
    const dir=path.resolve(process.argv[2]);
    const local=fs.mkdtempSync(path.join(os.tmpdir(),'queue-receiving-smoke-'));
    const direct=process.argv.includes('--comments-only');
    const source={id:'restricted-row',name:'Restricted smoke',enabled:true,
        ...(direct?{}:{url:'https://www.youtube.com/@smoke/live',meta:{}})};
    let child,key;
    const {createPlugin}=require(path.join(dir,'plugin.js'));
    const plugin=createPlugin({spawnWorker:(exe,args,options)=>{
        child=spawn(exe,args,{...options,env:{...process.env,LOCALAPPDATA:local}});return child;
    }});
    async function until(fn){
        const end=Date.now()+30000;
        while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,100));}
        throw Error('receiving smoke timeout');
    }
    async function api(endpoint,body){
        const r=await fetch('http://127.0.0.1:18765'+endpoint,{method:body?'POST':'GET',
            headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},
            body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(5000)});
        assert.equal(r.status,200);return r.json();
    }
    async function start(){
        plugin.init({dir},{services:[source]});
        await until(async()=>{
            const ready=(await plugin.request({method:'GET'})).response;
            if(!ready.ready)return false;key=new URL(ready.control).hash.slice(5);return true;
        });
        await until(async()=>{const state=await api('/api/onecomme/status');return state.connected&&(direct||state.ready_to_receive);});
    }
    function comment(id,message){return {service:'youtube',name:'Restricted smoke',data:{
        id,liveId:'opaque-restricted-room',userId:'opaque-viewer',name:'Smoke viewer',
        isMember:true,timestamp:new Date().toISOString(),comment:message}};}
    try{
        await start();
        assert.equal((await api('/api/onecomme/status')).selected,'');
        const settings=await fetch('http://127.0.0.1:18765/settings',{headers:{Authorization:'Bearer '+key}}).then(r=>r.text());
        assert.ok(settings.includes('id="onecomme-url"'));
        assert.ok(settings.includes('id="onecomme-url-select"'));
        for (const label of ['受付中の文言','現在対局中の見出し','次回グループの見出し','待機グループ数の見出し']) {
            assert.ok(settings.includes('<label>'+label+' <input id="setup-label-'));
        }
        const appearance=await api('/api/settings/overlay');
        assert.deepEqual(['open_label','now_label','next_label','queue_label'].map(key=>appearance[key]),
            ['受付中','現在の対戦','次回','待機人数']);
        const manualURL=direct?'':'https://www.youtube.com/watch?v=abcdefghijk';
        if(!direct){
            const linked=await api('/api/onecomme/select-url',{url:'https://youtu.be/abcdefghijk?si=discard-this',service_id:source.id});
            assert.equal(linked.manual_url,manualURL);assert.equal(linked.ready_to_receive,true);
        }
        assert.equal((await api('/api/bot')).authenticated,false);
        const description=(await api('/api/settings/description')).text;
        assert.ok(description.includes('参加回数が少ない方を優先させる場合があります。'));
        assert.ok(description.includes('待機順を確認する場合は、@JoinQueueBotへリプライしてください。'));
        assert.ok(description.includes('同じ方への回答は3分に1回です。'));
        await api('/api/setup',{completed:true,deferred:false,step:4,use_bot:false,use_obs:true});
        plugin.filterComment(comment('join','参加希望'),source);
        await until(async()=>(await api('/api/state')).current.length===1);
        let status=await api('/api/onecomme/status');
        assert.equal(status.selected,'opaque-restricted-room');assert.equal(status.services[0].id,'');
        assert.equal((await api('/api/overlay-state')).now_view[0].display_name,'Smoke viewer');
        plugin.destroy();await until(()=>child.exitCode!==null);
        await start();
        assert.equal((await api('/api/setup')).completed,true);
        assert.equal((await api('/api/onecomme/status')).manual_url,manualURL);
        assert.equal((await api('/api/state')).current.length,1);
        plugin.filterComment(comment('relink','接続確認'),source);
        await until(async()=>(await api('/api/onecomme/status')).selected==='opaque-restricted-room');
        assert.equal((await api('/api/state')).current.length,1);
        assert.equal((await api('/api/overlay-state')).now_view[0].display_name,'Smoke viewer');
    }finally{plugin.destroy();if(child)await until(()=>child.exitCode!==null);}
    console.log(JSON.stringify({ok:true,compiled_worker:true,receiving_without_video_metadata:true,
        direct_comments:direct,manual_url:!direct,synthetic_membership_comment:true,overlay_data:true,setup_without_bot:true,restart_restore:true,isolated_data:true}));
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});

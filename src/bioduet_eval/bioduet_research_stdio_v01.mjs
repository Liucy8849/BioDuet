// Sandbox-only fixed Unix MCP transport; no host URL or filesystem control.
import net from 'node:net';
import readline from 'node:readline';
async function relay(message){
 const body=Buffer.from(JSON.stringify(message));
 if(body.length>131072)throw Error('REQUEST_LIMIT');
 return await new Promise((resolve,reject)=>{
  const socket=net.createConnection('/research.sock');let data=Buffer.alloc(0),settled=false;
  const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);socket.destroy();error?reject(error):resolve(value);};
  const timer=setTimeout(()=>finish(Error('TOOL_DEADLINE')),300000);
  socket.on('connect',()=>{const h=Buffer.alloc(4);h.writeUInt32BE(body.length);socket.write(Buffer.concat([h,body]));});
  socket.on('data',chunk=>{
   data=Buffer.concat([data,chunk]);if(data.length>1048580)return finish(Error('RESPONSE_LIMIT'));
   if(data.length>=4){const n=data.readUInt32BE(0);if(n>1048576)return finish(Error('RESPONSE_LIMIT'));
    if(data.length===n+4){try{finish(null,JSON.parse(data.subarray(4).toString()));}catch(error){finish(error);}}
    else if(data.length>n+4)finish(Error('EXTRA_RESPONSE_BYTES'));
   }
  });
  socket.on('error',error=>finish(error));
  socket.on('close',()=>{if(!settled)finish(Error('INCOMPLETE_RESPONSE'));});
 });
}
let queue=Promise.resolve();
readline.createInterface({input:process.stdin,crlfDelay:Infinity}).on('line',line=>{
 queue=queue.then(async()=>{
  let message;
  try{
   if(Buffer.byteLength(line)>131072)throw Error('REQUEST_LIMIT');
   message=JSON.parse(line);
   if(message.id===undefined)return;
   const response=await relay(message);
   process.stdout.write(JSON.stringify(response)+'\n');
  }catch(error){
   process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:message?.id??null,
     error:{code:-32000,message:'BioDuet transport unavailable; inspect retained episode evidence.'}})+'\n');
  }
 });
});

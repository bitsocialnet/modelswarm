// Single-request subprocess boundary. Secrets arrive only over stdin; stdout is
// one bounded JSON result, never native PKC objects/errors containing signers.
import PKC, { createAnchorIpnsRecord } from '@pkcprotocol/pkc-js';
import { CID } from 'multiformats/cid';
import { of as ipfsHash } from 'typestub-ipfs-only-hash';
import { encodeRelease, parsePublisher, scanDiscussionFeed, verifyDiscussion, verifyRelease } from './protocol.mjs';

class RequestError extends Error {}
const fail = (message) => { throw new RequestError(message); };
const MAX_INPUT = 128 * 1024;
const MAX_MANIFEST = 1024 * 1024; // Pinned PKC fetchCid RPC limit; no size override.
let pkc;
let timer;
const resources = [];

async function input() {
  let data = '';
  for await (const chunk of process.stdin) {
    data += chunk;
    if (Buffer.byteLength(data) > MAX_INPUT) fail('Bridge request is too large');
  }
  try { return JSON.parse(data); } catch { fail('Bridge request must be JSON'); }
}
function rpcUrl(value) {
  if (typeof value !== 'string' || value.length > 8192) fail('A PKC RPC URL is required');
  let url;
  try { url = new URL(value); } catch { fail('Invalid PKC RPC URL'); }
  if (url.username || url.password || url.hash || !['ws:', 'wss:'].includes(url.protocol)) fail('Invalid PKC RPC URL');
  if (url.protocol === 'ws:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) fail('Remote RPC requires wss://');
  return value;
}
function timeoutResult() {
  process.stdout.write(JSON.stringify({ok:false,error:'PKC operation timed out; a publish or renewal may have succeeded. Check its result before retrying.'})+'\n');
  process.exit(1);
}
async function client(rpc) {
  const options = { noData:true, httpRoutersOptions:[], ipfsGatewayUrls:[], kuboRpcClientsOptions:[], pubsubKuboRpcClientsOptions:[], resolveAuthorNames:false };
  if (rpc) options.pkcRpcClientsOptions = [rpcUrl(rpc)];
  pkc = await PKC(options);
  pkc.on('error', () => {});
  return pkc;
}
async function signer(privateKey) {
  if (typeof privateKey !== 'string' || !/^[A-Za-z0-9+/]{43}$/.test(privateKey) || Buffer.from(privateKey,'base64').length !== 32) fail('Invalid Ed25519 private key');
  return pkc.createSigner({type:'ed25519', privateKey});
}
function event(instance, name, trigger, accepts=()=>true) {
  return new Promise((resolve,reject) => {
    const cleanup=()=>{instance.removeListener(name,onEvent);instance.removeListener('error',onError);};
    const onEvent=(...args)=>{ if(accepts(...args)){cleanup();resolve(args[0]);} };
    const onError=(error)=>{cleanup();reject(error);};
    instance.on(name,onEvent); instance.once('error',onError);
    Promise.resolve().then(trigger).catch(onError);
  });
}
async function loadProfile(publisher) {
  const profile=await pkc.createCommunity({publicKey:parsePublisher(publisher)});
  resources.push(profile);
  profile.on('error',()=>{});
  // Even an RPC-local instance must request fresh public pages.
  await event(profile,'update',()=>profile.update(),()=>typeof profile.updatedAt==='number');
  return profile;
}
// The node-held half of a delegation this RPC node hosts. Only an RPC-local
// profile exposes its minter; a remote reader's view of the same profile does not.
async function hostedProfile(publisher) {
  const profile=await pkc.createCommunity({publicKey:parsePublisher(publisher)});
  profile.on('error',()=>{});
  if(profile.publicKey!==publisher||profile.anchor?.publicKey!==publisher||typeof profile.signer?.address!=='string'||profile.signer.address===publisher) fail('This RPC node does not host a delegated profile for this publisher');
  return profile;
}
async function readRelease(cid,publisher) {
  CID.parse(cid);
  const response=await pkc.fetchCid({cid});
  return verifyRelease({rawComment:response.content,cid,publisher});
}
async function discover(publisher,name,version) {
  const profile=await loadProfile(publisher);
  const seenPages=new Set();
  const seenPosts=new Set();
  const matches=[];
  let page=profile.posts?.pages?.new;
  let next=profile.posts?.pageCids?.new;
  for(let count=0;page||next;count++) {
    if(count>=32) fail('Profile exceeds the 32-page scan limit; use an immutable release CID');
    if(!page) {
      if(typeof next!=='string'||seenPages.has(next)) fail('Invalid or cyclic profile pages');
      seenPages.add(next);
      page=await profile.posts.getPage({cid:next});
    }
    if(!Array.isArray(page.comments)) fail('Invalid profile page');
    for(const candidate of page.comments) {
      const cid=candidate.cid;
      if(typeof cid!=='string'||seenPosts.has(cid)) continue;
      seenPosts.add(cid);
      if(seenPosts.size>1024) fail('Profile exceeds the 1024-post scan limit; use an immutable release CID');
      // Candidate fields are merely hints: never use them to authorize a pull.
      // Invalid/foreign/non-release posts cannot claim the owner's namespace.
      try { CID.parse(cid); } catch { continue; }
      const {content:rawComment}=await pkc.fetchCid({cid});
      let verified;
      try { verified=await verifyRelease({rawComment,cid,publisher}); } catch { continue; }
      if(verified.release.name===name&&verified.release.version===version) matches.push(verified);
    }
    next=page.nextCid;
    page=undefined;
  }
  const announcements=new Set(matches.map(item=>encodeRelease(item.release)));
  if(announcements.size>1) fail('Publisher has conflicting announcements for this version; pin a release CID');
  matches.sort((a,b)=>a.cid.localeCompare(b.cid));
  return matches[0];
}

async function publishDiscussion(community, privateKey, fields, parent) {
  // The publisher's release is embedded as a native PKC crosspost and must
  // still fit the native publication limit once wrapped in the new signature.
  if (fields.crosspost && Buffer.byteLength(JSON.stringify(fields)) > 37000) fail('Release is too large to crosspost');
  const author = await signer(privateKey);
  const comment = await pkc.createComment({ signer: author, communityPublicKey: community, ...fields });
  resources.push(comment);
  comment.once('challenge', () => {
    comment.emit('error', new RequestError('The community requires an unsupported publishing challenge'));
  });
  const verification = await event(comment, 'challengeverification', () => comment.publish());
  if (!verification?.challengeSuccess || !comment.cid) fail('The community rejected publication');
  return readDiscussion(comment.cid, community, parent);
}

async function readDiscussion(cid, community, parent) {
  CID.parse(cid);
  const { content: rawComment } = await pkc.fetchCid({ cid });
  return verifyDiscussion({ rawComment, cid, community, parent });
}

async function discussionFeed(community) {
  const profile = await loadProfile(community);
  return { community, ...await scanDiscussionFeed(profile.posts, (cid, parent) => readDiscussion(cid, community, parent)) };
}

async function main(request) {
  const timeout=request.timeout ?? 120;
  if(!Number.isFinite(timeout)||timeout<=0||timeout>3600) fail('PKC timeout must be finite and between 0 and 3600 seconds');
  timer=setTimeout(timeoutResult,timeout*1000);
  process.env.PKC_RPC_CALL_TIMEOUT_MS=String(Math.ceil(timeout*1000));
  if(request.op==='keygen') {
    await client();
    const key=await pkc.createSigner();
    return {publisher:key.address,privateKey:key.privateKey};
  }
  if(request.op==='key-info') {
    await client();
    const key=await signer(request.privateKey);
    return {publisher:key.address};
  }
  await client(rpcUrl(request.rpc));
  if (request.op === 'community-init') {
    const owner = await signer(request.privateKey);
    const hub = await pkc.createCommunity({
      title: request.title, roles: { [owner.address]: { role: 'owner' } },
      settings: { challenges: [], pages: { posts: [{ name: 'new', preloaded: true }], replies: [{ name: 'new', preloaded: true }] } },
    });
    hub.on('error', () => {});
    await event(hub, 'update', () => hub.start(), () => typeof hub.updatedAt === 'number');
    return { community: parsePublisher(hub.publicKey) };
  }
  if (request.op === 'community-list') return discussionFeed(parsePublisher(request.community));
  if (request.op === 'community-share') {
    const community = parsePublisher(request.community);
    const original = await readRelease(request.cid, parsePublisher(request.publisher));
    if (original.release.name !== request.name || original.release.version !== request.version) fail('Pinned release does not match the requested model and version');
    return publishDiscussion(community, request.privateKey, { crosspost: { cid: original.cid, comment: original.comment } });
  }
  if (request.op === 'community-reply') {
    const community = parsePublisher(request.community);
    if (typeof request.text !== 'string' || !request.text.isWellFormed() || !request.text.trim() || Buffer.byteLength(request.text) > 4096) {
      fail('Reply must contain up to 4 KiB of text');
    }
    const { postCid } = await readDiscussion(request.cid, community);
    return publishDiscussion(community, request.privateKey, { parentCid: postCid, postCid, content: request.text }, postCid);
  }
  if(request.op==='profile-init') {
    const owner=await signer(request.privateKey);
    // Creation deliberately has no signer: only the public owner identity
    // crosses RPC. The node generates and retains its distinct minter key.
    const profile=await pkc.createCommunity({
      anchor:{publicKey:owner.address}, roles:{[owner.address]:{role:'owner'}},
      title:'ModelSwarm publisher', suggested:{uiType:'author'},
      settings:{disablePubsubChallengeExchange:true,
        challenges:[{name:'fail',options:{error:'Only the publisher can post to this profile.'},publicOptions:['error'],exclude:[{roles:['owner']}]}],
        pages:{posts:[{name:'new',preloaded:true}],replies:[]}}
    });
    // Do not add this started profile to resources: stopping this client must
    // leave the node hosting it. PKC RPC destroy only unsubscribes locally.
    profile.on('error',()=>{});
    if(profile.publicKey!==owner.address||profile.anchor?.publicKey!==owner.address||!profile.signer?.address||profile.signer.address===owner.address) fail('RPC returned an invalid delegated profile');
    if(profile.anchorRecordSequence!==undefined) fail('Profile already has an anchor record; refusing to replace delegation');
    const anchor=await createAnchorIpnsRecord({anchorSigner:owner,minterIpnsName:profile.signer.address,sequence:0});
    await profile.publishAnchorRecord(anchor);
    await event(profile,'update',()=>profile.start(),()=>typeof profile.updatedAt==='number');
    return {publisher:owner.address,minter:profile.signer.address,started:true};
  }
  if(request.op==='profile-start') {
    // Not added to resources, like profile-init: the node keeps hosting it.
    const profile=await hostedProfile(request.publisher);
    if(profile.anchorRecordSequence===undefined) fail('Profile has no anchor record; run profile-init first');
    try {
      await event(profile,'update',()=>profile.start(),()=>typeof profile.updatedAt==='number');
    } catch(error) {
      // A killed node leaves its start lock behind until it goes stale.
      if(error?.code==='ERR_COMMUNITY_ALREADY_STARTED') fail('The node still holds this profile\'s start lock; if the node was killed, retry in 10 seconds');
      throw error;
    }
    return {publisher:request.publisher,minter:profile.signer.address,started:true};
  }
  if(request.op==='profile-renew') {
    const owner=await signer(request.privateKey);
    const profile=await hostedProfile(owner.address);
    // The minter and both sequences below are the RPC's claims, and the result
    // is a delegation signed by the owner. Renew only the minter the owner
    // names, so a wrong or dishonest node cannot have a new one delegated to.
    if(profile.signer.address!==parsePublisher(request.minter)) fail('This RPC node holds a different minter than the one given; refusing to delegate to it');
    const previous=profile.anchorRecordSequence;
    if(typeof previous!=='string'||!/^\d{1,15}$/.test(previous)) fail('Profile has no anchor record to renew; run profile-init first');
    // Only the node, the online party, knows which sequence beats every record
    // already published. Never sign one that goes back, nor a jump far beyond
    // the SDK's margin of five: an inflated sequence can never be taken back.
    const {nextSequence}=await profile.prepareAnchorPublish();
    if(typeof nextSequence!=='string'||!/^\d{1,15}$/.test(nextSequence)||BigInt(nextSequence)<=BigInt(previous)||BigInt(nextSequence)-BigInt(previous)>1000n) fail('RPC returned an implausible anchor sequence; refusing to sign it');
    const anchor=await createAnchorIpnsRecord({anchorSigner:owner,minterIpnsName:profile.signer.address,sequence:nextSequence});
    const published=await profile.publishAnchorRecord(anchor);
    if(published?.sequence!==nextSequence||published.value!==`/ipns/${profile.signer.address}`||published.anchorPublicKey!==owner.address) fail('RPC did not accept the renewed anchor record');
    return {publisher:owner.address,minter:profile.signer.address,sequence:nextSequence,previousSequence:previous};
  }
  if(request.op==='publish') {
    const owner=await signer(request.privateKey);
    let content;
    // These errors describe local release fields, never an SDK object with secrets.
    try { content=encodeRelease(request.release); } catch(error) { fail(error.message); }
    const profile=await loadProfile(owner.address);
    if(profile.anchor?.publicKey!==owner.address||profile.roles?.[owner.address]?.role!=='owner'||!profile.settings?.disablePubsubChallengeExchange) fail('Publishing requires your feed-only delegated profile on this RPC node');
    const existing=await discover(owner.address,request.release.name,request.release.version);
    if(existing) {
      if(encodeRelease(existing.release)!==content) fail('This version already names a different release');
      return {...existing,reused:true};
    }
    const comment=await pkc.createComment({signer:owner,communityPublicKey:owner.address,
      title:`${request.release.name} ${request.release.version}`,content});
    resources.push(comment);
    // JSON escapes the card again inside the signed PKC publication.
    if(Buffer.byteLength(JSON.stringify(comment.raw.pubsubMessageToPublish))>40000) fail('Signed publication exceeds 40,000 bytes after encoding; shorten the model card or manifest URL');
    const verification=await event(comment,'challengeverification',()=>comment.publish());
    if(!verification?.challengeSuccess||!comment.cid) fail('The profile rejected publication');
    // Read back the immutable record and verify locally, even when our RPC
    // reports success. A transport receipt alone is not publication evidence.
    const verified=await readRelease(comment.cid,owner.address);
    if(encodeRelease(verified.release)!==content) fail('Published release differs from the signed request');
    return {...verified,reused:false};
  }
  if(request.op==='resolve') {
    const publisher=parsePublisher(request.publisher);
    const verified=request.cid ? await readRelease(request.cid,publisher) : await discover(publisher,request.name,request.version);
    if(!verified) fail('No verified publisher release matches this model and version');
    if(verified.release.name!==request.name||verified.release.version!==request.version) fail('Pinned release does not match the requested model and version');
    return verified;
  }
  if(request.op==='fetch-manifest') {
    const cid=CID.parse(request.cid);
    // At the size boundary, the pinned SDK compares its CIDv0 hash as a string.
    // Normalize equivalent default UnixFS CIDs before that transport check.
    const fetchCid=cid.code===0x70&&cid.multihash.code===0x12&&cid.multihash.digest.byteLength===32?cid.toV0():cid;
    let content;
    try { ({content}=await pkc.fetchCid({cid:fetchCid.toString()})); }
    catch(error) {
      if(error?.code==='ERR_OVER_DOWNLOAD_LIMIT') fail('IPFS manifests are limited to 1 MiB by the pinned PKC SDK; use an HTTPS manifest URL');
      throw error;
    }
    if(typeof content!=='string'||Buffer.byteLength(content)>MAX_MANIFEST) fail('IPFS manifest exceeds the 1 MiB limit; use an HTTPS manifest URL');
    const computed=CID.parse(await ipfsHash(Buffer.from(content)));
    if(!computed.toV1().equals(cid.toV1())) fail('IPFS manifest bytes do not match their CID');
    return {content};
  }
  fail('Unknown bridge operation');
}

try {
  const result=await main(await input());
  process.stdout.write(JSON.stringify({ok:true,...result})+'\n');
} catch(error) {
  const code=typeof error?.code==='string'&&/^ERR_[A-Z0-9_]+$/.test(error.code)?error.code:undefined;
  const message=error instanceof RequestError?error.message:code?`PKC operation failed (${code})`:'PKC operation or signature verification failed';
  process.stdout.write(JSON.stringify({ok:false,error:message})+'\n');
  process.exitCode=1;
} finally {
  clearTimeout(timer);
  // SDK shutdown may stall on an unavailable RPC. Bound cleanup too.
  const force=setTimeout(()=>process.exit(process.exitCode??0),5000);
  for(const instance of resources.reverse()) { try{await (typeof instance.stopWithoutRpcCall==='function'?instance.stopWithoutRpcCall():instance.stop());}catch{} }
  try{await pkc?.destroy();}catch{}
  clearTimeout(force);
}

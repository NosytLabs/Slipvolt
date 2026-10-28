const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const path=require('node:path').join(__dirname,'../public/admin/burns/account-view.js');
function moduleUnderTest(){assert.ok(fs.existsSync(path),'Treasury account view is missing');return require(path);}
const owner='C'.repeat(43),mint='A'.repeat(43),source='B'.repeat(43),program='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const config={treasury_owner:owner,mint,decimals:6};
const fixture=()=>({schema:'holdbyte.treasury-accounts.v1',treasury_owner:owner,mint,decimals:6,token_program:program,listing_slot:10,reference_slot:11,total_raw:'9007199254740993',execution_enabled:false,transactions_sent:0,accounts:[{address:source,balance_raw:'9007199254740993',review_eligible:true,reason:null}]});
test('exact account quantities never pass through Number',()=>{const v=moduleUnderTest();assert.equal(v.format('9007199254740993',6),'9,007,199,254.740993');assert.equal(v.normalize(fixture(),config).accounts[0].balance_raw,'9007199254740993');});
test('zero listing is distinct from malformed or unavailable',()=>{const v=moduleUnderTest();assert.equal(v.normalize({...fixture(),accounts:[],total_raw:'0'},config).accounts.length,0);for(const x of [null,{}, {accounts:[]}])assert.throws(()=>v.normalize(x,config));});
for(const change of [{mint:'D'.repeat(43)},{treasury_owner:'D'.repeat(43)},{decimals:9},{execution_enabled:true},{transactions_sent:1},{reference_slot:9},{listing_slot:0},{total_raw:'1'},{token_program:'evil'},{accounts:null}])test('reject inconsistent discovery '+JSON.stringify(change),()=>assert.throws(()=>moduleUnderTest().normalize({...fixture(),...change},config)));
test('reject duplicate accounts and eligibility/quantity mismatches',()=>{const v=moduleUnderTest();for(const change of [{balance_raw:'0'},{balance_raw:'1e6'},{balance_raw:9007199254740993},{reason:'frozen'},{review_eligible:false},{address:'javascript:alert(1)'}]){const f=fixture();f.accounts[0]={...f.accounts[0],...change};assert.throws(()=>v.normalize(f,config));}const f=fixture();f.accounts.push(f.accounts[0]);assert.throws(()=>v.normalize(f,config));});
test('known restrictions have usable labels without accepting arbitrary HTML',()=>{const v=moduleUnderTest();for(const reason of ['frozen','delegated','native','empty','close_authority','unsupported_extension']){const f=fixture();f.accounts[0].review_eligible=false;f.accounts[0].reason=reason;if(reason==='empty'){f.accounts[0].balance_raw='0';f.total_raw='0';}assert.equal(v.normalize(f,config).accounts[0].review_eligible,false);assert.equal(typeof v.reason(reason),'string');}assert.throws(()=>v.reason('<script>'));});

test('shared treasury arithmetic parses exact token units and untrusted raw quantities',()=>{
  const v=moduleUnderTest();
  assert.equal(v.parseUnits('1.25',6),'1250000');
  assert.equal(v.parseUnits('18446744073709551615',0),'18446744073709551615');
  assert.equal(v.parseUnits('0.000001',6),'1');
  assert.equal(v.parseRaw('18446744073709551615'),18446744073709551615n);
  assert.equal(v.format('1250000',6),'1.25');
  for(const amount of ['0','0.000000','01.25','1e6','-1','1.2345678','18446744073709551616','abc',1.25,null]){
    assert.throws(()=>v.parseUnits(amount,6),String(amount));
  }
  for(const raw of ['18446744073709551616','01','1e6','-1',1,null]){
    assert.throws(()=>v.parseRaw(raw),String(raw));
  }
  for(const precision of [-1,19,1.5,NaN,'6']){
    assert.throws(()=>v.parseUnits('1',precision),String(precision));
  }
});
test('burn review imports the shared exact helpers instead of its duplicate parsers',()=>{
  const app=fs.readFileSync(require('node:path').join(__dirname,'../public/admin/burns/app.js'),'utf8');
  const html=fs.readFileSync(require('node:path').join(__dirname,'../public/admin/burns/index.html'),'utf8');
  assert.ok(html.indexOf('src="account-view.js"')<html.indexOf('src="app.js"'));
  assert.match(app,/\.parseUnits\(/);
  assert.match(app,/\.parseRaw\(/);
  assert.match(app,/\.format\(/);
  assert.ok(!app.includes('const raw=(v,d)=>'));
  assert.ok(!app.includes('const exact=v=>'));
});

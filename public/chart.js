'use strict';
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.SlipvoltCharts=api;
})(typeof window!=='undefined'?window:globalThis,function(){
  const NS='http://www.w3.org/2000/svg';
  const SAFE=/^[A-Za-z][A-Za-z0-9_]*$/;
  const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function checkKey(key){if(typeof key!=='string'||!SAFE.test(key)||key==='__proto__'||key==='constructor'||key==='prototype')throw new Error('Invalid chart key');}
  function build(rows,opts){
    if(!Array.isArray(rows)||!opts||!Array.isArray(opts.series)||!opts.series.length)throw new Error('Invalid chart data');
    checkKey(opts.x);const seen=new Set();for(const s of opts.series){checkKey(s.key);if(seen.has(s.key))throw new Error('Duplicate chart series');seen.add(s.key);}
    const clean=[];
    for(const row of rows){
      if(!row||typeof row!=='object')continue;const label=row[opts.x];if(typeof label!=='string'||!label)continue;
      const values=opts.series.map(s=>Number(row[s.key]));if(values.some(v=>!Number.isFinite(v)))continue;
      clean.push({label,values});
    }
    const max=Math.max(0,...clean.flatMap(r=>r.values));
    return {labels:clean.map(r=>r.label),series:opts.series.map((s,i)=>({key:s.key,label:s.label||s.key,values:clean.map(r=>r.values[i])})),max};
  }
  const lineModel=build,barModel=build;
  function shortDate(value){const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));if(!m)return String(value);const month=Number(m[2]);return month>=1&&month<=12?MONTHS[month-1]+' '+Number(m[3]):String(value);}
  function svgNode(tag,attrs={},text){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!=null)n.textContent=String(text);return n;}
  function format(v,kind){if(kind==='usd')return '$'+new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v);return new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v);}
  function mount(target,model,opts,type){
    if(!target)return false;target.replaceChildren();target.dataset.state=model.labels.length?'ready':'empty';if(!model.labels.length||model.max<=0)return false;
    const W=720,H=240,L=54,R=18,T=18,B=38,plotW=W-L-R,plotH=H-T-B,max=model.max||1;
    const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':opts.ariaLabel||'Measured chart'});svg.classList.add('sv-chart-svg');
    for(let i=0;i<=4;i++){const y=T+plotH*i/4;svg.append(svgNode('line',{x1:L,y1:y,x2:W-R,y2:y,class:'sv-grid'}));svg.append(svgNode('text',{x:L-9,y:y+4,'text-anchor':'end',class:'sv-axis'},format(max*(4-i)/4,opts.format)));}
    if(type==='line'){
      model.series.forEach((series,si)=>{let d='';series.values.forEach((v,i)=>{const x=L+(model.labels.length===1?plotW/2:plotW*i/(model.labels.length-1));const y=T+plotH-(v/max)*plotH;d+=(i?' L ':'M ')+x+' '+y;});svg.append(svgNode('path',{d,class:`sv-series sv-series-${si+1}`}));});
    }else{
      const groupW=plotW/model.labels.length,barW=Math.max(2,Math.min(22,(groupW-6)/model.series.length));
      model.labels.forEach((_,i)=>model.series.forEach((series,si)=>{const v=series.values[i],h=(v/max)*plotH;const x=L+i*groupW+(groupW-barW*model.series.length)/2+si*barW;svg.append(svgNode('rect',{x,y:T+plotH-h,width:Math.max(1,barW-2),height:h,class:`sv-bar sv-series-${si+1}`}));}));
    }
    const step=Math.max(1,Math.ceil(model.labels.length/6));model.labels.forEach((label,i)=>{if(i%step&&i!==model.labels.length-1)return;const x=L+(model.labels.length===1?plotW/2:plotW*i/(Math.max(1,model.labels.length-1)));svg.append(svgNode('text',{x,y:H-12,'text-anchor':'middle',class:'sv-axis'},shortDate(label)));});
    target.append(svg);return true;
  }
  function renderLine(target,rows,opts){return mount(target,lineModel(rows,opts),opts,'line');}
  function renderBars(target,rows,opts){return mount(target,barModel(rows,opts),opts,'bar');}
  return {lineModel,barModel,shortDate,renderLine,renderBars};
});

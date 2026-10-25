/* Public metadata only. No keys, wallet calls, inference or persisted history. */
(function(){
  'use strict';
  function start(){
    const $=id=>document.getElementById(id),V=globalThis.HoldbyteModelDirectory;
    const state={catalog:null,serial:0,controller:null};
    const tokens=value=>value===null?'Unknown':new Intl.NumberFormat('en').format(value);
    function node(tag,className,text){const element=document.createElement(tag);if(className)element.className=className;if(text!==undefined)element.textContent=text;return element;}
    function datum(list,title,value){const group=node('div');group.append(node('dt','',title),node('dd','',value));list.append(group);}
    function render(){
      $('model-cards').replaceChildren();$('empty-state').hidden=true;
      if(!state.catalog){$('model-count').textContent='—';return;}
      const models=V.filter(state.catalog,$('model-search').value,$('availability-filter').value);
      $('model-count').textContent=models.length+' of '+state.catalog.models.length+' models';$('empty-state').hidden=models.length!==0;
      for(const model of models){
        const card=node('article','model-card'),top=node('div','card-top'),badge=node('span','badge',V.status(model,state.catalog.live));
        badge.dataset.state=V.status(model,state.catalog.live).toLowerCase();
        top.append(node('span','model-category',model.category),badge);card.append(top,node('h2','',model.name));
        const identity=node('div','model-id'),copy=node('button','button copy-id','Copy ID');copy.type='button';copy.setAttribute('aria-label','Copy '+model.name+' model ID');
        copy.addEventListener('click',async()=>{const serial=state.serial;try{await navigator.clipboard.writeText(model.id);if(serial===state.serial)$('copy-status').textContent='Copied model ID: '+model.id;}catch{if(serial===state.serial)$('copy-status').textContent='Clipboard unavailable. Select and copy the model ID shown on the card.';}});
        identity.append(node('code','',model.id),copy);card.append(identity);
        const limits=node('dl','model-limits');datum(limits,'Context · tokens',tokens(model.context));datum(limits,'Output cap · tokens',tokens(model.output));datum(limits,'Default output',tokens(model.defaultOutput));
        card.append(limits,node('p','model-note','Local service limits—not verified upstream maximums.'));
        if(model.override)card.append(node('p','override','Operator override configured · upstream acceptance unverified'));
        const details=node('details'),evidence=node('dl','evidence');details.append(node('summary','','Limit sources'));
        datum(evidence,'Context policy',model.contextSource);datum(evidence,'Output policy',model.outputSource);
        datum(evidence,'Discovered context',tokens(model.discoveredContext));datum(evidence,'Discovered output',tokens(model.discoveredOutput));
        details.append(evidence,node('p','',model.source));card.append(details);$('model-cards').append(card);
      }
    }
    function invalidate(){state.serial++;state.controller?.abort();state.controller=null;state.catalog=null;render();$('copy-status').textContent='';}
    async function refresh(){
      invalidate();const serial=state.serial,controller=new AbortController();state.controller=controller;
      $('refresh-models').disabled=true;$('catalog-state').textContent='Loading';delete $('catalog-state').dataset.live;
      $('catalog-message').textContent='Checking the service catalog…';$('catalog-source').textContent='';
      const timeout=setTimeout(()=>controller.abort(),20000);
      try{
        const response=await fetch('/api/models',{credentials:'omit',cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error('Catalog request failed ('+response.status+').');
        const text=await response.text();if(text.length>250000)throw Error('Catalog response exceeded the supported size.');
        const value=V.catalog(JSON.parse(text));if(serial!==state.serial)return;
        state.catalog=value;$('catalog-state').textContent=value.live?'Live catalog':'Snapshot only';$('catalog-state').dataset.live=String(value.live);
        $('catalog-message').textContent=value.live?'Catalog lookup succeeded. This is not a paid inference or context-window test.':'Live lookup is unavailable. These are saved policy entries, not live availability.';
        $('catalog-source').textContent=value.source;render();
      }catch(error){
        if(serial!==state.serial)return;state.catalog=null;render();$('catalog-state').textContent='Unavailable';delete $('catalog-state').dataset.live;
        $('catalog-message').textContent=error.name==='AbortError'?'The catalog request timed out. Try refreshing.':'Could not load reliable model metadata. Try refreshing or check service status.';
        $('catalog-source').textContent='No previous catalog is being presented as current.';
      }finally{clearTimeout(timeout);if(serial===state.serial){state.controller=null;$('refresh-models').disabled=false;}}
    }
    $('model-search').addEventListener('input',render);$('availability-filter').addEventListener('change',render);$('refresh-models').addEventListener('click',refresh);
    window.addEventListener('pagehide',()=>{invalidate();$('refresh-models').disabled=false;$('catalog-state').textContent='Not checked';$('catalog-source').textContent='';$('catalog-message').textContent='Refresh to check the catalog.';delete $('catalog-state').dataset.live;});
    window.addEventListener('pageshow',event=>{if(event.persisted)refresh();});
    refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();

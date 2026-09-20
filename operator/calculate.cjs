#!/usr/bin/env node
/* Local scenario CLI. Reads only the named JSON file and never contacts a service. */
'use strict';
const fs=require('node:fs');
const {project,defaults}=require('./profit-core.js');
try {
  const args=process.argv.slice(2);
  if(args.includes('--help')) {
    console.log('Usage: node operator/calculate.cjs [operator/scenario.json]\nNo credentials, transactions, network calls or payment collection.');
    process.exit(0);
  }
  if(args.length>1) throw new Error('Expected at most one JSON file path.');
  let scenario={...defaults};
  if(args.length){
    if(fs.statSync(args[0]).size>65536) throw new Error('Scenario file must be at most 64 KiB.');
    scenario=JSON.parse(fs.readFileSync(args[0],'utf8'));
  }
  console.log(JSON.stringify({assumptions:scenario,result:project(scenario),
    zeroTradingVolume:project({...scenario,volumeUsd:0}),
    doubledGnkPrice:project({...scenario,gnkUsd:Number(scenario.gnkUsd)*2})},null,2));
} catch(error) {
  console.error('Scenario rejected: '+error.message);
  process.exitCode=2;
}

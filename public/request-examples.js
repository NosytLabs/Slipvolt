/* Pure example builder: never copies a real credential into an example. */
(function(root) {
  'use strict';
  function example(language, base, model, maxTokens, outputCeiling = 4096) {
    if (!['curl','python','javascript'].includes(language)) throw new Error('Unsupported example language');
    if (!Number.isSafeInteger(outputCeiling) || outputCeiling < 1 || outputCeiling > 1048576 ||
        !Number.isSafeInteger(maxTokens) || maxTokens < 1 || maxTokens > outputCeiling) throw new Error('Invalid output budget');
    const endpoint = new URL(base);
    if (!['http:', 'https:'].includes(endpoint.protocol) || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) throw new Error('Invalid API base URL');
    if (typeof model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,149}$/.test(model)) throw new Error('Invalid model ID');
    base=base.replace(/\/+$/, '');
    const payload = {model, messages:[{role:'user',content:'Hello!'}], max_tokens:maxTokens, stream:false};
    const q = value => JSON.stringify(value);
    if (language === 'python') return `import os\nfrom openai import OpenAI\n\napi_key = (os.environ.get("HOLDBYTE_API_KEY") or os.environ.get("SLIPVOLT_API_KEY") or "").strip()\nif not api_key:\n    raise RuntimeError("Set HOLDBYTE_API_KEY or legacy SLIPVOLT_API_KEY")\n\nclient = OpenAI(\n    base_url=${q(base)},\n    api_key=api_key,\n    max_retries=0,  # inspect usage before retrying uncertain failures\n)\nresponse = client.chat.completions.create(\n    model=${q(model)},\n    messages=[{"role": "user", "content": "Hello!"}],\n    max_tokens=${maxTokens},\n)\nprint(response.choices[0].message.content)`;
    if (language === 'javascript') return `const apiKey = (process.env.HOLDBYTE_API_KEY || process.env.SLIPVOLT_API_KEY || "").trim();\nif (!apiKey) throw new Error("Set HOLDBYTE_API_KEY or legacy SLIPVOLT_API_KEY");\n\nconst response = await fetch(${q(base+'/chat/completions')}, {\n  method: "POST",\n  headers: {\n    "Authorization": "Bearer " + apiKey,\n    "Content-Type": "application/json"\n  },\n  body: JSON.stringify(${JSON.stringify(payload,null,2)})\n});\nif (!response.ok) throw new Error(await response.text());\nconsole.log((await response.json()).choices[0].message.content);`;
    const body=JSON.stringify(payload,null,2).replace(/'/g, "'\\''");
    const shellUrl=(base+'/chat/completions').replace(/'/g, "'\\''");
    return `HOLDBYTE_API_KEY="\${HOLDBYTE_API_KEY:-\${SLIPVOLT_API_KEY:-}}"\n: "\${HOLDBYTE_API_KEY:?Set HOLDBYTE_API_KEY or legacy SLIPVOLT_API_KEY}"\ncurl --fail-with-body --retry 0 '${shellUrl}' \\\n  -H "Authorization: Bearer $HOLDBYTE_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${body}'`;
  }
  root.SlipvoltExamples={example};
  if(typeof module==='object'&&module.exports) module.exports={example};
})(typeof globalThis==='object'?globalThis:this);

/* Pure example builder: never copies a real credential into an example. */
(function(root) {
  'use strict';
  function example(language, base, model, maxTokens) {
    if (!['curl','python','javascript'].includes(language)) throw new Error('Unsupported example language');
    if (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > 16384) throw new Error('Invalid output budget');
    const payload = {model, messages:[{role:'user',content:'Hello!'}], max_tokens:maxTokens, stream:false};
    const q = value => JSON.stringify(value);
    if (language === 'python') return `import os\nfrom openai import OpenAI\n\nclient = OpenAI(\n    base_url=${q(base)},\n    api_key=os.environ["SLIPVOLT_API_KEY"],\n    max_retries=0,  # inspect usage before retrying uncertain failures\n)\nresponse = client.chat.completions.create(\n    model=${q(model)},\n    messages=[{"role": "user", "content": "Hello!"}],\n    max_tokens=${maxTokens},\n)\nprint(response.choices[0].message.content)`;
    if (language === 'javascript') return `const response = await fetch(${q(base+'/chat/completions')}, {\n  method: "POST",\n  headers: {\n    "Authorization": "Bearer " + process.env.SLIPVOLT_API_KEY,\n    "Content-Type": "application/json"\n  },\n  body: JSON.stringify(${JSON.stringify(payload,null,2)})\n});\nif (!response.ok) throw new Error(await response.text());\nconsole.log((await response.json()).choices[0].message.content);`;
    const body=JSON.stringify(payload,null,2).replace(/'/g, "'\\''");
    return `curl --retry 0 ${base}/chat/completions \\\n  -H "Authorization: Bearer $SLIPVOLT_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${body}'`;
  }
  root.SlipvoltExamples={example};
  if(typeof module==='object'&&module.exports) module.exports={example};
})(typeof globalThis==='object'?globalThis:this);

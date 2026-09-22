"""Bound complex inputs and reserve all requested completions before dispatch.

The byte admission estimate is deliberately conservative, NOT an exact tokenizer
for every model. It may reject a request that the model could otherwise fit.
No prompt is silently truncated and no customer is billed from this estimate.
"""
import json
import re

TEMPLATE_DENY = {'chat_template','tokenize','tools','documents','conversation',
    'continue_final_message','padding','truncation','max_length','return_tensors','return_dict'}


def input_budget(payload):
    # Include tool schemas, roles, prior reasoning and other serialized inputs.
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    return len(encoded) + 1024 + 32 * len(payload.get('messages', []))


def bounded_object(obj, *, max_nodes=256):
    if len(json.dumps(obj, ensure_ascii=False, allow_nan=False).encode()) > 16384:
        raise ValueError('Structured fields must fit within 16 KiB')
    stack=[(obj,0)];nodes=0
    while stack:
        value,depth=stack.pop();nodes+=1
        if nodes>max_nodes or depth>16:raise ValueError('Structured field complexity limit exceeded')
        if isinstance(value,dict):
            if {'$ref','$defs','definitions'} & value.keys():raise ValueError('Schema references are not supported')
            for k,v in value.items():
                if k=='pattern' and (not isinstance(v,str) or len(v.encode())>512):
                    raise ValueError('Schema pattern exceeds 512 bytes')
                if k=='enum' and isinstance(v,list) and len(v)>256:raise ValueError('Schema enum is too large')
                if k in ('anyOf','oneOf','allOf') and isinstance(v,list) and len(v)>16:raise ValueError('Too many schema branches')
                stack.append((v,depth+1))
        elif isinstance(value,list):stack.extend((v,depth+1) for v in value)


def validate_extensions(body):
    if body.response_format is not None and body.structured_outputs is not None:
        raise ValueError('Choose either response_format or structured_outputs, not both')
    if body.chat_template_kwargs is not None:
        if TEMPLATE_DENY & body.chat_template_kwargs.keys():raise ValueError('Unsafe chat template override')
        bounded_object(body.chat_template_kwargs,max_nodes=128)
    for obj in (body.response_format,body.structured_outputs):
        if obj is not None:bounded_object(obj)
    names=set()
    for tool in body.tools or []:
        f=tool.get('function')
        if tool.get('type')!='function' or not isinstance(f,dict):raise ValueError('Only function tools are supported')
        name=f.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):raise ValueError('Invalid function name')
        if name in names:raise ValueError('Duplicate function tool name')
        names.add(name)
        if f.get('parameters') is not None:
            if not isinstance(f['parameters'],dict):raise ValueError('Function parameters must be an object')
            bounded_object(f['parameters'])
    for message in body.messages:
        if isinstance(message.content,list):
            for part in message.content:
                if part.get('type')!='text' or not isinstance(part.get('text'),str):raise ValueError('Only text content parts are supported')
        ids=[call.get('id') for call in message.tool_calls or []]
        if ids and (any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids)):
            raise ValueError('Tool-call IDs must be non-empty and unique in a message')

"""ASGI request body size/nesting guard, independent of route construction."""
from fastapi.responses import JSONResponse


class BodyLimitMiddleware:
    """Bound request buffering even when Content-Length is absent or forged."""
    def __init__(self, app, limit=131072):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type']!='http' or scope.get('method') not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        messages=[]; size=0; depth=0; in_string=False; escaped=False
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            if message['type']!='http.request': continue
            chunk=message.get('body',b'');size+=len(chunk)
            if size>self.limit:
                return await JSONResponse({'error':{'message':'Request too large'}},status_code=413)(scope,receive,send)
            # Gonka caps request JSON nesting at 32. Scan raw bytes so deeply nested
            # objects are rejected before Starlette/Pydantic allocates the parsed tree.
            for byte in chunk:
                if in_string:
                    if escaped:escaped=False
                    elif byte==92:escaped=True
                    elif byte==34:in_string=False
                    continue
                if byte==34:in_string=True
                elif byte in (123,91):
                    depth+=1
                    if depth>32:
                        return await JSONResponse({'error':{'message':'Request nesting exceeds the 32-level limit'}},status_code=400)(scope,receive,send)
                elif byte in (125,93):depth=max(0,depth-1)
            messages.append(message)
            if not message.get('more_body',False): break
        index=0
        async def replay():
            nonlocal index
            if index<len(messages):
                result=messages[index]; index+=1; return result
            return await receive()
        await self.app(scope,replay,send)

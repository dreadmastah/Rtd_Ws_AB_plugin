"""Opt-in observer adapter around the RC2 approved market-data engine.

No filesystem work or awaits in recorder calls. The middleware observes each
HTTP attempt, including aiohttp retries/redirects, after the R15B pacing gate.
The recorded boundary is handler entry, never claimed to be a wire timestamp.
"""
from contextvars import ContextVar
import aiohttp
if __package__:
    from Binance.sender import Sender
    from Binance.rest_telemetry import RestTelemetry, MAX_COUNTER
else:
    from sender import Sender
    from rest_telemetry import RestTelemetry, MAX_COUNTER


class TelemetrySender(Sender):
    def __init__(self, args, session, rest_telemetry=None, diagnostics=None):
        if rest_telemetry is not None and type(rest_telemetry) is not RestTelemetry:
            raise TypeError('Only the bounded recorder is supported')
        self.rest_telemetry=rest_telemetry
        self._rest_telemetry_failures=0
        self._observation=ContextVar('rest_observation',default=None)
        self._role=ContextVar('rest_role',default='HISTORY')
        super().__init__(args,session,diagnostics=diagnostics)
        # Disposable simulated sessions do not implement aiohttp middleware.
        # This adapter preserves their context-manager contract for fixtures.
        if not isinstance(session,aiohttp.ClientSession) and rest_telemetry is not None:
            self.session=_ObservedSession(session,self)

    def _observe(self,method,*args):
        if self.rest_telemetry is None:return None
        try:return getattr(self.rest_telemetry,method)(*args)
        except Exception:
            self._rest_telemetry_failures=min(MAX_COUNTER,self._rest_telemetry_failures+1)
            return None

    def _begin(self,request=None):
        try:return self._begin_record(request)
        except Exception:
            self._rest_telemetry_failures=min(MAX_COUNTER,self._rest_telemetry_failures+1)
            return None

    def _begin_record(self,request=None):
        context=self._observation.get()
        if context is None:return None
        path,params,counter=context
        if request is not None:
            path=request.url.path
            params={key:request.url.query.get(key) for key in ('interval','limit')}
        role=self._role.get()
        request_class=('STARTUP' if path=='/fapi/v1/exchangeInfo' else
                       ('DAILY_REPAIR' if params.get('interval')=='1d' else 'MINUTE_REPAIR') if role=='REPAIR' else role)
        token=self._observe('begin',path,params,request_class,counter[0],False)
        if token is not None:
            self.rest_telemetry.records[token]['boundary']='BEFORE_HTTP_HANDLER_NOT_WIRE_SEND' if request is not None else 'BEFORE_SIMULATED_RESPONSE_ENTRY'
        counter[0]+=1
        return token

    def _response(self,token,response):
        delay=None
        try:
            if response.status in (418,429):delay=max(60 if response.status==418 else 1,float(response.headers.get('Retry-After',60)))
            self._observe('response',token,response.status,response.headers,delay)
        except Exception:self._rest_telemetry_failures=min(MAX_COUNTER,self._rest_telemetry_failures+1)

    async def _paced_rest_attempt(self,request,handler):
        async def observed(req):
            token=self._begin(req)
            try:
                response=await handler(req)
                self._response(token,response)
                return response
            finally:self._observe('finish',token)
        return await super()._paced_rest_attempt(request,observed)

    async def rest(self,path,**params):
        token=self._observation.set((path,params,[0]))
        try:return await super().rest(path,**params)
        finally:self._observation.reset(token)

    async def repair_one(self,ws):
        token=self._role.set('REPAIR')
        try:return await super().repair_one(ws)
        finally:self._role.reset(token)

    async def repair_step(self, ws, *args, **kwargs):
        # R6A invokes repair_step directly, including between preload pages.
        token = self._role.set('REPAIR')
        try:
            return await super().repair_step(ws, *args, **kwargs)
        finally:
            self._role.reset(token)

    async def native_history(self,ws,symbol):
        token=self._role.set('PRELOAD')
        try:return await super().native_history(ws,symbol)
        finally:self._role.reset(token)

    def rest_telemetry_snapshot(self):
        if self.rest_telemetry is None:return None
        value=self.rest_telemetry.snapshot()
        value['sender_observer_failures']=self._rest_telemetry_failures
        return value


class _ObservedSession:
    def __init__(self,session,owner):self.session,self.owner=session,owner
    def get(self,*args,**kwargs):
        underlying=self.session.get(*args,**kwargs);owner=self.owner
        class Response:
            async def __aenter__(self):
                self.token=owner._begin()
                try:
                    value=await underlying.__aenter__();owner._response(self.token,value);return value
                except BaseException:
                    owner._observe('finish',self.token);raise
            async def __aexit__(self,*args):
                try:return await underlying.__aexit__(*args)
                finally:owner._observe('finish',self.token)
        return Response()

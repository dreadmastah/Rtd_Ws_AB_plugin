import json
from admission import Refused
class Handoff:
 def __init__(self,backend,pipeline):
  self.backend=backend;self.pipeline=pipeline
  c=backend.control.c
  if pipeline.session!=c['producer_session'] or pipeline.universe!=c['universe_version'] or pipeline.receiver.symbols!=frozenset(c['symbols']):raise Refused('pipeline binding')
 def receive_one(self):
  body=self.backend.receive()
  def unique(pairs):
   d={}
   for k,v in pairs:
    if k in d:raise Refused('duplicate JSON key')
    d[k]=v
   return d
  try:
   raw=json.loads(body,object_pairs_hook=unique)
   if type(raw)is not dict:raise Refused('source root')
   c=self.backend.control.c
   if self.pipeline.session!=c['producer_session'] or self.pipeline.universe!=c['universe_version'] or self.pipeline.receiver.symbols!=frozenset(c['symbols']):raise Refused('pipeline authority changed')
   if raw.get('s') not in self.backend.subscribed:raise Refused('unsolicited symbol')
   packet=self.pipeline.encode(raw)
   result=self.pipeline.receive(packet)
   if result.startswith('INVALID'):raise Refused(result)
   return result,packet
  except Exception:
   self.backend.shutdown();raise

"""Explicit isolated one-symbol startup. No receiver-arrival trigger or legacy fallback."""
import hashlib,json,os
from admission import Refused
from custody import Attestation
from network import Backend
class ControlledSession:
 def __init__(self,ledger,endpoint,expected_receiver,expected_producer,approved_contract_hash):
  digest=hashlib.sha256(json.dumps(ledger.c,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  if digest!=approved_contract_hash or ledger.c['symbols']!=['BTCUSDT']:raise Refused('explicit one-symbol authority required')
  if expected_producer['pid']!=os.getpid():raise Refused('producer must own this backend process')
  self.producer=self.receiver=None;self.backend=None
  try:
   self.producer=Attestation(expected_producer['pid'],expected_producer)
   self.receiver=Attestation(expected_receiver['pid'],expected_receiver)
   if (expected_receiver['pid'],expected_receiver['creation'])!=(ledger.c['receiver_pid'],ledger.c['receiver_creation']):raise Refused('receiver ledger binding')
   self.ledger=ledger
   self.backend=Backend(ledger,{k:ledger.c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')},endpoint)
  except BaseException:self.close();raise
 def start(self):
  try:self.producer.check();self.receiver.check();self.backend.connect_ws(False);self.backend.subscribe('BTCUSDT')
  except BaseException:self.close();raise
 def read(self):
  try:
   self.producer.check();self.receiver.check();event=self.backend.receive()
   self.producer.check();self.receiver.check();return event
  except BaseException:self.backend.shutdown();raise
 def close(self):
  if self.backend:self.backend.shutdown();self.backend=None
  if self.receiver:self.receiver.close();self.receiver=None
  if self.producer:self.producer.close();self.producer=None

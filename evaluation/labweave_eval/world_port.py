"""Trusted world seam shared by synthetic and authenticated live adapters."""
from typing import Protocol
from copy import deepcopy
from .contract import CONTRACT, Rejection

class WorldPort(Protocol):
    def validate_context(self, context): ...
    def authorize_read(self, context, project_id, target): ...
    def available_actions(self, context): ...
    def execute(self, context, request): ...

class ActionBroker:
    """Tool availability is enforced here; server grants remain independent.

    Revoking an offered capability also blocks a previously prepared decision.
    This is a trusted broker, never copied into participant input directories.
    """
    def __init__(self, world):
        self.world=world;self._removed={};self.audit=[]
    def validate_context(self, context):return self.world.validate_context(context)
    def authorize_read(self, context, project_id, target):
        if 'A01' not in self.available_actions(context):raise Rejection('CAPABILITY_UNAVAILABLE')
        return self.world.authorize_read(context,project_id,target)
    def available_actions(self, context):
        self.validate_context(context)
        return sorted(set(self.world.available_actions(context))-self._removed.get(id(context),set()))
    def remove_capability(self, context, action_id):
        self.validate_context(context);self._removed.setdefault(id(context),set()).add(action_id)
    def execute(self, context, request):
        action=request.get('action',{}).get('id') if isinstance(request,dict) else None
        if action not in self.available_actions(context):
            self.audit.append({'boundary':'harness_capability','action':action,'forwarded':False,'principal_id':context.principal_id})
            return {'contract_version':CONTRACT,'status':'rejected','operation_id':request.get('operation_id') if isinstance(request,dict) else None,'replayed':False,'result':None,'error':{'code':'CAPABILITY_UNAVAILABLE','retryable':False,'message':'Trusted broker did not forward this action'},'trace_id':'broker:capability-denied'}
        self.audit.append({'boundary':'world_dispatch','action':action,'forwarded':True,'principal_id':context.principal_id})
        return self.world.execute(context,deepcopy(request))

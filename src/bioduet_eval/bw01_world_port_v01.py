"""BW-01 WorldPort seam using the existing trusted ActionBroker.

This is an explicitly scoped BW-01 envelope, not full research-action/0.1
conformance. The controller owns contexts and clock. In-process identity checks
are not an OS sandbox; never expose this object to participant processes.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4

from .contract import REGISTRY, Rejection
from .world_port import ActionBroker
from .bw01_logical_v01 import safe_copy

CONTRACT = 'bioduet-bw01-world-port/0.1'


@dataclass(frozen=True, eq=False)
class BoundContext:
    principal_id: str
    project_id: str
    episode_id: str
    actor: str


class ScienceWorldPort:
    def __init__(self, world):
        self.world = world
        self.project_id = uuid4().hex
        self.episode_id = uuid4().hex
        self._contexts = {}
        self.audit = []

    def issue_context(self, actor):
        if type(actor) is not str or actor not in ('A', 'H') or actor in self._contexts:
            raise Rejection('CONTEXT_ISSUANCE')
        context = BoundContext(uuid4().hex, self.project_id, self.episode_id, actor)
        self._contexts[actor] = context
        return context

    def validate_context(self, context):
        if not any(context is known for known in self._contexts.values()):
            raise Rejection('CONTEXT_NOT_ISSUED')
        if self.world.tick >= self.world.expires_at:
            raise Rejection('CONTEXT_EXPIRED')

    def available_actions(self, context):
        self.validate_context(context)
        return self.world.available_actions(context.actor)

    def authorize_read(self, context, project_id, target):
        self.validate_context(context)
        if project_id != self.project_id or target != 'world':
            raise Rejection('READ_SCOPE')
        return {'status': 'succeeded', 'observation': self.world.observe(context.actor)}

    def envelope(self, context, request):
        self.validate_context(context)
        request = safe_copy(request)
        if (type(request) is not dict or type(request.get('action_id')) is not str
                or request['action_id'] not in REGISTRY):
            raise Rejection('ACTION_SCHEMA')
        action = request['action_id']
        return {'contract_version': CONTRACT, 'project_id': self.project_id,
                'episode_id': self.episode_id,
                'action': {'id': action, 'name': REGISTRY[action]['name'], 'version': 'a1'},
                'request': request}

    def execute(self, context, envelope):
        self.validate_context(context)
        value = safe_copy(envelope)
        if (type(value) is not dict or set(value) !=
                {'contract_version', 'project_id', 'episode_id', 'action', 'request'}
                or value['contract_version'] != CONTRACT
                or value['project_id'] != self.project_id
                or value['episode_id'] != self.episode_id
                or type(value['request']) is not dict):
            raise Rejection('ENVELOPE_SCOPE_OR_SCHEMA')
        original = value['request']
        if self.envelope(context, original) != value:
            raise Rejection('ACTION_BINDING')
        # No role, operation ID, label, evidence or scientific choice is filled.
        result = self.world.execute(context.actor, original)
        self.audit.append({'tick': self.world.tick, 'actor': context.actor,
                           'request': deepcopy(original), 'result': deepcopy(result)})
        return result


class BrokeredScienceWorld:
    """LogicalSession-compatible wrapper with persistent per-role capabilities."""
    def __init__(self, world):
        self._port = ScienceWorldPort(world)
        self._contexts = {a: self._port.issue_context(a) for a in ('A', 'H')}
        self._broker = ActionBroker(self._port)

    def __getattr__(self, name):
        # Controller-only delegation. Observations use the explicit method below.
        return getattr(self._port.world, name)

    @property
    def broker_audit(self):
        return deepcopy(self._broker.audit)

    @property
    def port_audit(self):
        return deepcopy(self._port.audit)

    def _context(self, actor):
        if type(actor) is not str or actor not in self._contexts:
            raise Rejection('ACTOR')
        return self._contexts[actor]

    def advance(self, tick):
        return self._port.world.advance(tick)

    def available_actions(self, actor):
        context = self._context(actor)
        try:
            return self._broker.available_actions(context)
        except Rejection as error:
            if error.code == 'CONTEXT_EXPIRED':
                return []
            raise

    def observe(self, actor):
        context = self._context(actor)
        if self._port.world.tick >= self._port.world.expires_at:
            return {'status': 'access_expired'}
        try:
            return self._broker.authorize_read(context, self._port.project_id, 'world')['observation']
        except Rejection as error:
            if error.code == 'CAPABILITY_UNAVAILABLE':
                return {'status': 'read_capability_unavailable'}
            raise

    def remove_capability(self, actor, action):
        if type(action) is not str or action not in REGISTRY:
            raise Rejection('ACTION')
        self._broker.remove_capability(self._context(actor), action)

    def execute(self, actor, request):
        try:
            context = self._context(actor)
            envelope = self._port.envelope(context, request)
            result = self._broker.execute(context, envelope)
        except Rejection as error:
            return {'status': 'rejected', 'reason': error.code}
        # ActionBroker's common capability-denied receipt is kept in its audit;
        # LogicalSession receives the unchanged BW-01 status/reason vocabulary.
        if result.get('contract_version') == 'research-action/0.1':
            return {'status': 'rejected', 'reason': result['error']['code']}
        return result

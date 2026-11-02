"""BW-01 engineering interaction kernel; no model or science claims.

Separate profile, not an implementation of the public research-action contract.
The trusted runner owns the clock and context. In-process projections are not
an OS sandbox. Scientific actions live in the separate scientific world module.
"""
from copy import deepcopy
import json
from uuid import uuid4

PROFILE = 'bw01-interaction-engineering/0.1'
MAX_INT = 2**31 - 1


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise ValueError('INVALID_INTEGER')
    return value


def safe_copy(value, max_bytes=65536, max_depth=20):
    def check(x, depth=0):
        if depth > max_depth:
            raise ValueError('TOO_DEEP')
        if x is None or type(x) is bool or type(x) is str:
            return
        if type(x) is int:
            integer(x)
        elif type(x) is list:
            for item in x:
                check(item, depth + 1)
        elif type(x) is dict and all(type(k) is str for k in x):
            for item in x.values():
                check(item, depth + 1)
        else:
            raise ValueError('INVALID_JSON_TYPE')
    check(value)
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    if len(encoded) > max_bytes:
        raise ValueError('TOO_LARGE')
    return json.loads(encoded)


class LogicalSession:
    """One outstanding turn; bounded fair scheduling at action boundaries.

    world.advance(tick), observe(actor), available_actions(actor), execute(actor,
    request) use a single trusted clock. A real adapter must preserve this port.
    Participant decisions may come from replay or separately isolated model adapters.
    """
    def __init__(self, world, *, deadline=80, max_turns=80):
        self.world = world
        self.episode_id = uuid4().hex
        self.deadline = integer(deadline, 1)
        self.max_turns = integer(max_turns, 1)
        if self.max_turns > 128:
            raise ValueError("TURN_LIMIT_TOO_LARGE")
        self.tick = 0
        self.seq = 0
        self.ready = {'A': 0, 'H': 0}
        self.served = {'A': -2, 'H': -1}
        self.inbox = {'A': [], 'H': []}
        self.records = []
        self.pending = None
        self.terminal = None

    def next_turn(self):
        if self.pending is not None:
            raise RuntimeError('TURN_PENDING')
        if self.terminal is not None:
            return None
        # The last allowed action may finish the last participant.
        if not self.ready:
            self.terminal = 'participants_finished'
            return None
        if self.seq >= self.max_turns:
            self.terminal = 'budget_exhausted'
            return None
        actor = min(self.ready, key=lambda a: (self.ready[a], self.served[a], a))
        self.tick = max(self.tick, self.ready[actor])
        if self.tick >= self.deadline:
            self.terminal = 'deadline'
            return None
        try:
            stage = 'advance'
            self.world.advance(self.tick)
            stage = 'observe'
            observation = self.world.observe(actor)
            stage = 'available_actions'
            available_actions = self.world.available_actions(actor)
            stage = 'packet_validation'
            packet = safe_copy({
                'profile': getattr(self.world, 'profile', PROFILE), 'episode_id': self.episode_id, 'actor': actor, 'tick': self.tick,
                'turn_token': f'{self.episode_id}:{actor}:{self.seq}',
                'observation': observation,
                'available_actions': available_actions,
                'messages': self.inbox[actor],
                'remaining_turns': self.max_turns - self.seq,
            })
        except Exception as exc:
            self.terminal = 'environment_error'
            self.records.append({'seq': self.seq, 'tick': self.tick, 'actor': actor,
                                 'stage': stage, 'result': {'status': 'environment_error',
                                                          'error_type': type(exc).__name__}})
            self.seq += 1
            return None
        self.inbox[actor] = []
        self.pending = deepcopy(packet)
        return packet

    def submit(self, token, decision):
        if self.pending is None or token != self.pending['turn_token']:
            raise ValueError('STALE_TURN')
        actor = self.pending['actor']
        self.pending = None
        self.served[actor] = self.seq
        self.ready[actor] = self.tick + 1
        record = {'seq': self.seq, 'tick': self.tick, 'actor': actor}
        self.seq += 1
        try:
            decision = safe_copy(decision)
            if type(decision) is not dict:
                raise ValueError('DECISION_OBJECT_REQUIRED')
            kind = decision.get('kind')
            fields = {'action': {'kind', 'request'}, 'message': {'kind', 'to', 'text'},
                      'wait': {'kind', 'until'}, 'finish': {'kind'}}
            if type(kind) is not str or kind not in fields or set(decision) != fields[kind]:
                raise ValueError('DECISION_SCHEMA')
            record['decision'] = deepcopy(decision)
            if kind == 'wait':
                self.ready[actor] = integer(decision['until'], self.tick + 1)
                result = {'status': 'waiting'}
            elif kind == 'finish':
                del self.ready[actor]
                result = {'status': 'finished'}
            elif kind == 'message':
                target, text = decision['to'], decision['text']
                if type(target) is not str or target not in self.inbox or target == actor or type(text) is not str or not 1 <= len(text) <= 4096:
                    raise ValueError('MESSAGE_SCHEMA')
                if len(self.inbox[target]) >= 16 or sum(len(m["text"]) for m in self.inbox[target]) + len(text) > 16384:
                    raise ValueError("MESSAGE_QUEUE_FULL")
                self.inbox[target].append({'from': actor, 'sent_tick': self.tick,
                                           'source_kind': 'participant_statement', 'text': text})
                result = {'status': 'message_queued'}
            else:
                if type(decision['request']) is not dict:
                    raise ValueError('ACTION_OBJECT_REQUIRED')
                # The world is a trusted boundary, not participant validation.
                # Its exceptions (including ValueError) and invalid outputs stop
                # the episode without disclosing exception messages or results.
                try:
                    stage = 'world_execute'
                    raw_result = self.world.execute(actor, decision['request'])
                    stage = 'world_result_validation'
                    result = safe_copy(raw_result)
                except Exception as exc:
                    self.terminal = 'environment_error'
                    result = {'status': 'environment_error', 'error_type': type(exc).__name__,
                              'stage': stage}
            record['result'] = result
        except ValueError as exc:
            record['result'] = {'status': 'rejected', 'reason': str(exc)}
        except Exception as exc:
            self.terminal = 'environment_error'
            record['result'] = {'status': 'environment_error', 'error_type': type(exc).__name__}
        self.records.append(record)
        self.tick += 1
        return deepcopy(record)

    def report(self):
        return safe_copy({'profile': PROFILE, 'episode_id': self.episode_id, 'behavior_source': 'simulated_replay',
                         'time_model': 'logical_time', 'actual_model_calls': 0,
                         'interactive_closed_loop': False,
                         'scientific_validity': 'not_assessed',
                         'formal_benchmark_score': None, 'terminal': self.terminal,
                         'records': self.records}, max_bytes=16*1024*1024, max_depth=32)


class Bw01EngineeringWorld:
    """Synthetic metadata/evidence/design slice; A11 and science are unsupported.

    E01 becomes visible to H after a successful first A06. A02 releases only
    the allowed synthetic certificate. A03 may still be wrong: this world does
    not replace the participant's scientific judgment with the hidden answer.
    """
    def __init__(self, condition='H1', *, expires_at=80):
        if condition not in ('H0', 'H1'):
            raise ValueError('CONDITION')
        self.tick = 0
        self.expires_at = integer(expires_at, 1)
        self.sample = {'id': 'S01', 'version': 1, 'condition': 'stim' if condition == 'H0' else 'control',
                       'claim_status': 'submitted'}
        self.counts = {'id': 'L01', 'version': 1, 'identity': 'synthetic-counts-fixture-not-real-data'}
        self.private_evidence = {'id': 'E01', 'sample_id': 'S01', 'condition': 'stim',
                                 'source_kind': 'synthetic', 'original_ref': 'simulated-log-01'}
        self.evidence_open = False
        self.public_evidence = None
        self.design = None
        self.operations = {}
        self.history = []

    def advance(self, tick):
        integer(tick)
        if tick < self.tick:
            raise ValueError('CLOCK_BACKWARDS')
        self.tick = tick

    def available_actions(self, actor):
        if actor not in ('A', 'H'):
            raise ValueError('ACTOR')
        if self.tick >= self.expires_at:
            return []
        return ['A01', 'A06'] if actor == 'A' else ['A01', 'A02', 'A03']

    def observe(self, actor):
        self.available_actions(actor)
        if self.tick >= self.expires_at:
            return {'status': 'access_expired'}
        view = {'sample': self.sample, 'counts': self.counts,
                'public_evidence': self.public_evidence, 'design': self.design}
        if actor == 'H':
            view['private_evidence'] = self.private_evidence if self.evidence_open else None
        return deepcopy(view)

    def execute(self, actor, request):
        request = safe_copy(request)
        action = request.get('action_id')
        if action not in self.available_actions(actor):
            return {'status': 'rejected', 'reason': 'CAPABILITY_UNAVAILABLE'}
        if action == 'A01':
            if set(request) != {'action_id'}:
                return {'status': 'rejected', 'reason': 'ACTION_SCHEMA'}
            return {'status': 'succeeded', 'observation': self.observe(actor)}
        if set(request) != {'action_id', 'operation_id', 'payload'}:
            return {'status': 'rejected', 'reason': 'ACTION_SCHEMA'}
        op, payload = request['operation_id'], request['payload']
        if type(op) is not str or not 1 <= len(op) <= 128 or type(payload) is not dict:
            return {'status': 'rejected', 'reason': 'ACTION_SCHEMA'}
        key = (actor, op)
        signature = json.dumps(request, sort_keys=True)
        if key in self.operations:
            old_sig, old_result = self.operations[key]
            return deepcopy(old_result) if old_sig == signature else {'status': 'rejected', 'reason': 'IDEMPOTENCY_CONFLICT'}
        before = deepcopy({'sample': self.sample, 'design': self.design, 'public_evidence': self.public_evidence})
        if action == 'A02':
            if payload != {'evidence_ref': 'E01'} or not self.evidence_open:
                return {'status': 'rejected', 'reason': 'EVIDENCE_UNAVAILABLE'}
            self.public_evidence = deepcopy(self.private_evidence)
            if self.sample['condition'] == self.public_evidence['condition']:
                self.sample['claim_status'] = 'corroborated'
        elif action == 'A03':
            if (set(payload) != {'expected_version', 'condition', 'reason'} or
                    type(payload['expected_version']) is not int or
                    payload['condition'] not in ('stim', 'control') or
                    type(payload['reason']) is not str or not 1 <= len(payload['reason']) <= 1024):
                return {'status': 'rejected', 'reason': 'ACTION_SCHEMA'}
            if payload['expected_version'] != self.sample['version']:
                return {'status': 'rejected', 'reason': 'VERSION_CONFLICT'}
            self.sample['version'] += 1
            self.sample['condition'] = payload['condition']
            self.sample['claim_status'] = ('corroborated' if self.public_evidence and
                                           self.public_evidence['condition'] == payload['condition'] else 'submitted')
        elif action == 'A06':
            if (set(payload) != {'sample_version', 'declared_condition'} or
                    type(payload['sample_version']) is not int or
                    payload['declared_condition'] not in ('stim', 'control')):
                return {'status': 'rejected', 'reason': 'ACTION_SCHEMA'}
            if payload['sample_version'] != self.sample['version']:
                return {'status': 'rejected', 'reason': 'VERSION_CONFLICT'}
            self.design = {'id': 'D01', 'version': (self.design['version'] + 1 if self.design else 1),
                           'sample_version': payload['sample_version'],
                           'declared_condition': payload['declared_condition'], 'status': 'draft'}
            self.evidence_open = True
        result = {'status': 'succeeded', 'operation_id': op, 'sample_version': self.sample['version']}
        self.operations[key] = (signature, deepcopy(result))
        self.history.append({'tick': self.tick, 'actor': actor, 'action_id': action,
                             'before': before, 'after': deepcopy({'sample': self.sample, 'design': self.design,
                                                                'public_evidence': self.public_evidence})})
        return result

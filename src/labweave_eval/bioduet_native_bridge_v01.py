"""Native tool boundary candidate, no engine/provider execution.

Preserves the frozen LogicalSession kernel. Human callable is independent and
receives only its issued packet; this bridge never fills scientific decisions.
"""
from copy import deepcopy

class NativeTurnBridge:
    def __init__(self, session, human_step):
        self.session = session
        self.human_step = human_step
        self.packet = None
        self.started = False
        self.closed = False
        self.native_events = []
        self.environment_failure = None

    def _advance(self):
        while True:
            packet = self.session.next_turn()
            if packet is None:
                self.packet = None
                self.closed = True
                return None
            if packet['actor'] == 'A':
                self.packet = packet
                public = deepcopy(packet)
                del public['turn_token']
                return public
            if packet['actor'] != 'H':
                raise ValueError('UNSUPPORTED_PARTICIPANT')
            try:
                decision = self.human_step(deepcopy(packet))
            except Exception as exc:
                self.environment_failure = {'code': 'HUMAN_STEP_FAILED', 'actor': 'H'}
                self.native_events.append({'kind': 'human_step_failed',
                                           'error_type': type(exc).__name__, 'seq': self.session.seq})
                self.session.records.append({'seq': self.session.seq, 'tick': self.session.tick,
                                             'actor': 'H', 'stage': 'human_step',
                                             'result': {'status': 'environment_error',
                                                        'reason': 'HUMAN_STEP_FAILED'}})
                self.session.seq += 1
                self.session.pending = None
                self.session.terminal = 'environment_error'
                self.packet = None
                self.closed = True
                return None
            self.session.submit(packet['turn_token'], decision)

    def start(self):
        if self.started:
            raise ValueError('ALREADY_STARTED')
        self.started = True
        return self._advance()

    def exchange(self, decision):
        if not self.started or self.closed or self.packet is None:
            raise ValueError('NO_AGENT_TURN')
        token = self.packet['turn_token']
        self.packet = None
        record = self.session.submit(token, decision)
        next_turn = self._advance()
        return {'receipt': record, 'next_turn': next_turn,
                'environment_failure': deepcopy(self.environment_failure)}

    def native_completed(self):
        if not self.started or self.closed or self.packet is None:
            raise ValueError('NO_AGENT_TURN')
        # Native completion maps to participant lifecycle, never a world action.
        self.native_events.append({'kind': 'native_completed', 'seq': self.session.seq})
        return self.exchange({'kind': 'finish'})

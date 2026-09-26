"""Recognize the trusted serving engine's terminal SSE acknowledgment.

Client disconnect alone is never an acknowledgment. All requested choices must
finish before the engine's exact [DONE] frame; model text remains JSON content.
"""
import json

class StreamCompletion:
    def __init__(self, choices):
        self.expected=choices if type(choices) is int and 0 < choices <= 128 else None
        self.finished=set();self.pending=b'';self.failed=False;self.complete=False

    def feed(self, data):
        if self.failed or self.complete or self.expected is None:return
        self.pending=(self.pending+data).replace(b'\r\n',b'\n')
        if len(self.pending)>65536:
            self.failed=True;self.pending=b'';return
        while b'\n\n' in self.pending:
            frame,self.pending=self.pending.split(b'\n\n',1)
            fields=[line[5:].lstrip(b' ') for line in frame.split(b'\n') if line.startswith(b'data:')]
            if not fields:continue
            wire=b'\n'.join(fields)
            if wire==b'[DONE]':
                self.complete=len(self.finished)==self.expected
                if not self.complete:self.failed=True
                return
            try:
                event=json.loads(wire)
                if not isinstance(event,dict) or 'error' in event:raise ValueError()
                for choice in event.get('choices',[]):
                    index=choice.get('index')
                    reason=choice.get('finish_reason')
                    if reason is not None:
                        if type(index) is not int or not 0<=index<self.expected or not isinstance(reason,str) or not reason:raise ValueError()
                        self.finished.add(index)
            except (ValueError,TypeError,AttributeError):
                self.failed=True;self.pending=b'';return

import json,unittest
from aimee_vllm.stream_completion import StreamCompletion

def frame(choices):return b'data: '+json.dumps({'choices':choices}).encode()+b'\n\n'
class StreamTests(unittest.TestCase):
 def test_terminal_frames_can_cross_every_byte_boundary(self):
  raw=frame([{'index':0,'finish_reason':'stop'}])+b'data: [DONE]\n\n'
  for split in range(len(raw)+1):
   tracker=StreamCompletion(1);tracker.feed(raw[:split]);tracker.feed(raw[split:]);self.assertTrue(tracker.complete,split)
 def test_all_choices_must_finish_before_done(self):
  tracker=StreamCompletion(2);tracker.feed(frame([{'index':0,'finish_reason':'stop'}])+b'data: [DONE]\n\n');self.assertFalse(tracker.complete)
  tracker=StreamCompletion(2);tracker.feed(frame([{'index':1,'finish_reason':'length'}]));tracker.feed(frame([{'index':0,'finish_reason':'stop'}]));tracker.feed(b'data: [DONE]\n\n');self.assertTrue(tracker.complete)
 def test_model_text_error_and_partial_completion_cannot_acknowledge(self):
  for raw in [frame([{'index':0,'finish_reason':None,'delta':{'content':'\n\ndata: [DONE]\n\n'}}]), b'data: {"error":{"message":"failed"}}\n\ndata: [DONE]\n\n',frame([{'index':0,'finish_reason':'stop'}]),b'data: [DONE]\n\n']:
   tracker=StreamCompletion(1);tracker.feed(raw);self.assertFalse(tracker.complete)
 def test_parser_bounds_and_invalid_choice_fail_closed(self):
  for raw in [b'x'*65537,frame([{'index':9,'finish_reason':'stop'}]),frame([{'index':False,'finish_reason':'stop'}])]:
   tracker=StreamCompletion(1);tracker.feed(raw);tracker.feed(frame([{'index':0,'finish_reason':'stop'}])+b'data: [DONE]\n\n');self.assertFalse(tracker.complete)
if __name__=='__main__':unittest.main()

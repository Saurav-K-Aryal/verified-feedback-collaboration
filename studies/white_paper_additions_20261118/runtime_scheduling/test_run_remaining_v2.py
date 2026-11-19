"""CPU-only operational guard checks. No subprocesses, inference or signals."""
import json
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import Mock,MagicMock,patch,call
import run_remaining_v2 as v
b=v.b


def controller():
    plan={'hard_stop_utc':b.datetime.fromtimestamp(time.time()+1000,b.timezone.utc).isoformat(),
          'primary':{'pid':123,'identity':'primary-original'}}
    with patch.object(b,'read',side_effect=lambda path,default=None:default):return v.ControllerV2(plan)


def add(c,name,pid):
    record={'stage':name,'pid':pid,'pgid':pid,'identity':'identity-'+str(pid),'controller_owned':True,
            'stage_deadline_epoch':time.time()+500,'paused':False}
    process=Mock();process.poll.return_value=None
    c.parallel[name]=(record,process);c.state['stages'][name]={'status':'running','process':record}
    return record,process


class Guards(unittest.TestCase):
    def test_transient_runner_and_listener_shutdown_gets_bounded_grace(self):
        c=controller();clock=[0.]
        with patch.object(v,'process_group_members',side_effect=[[78],[],[]]),patch.object(v,'isolated_listener_exists',side_effect=[True,True,False]),patch.object(b.time,'monotonic',side_effect=lambda:clock[0]),patch.object(b.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)),patch.object(b,'signal_owned') as signal:
            self.assertTrue(c.wait_server_quiescence(77));self.assertAlmostEqual(clock[0],.4);signal.assert_not_called()

    def test_persistent_runner_stops_waiting_at_fifteen_seconds(self):
        c=controller();clock=[0.]
        with patch.object(v,'process_group_members',return_value=[78]),patch.object(v,'isolated_listener_exists',return_value=False),patch.object(b.time,'monotonic',side_effect=lambda:clock[0]),patch.object(b.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)),patch.object(b,'signal_owned') as signal:
            self.assertFalse(c.wait_server_quiescence(77));self.assertAlmostEqual(clock[0],15);signal.assert_not_called()

    def test_cleanup_grace_does_not_extend_hard_deadline(self):
        c=controller();clock=[0.];c.hard=102.
        with patch.object(v,'process_group_members',return_value=[]),patch.object(v,'isolated_listener_exists',return_value=True),patch.object(b.time,'time',return_value=100.),patch.object(b.time,'monotonic',side_effect=lambda:clock[0]),patch.object(b.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            self.assertFalse(c.wait_server_quiescence(77));self.assertAlmostEqual(clock[0],2)

    def test_benchmark_power_pause_invalidates_gate(self):
        c=controller();c.current={'stage':'free_gpu_benchmark'}
        result={'supervisor_exit_code':0,'complete_blocks':4,'errors':0,'selected_mode':'two_per_model'}
        with patch.object(b.Controller,'power',return_value=False),patch.object(c,'persist'),patch.object(b,'event'),patch.object(b,'read',return_value=result):
            c.power();self.assertTrue(c.state['benchmark_interrupted_by_power']);self.assertFalse(c.ready('free_gpu_benchmark'))

    def test_surviving_runner_blocks_server_cleanup_success(self):
        c=controller();c.server={'pid':77,'pgid':77}
        with patch.object(b,'owned_process',return_value=False),patch.object(b,'process_exists',return_value=False),patch.object(c,'wait_server_quiescence',return_value=False),patch.object(c,'persist_server'),patch.object(b,'event'):
            with self.assertRaisesRegex(RuntimeError,'survives the cleanup window'):c.stop_server('test')

    def test_isolated_server_pauses_and_resumes_with_power(self):
        c=controller();c.server={'stage':'isolated_server','pid':77,'paused':False}
        with patch.object(b.Controller,'power',side_effect=[False,True]),patch.object(b,'owned_process',return_value=True),patch.object(c,'persist_server'),patch.object(b,'signal_owned') as sig:
            self.assertFalse(c.power());self.assertTrue(c.power())
            self.assertEqual([x.args[1] for x in sig.call_args_list],[signal.SIGSTOP,signal.SIGCONT])

    def test_isolated_server_identity_loss_stops_new_work(self):
        c=controller();c.server={'pid':77}
        with patch.object(b.Controller,'power',return_value=True),patch.object(b,'owned_process',return_value=False),patch.object(b,'signal_owned') as sig:
            with self.assertRaisesRegex(RuntimeError,'identity is no longer verified'):c.power()
            sig.assert_not_called()

    def test_server_reaped_before_exit_verification(self):
        c=controller();c.server={'pid':77,'pgid':77};c.server_process=Mock();order=[]
        c.server_process.wait.side_effect=lambda timeout:order.append('wait')
        def exists(pid):order.append('check');return False
        with patch.object(b,'owned_process',return_value=False),patch.object(b,'process_exists',side_effect=exists),patch.object(v,'process_group_members',return_value=[]),patch.object(v,'isolated_listener_exists',return_value=False),patch.object(c,'persist_server'),patch.object(b,'event'):
            c.stop_server('test');self.assertEqual(order,['wait','check']);self.assertIsNone(c.server)

    def test_bound_isolated_port_prevents_server_spawn(self):
        import socket
        c=controller();probe=MagicMock();probe.__enter__.return_value.connect_ex.return_value=0
        with patch.object(b,'read',return_value={}),patch.object(socket,'socket',return_value=probe),patch.object(b.subprocess,'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError,'unowned listener'):c.start_server()
            popen.assert_not_called()

    def test_serial_mode_does_not_release_phi_after_only_timing(self):
        c=controller();c.mode='serial';add(c,'mistral',11);ticks=[0];called=[]
        def tick():
            ticks[0]+=1
            if ticks[0]==3:c.parallel.clear()
        def start_phi():called.append(ticks[0]);return True
        with patch.object(c,'ready',return_value=False),patch.object(c,'tick_parallel',side_effect=tick),patch.object(v,'overlap_ready',return_value=True),patch.object(c,'start_phi',side_effect=start_phi),patch.object(b,'event'),patch.object(b.time,'sleep'):
            c.generation_pair();self.assertEqual(called,[3])

    def test_drain_failure_blocks_all_detector_work(self):
        c=controller()
        with patch.object(b,'t3_ready',return_value=False),patch.object(c,'drain_generation_models',side_effect=RuntimeError('unknown request')),patch.object(c,'stage') as stage:
            with self.assertRaisesRegex(RuntimeError,'unknown request'):c.post_generation()
            stage.assert_not_called()

    def test_drain_requires_unload_confirmation_and_no_resident_models(self):
        c=controller();responses=[]
        for obj in [{'done':True},{'done':True},{'models':[]}]:
            response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps(obj).encode();responses.append(response)
        with patch.object(b.urllib.request,'urlopen',side_effect=responses) as request,patch.object(b,'event'):
            c.drain_generation_models();self.assertEqual(request.call_count,3)
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{}'
        with patch.object(b.urllib.request,'urlopen',return_value=response),patch.object(b,'event'):
            with self.assertRaisesRegex(RuntimeError,'not confirmed'):c.drain_generation_models()

    def test_normal_negative_gate_is_completed(self):
        result={'supervisor_exit_code':0,'complete_blocks':4,'errors':0,'selected_mode':'serial'}
        self.assertTrue(v.benchmark_complete(result))
        for key,value in [('supervisor_exit_code',2),('complete_blocks',3),('errors',1),('selected_mode',None)]:
            self.assertFalse(v.benchmark_complete({**result,key:value}))

    def test_release_requires_protocol_and_completed_test_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            self.assertFalse(v.overlap_ready(folder))
            (folder/'TEST_PROTOCOL.json').write_text('{}')
            self.assertFalse(v.overlap_ready(folder))
            (folder/'test_calls.jsonl').write_text('{"incomplete":')
            self.assertFalse(v.overlap_ready(folder))
            (folder/'test_calls.jsonl').write_text(json.dumps({'response':{'error':None}})+'\n')
            self.assertTrue(v.overlap_ready(folder))

    def test_live_serial_controller_blocks_handover(self):
        with patch.object(b,'read',return_value={'controller_pid':99,'controller_identity':'same','stages':{}}),patch.object(b,'process_exists',return_value=True),patch.object(b,'process_identity',return_value='same'):
            with self.assertRaisesRegex(RuntimeError,'remains active'):v.require_serial_inactive()

    def test_serial_leftover_child_blocks_handover(self):
        state={'stages':{'mistral':{'process':{'pid':44}}}}
        with patch.object(b,'read',return_value=state),patch.object(b,'process_exists',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'unresolved live child'):v.require_serial_inactive()

    def test_ambiguous_live_child_halts_without_signaling(self):
        c=controller();record,process=add(c,'mistral',11)
        with patch.object(b,'owned_process',return_value=False),patch.object(b,'process_exists',return_value=True),patch.object(c,'persist_parallel'),patch.object(b,'event'),patch.object(b,'signal_owned') as signals:
            with self.assertRaisesRegex(RuntimeError,'identity is ambiguous'):c.tick_parallel()
            signals.assert_not_called();self.assertEqual(c.state['stages']['mistral']['status'],'ambiguous_live')

    def test_pause_resume_both_without_budget_extension(self):
        c=controller();r1,p1=add(c,'mistral',11);r2,p2=add(c,'phi_generate',12)
        deadlines=[r1['stage_deadline_epoch'],r2['stage_deadline_epoch']]
        with patch.object(b,'owned_process',return_value=True),patch.object(c,'power',side_effect=[False,True]),patch.object(c,'persist_parallel'),patch.object(c,'log_progress'),patch.object(b,'signal_owned') as sig:
            c.tick_parallel();c.tick_parallel()
            self.assertEqual([(x.args[0]['stage'],x.args[1]) for x in sig.call_args_list],
                             [('mistral',signal.SIGSTOP),('phi_generate',signal.SIGSTOP),('mistral',signal.SIGCONT),('phi_generate',signal.SIGCONT)])
            self.assertEqual(deadlines,[r1['stage_deadline_epoch'],r2['stage_deadline_epoch']])

    def test_global_deadline_stops_both_before_power_check(self):
        c=controller();add(c,'mistral',11);add(c,'phi_generate',12);c.hard=time.time()-1
        with patch.object(b,'owned_process',return_value=True),patch.object(c,'stop_parallel') as stop,patch.object(c,'power') as power:
            c.tick_parallel();stop.assert_called_once();power.assert_not_called()

    def test_cleanup_notifies_every_group_before_waiting(self):
        c=controller();add(c,'mistral',11);add(c,'phi_generate',12);sequence=[]
        with patch.object(b,'owned_process',return_value=True),patch.object(b,'signal_owned',side_effect=lambda r,s:sequence.append(('signal',r['stage'],s))),patch.object(c,'stop_owned',side_effect=lambda r,why:sequence.append(('wait',r['stage']))):
            c.stop_parallel('test')
        self.assertEqual([x[:2] for x in sequence[:4]],[('signal','mistral'),('signal','mistral'),('signal','phi_generate'),('signal','phi_generate')])
        self.assertTrue(all(x[0]=='wait' for x in sequence[4:]))

    def test_battery_defers_second_launch_without_blocking_monitor(self):
        c=controller();add(c,'mistral',11)
        with patch.object(c,'ready',return_value=False),patch.object(c,'power',return_value=False),patch.object(c,'wait_power') as wait,patch.object(b.subprocess,'Popen') as popen:
            self.assertIsNone(c.start_async('phi_generate',['unused'],time.time()+100))
            wait.assert_not_called();popen.assert_not_called()

    def test_expired_child_never_starts(self):
        c=controller()
        with patch.object(c,'ready',return_value=False),patch.object(b.subprocess,'Popen') as popen:
            self.assertFalse(c.start_async('phi_generate',['unused'],time.time()-1));popen.assert_not_called()

    def test_deadline_rechecked_after_power_wait(self):
        c=controller();clock=[100.];c.hard=1000
        def restore():clock[0]=300.;return True
        with patch.object(b.time,'time',side_effect=lambda:clock[0]),patch.object(c,'ready',return_value=False),patch.object(c,'wait_power',side_effect=restore),patch.object(b.subprocess,'Popen') as popen:
            self.assertFalse(c.start_async('phi_generate',['unused'],200));popen.assert_not_called()

    def test_no_scoring_while_either_generation_client_active(self):
        c=controller();add(c,'phi_generate',12)
        with patch.object(c,'stage') as stage:
            with self.assertRaisesRegex(RuntimeError,'No scoring'):c.post_generation()
            stage.assert_not_called()

    def test_mixed_serial_and_generation_reentry_fails_before_monitor(self):
        c=controller();add(c,'mistral',11)
        c.state['stages']['phi_score']={'status':'running','process':{'pid':22}}
        with patch.object(b,'process_exists',return_value=True),patch.object(c,'monitor') as monitor:
            with self.assertRaisesRegex(RuntimeError,'serial stage overlaps'):c.reconcile()
            monitor.assert_not_called()

    def test_exit_code_without_artifact_does_not_claim_completion(self):
        c=controller();record,process=add(c,'phi_generate',12);process.poll.return_value=0
        with patch.object(c,'ready',return_value=False),patch.object(c,'persist_parallel'),patch.object(c,'log_progress'),patch.object(b,'event'):
            c.tick_parallel()
            self.assertFalse(c.parallel);self.assertEqual(c.state['stages']['phi_generate']['status'],'incomplete_or_failed')

    def test_adoption_keeps_surviving_phi_without_restarting_timing(self):
        c=controller();add(c,'phi_generate',12)
        def finish():c.parallel.clear()
        with patch.object(c,'start_mistral') as start,patch.object(c,'ready',return_value=True),patch.object(c,'tick_parallel',side_effect=finish):
            c.generation_pair();start.assert_not_called()

    def test_generation_waits_for_timing_then_releases_phi(self):
        c=controller();c.mode='one_per_model';add(c,'mistral',11);ticks=[0]
        def tick():
            ticks[0]+=1
            if ticks[0]==3:c.parallel.clear()
        with patch.object(c,'ready',return_value=False),patch.object(c,'tick_parallel',side_effect=tick),patch.object(v,'overlap_ready',side_effect=[False,True,True]),patch.object(c,'start_phi',return_value=True) as phi,patch.object(b,'event'),patch.object(b.time,'sleep'):
            c.generation_pair();phi.assert_called_once();self.assertEqual(ticks[0],3)

if __name__=='__main__':unittest.main(verbosity=2)

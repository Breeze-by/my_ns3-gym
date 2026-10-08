from types import SimpleNamespace
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage
from multi_robot_exploration.tf_ingress_sampler import TfIngressSampler


def sample(parent, child, sec, ns=0):
    t=TransformStamped()
    t.header.frame_id, t.child_frame_id = parent, child
    t.header.stamp.sec, t.header.stamp.nanosec = sec, ns
    return t


def test_native_duplicates_and_base_tf_do_not_starve_fresh_map_odom():
    packets=[];native=[]
    node=SimpleNamespace(last_source_stamp=-1, publisher=SimpleNamespace(publish=packets.append),
                         native_publisher=SimpleNamespace(publish=native.append))
    first=sample('map','odom',10,200000000)
    for _ in range(100):
        TfIngressSampler.observe(node,TFMessage(transforms=[sample('odom','base_link',11)]))
        TfIngressSampler.observe(node,TFMessage(transforms=[first]))
    fresh=sample('map','odom',10,400000000)
    TfIngressSampler.observe(node,TFMessage(transforms=[fresh]))
    TfIngressSampler.observe(node,TFMessage(transforms=[first]))
    assert len(packets)==2
    assert [m.transforms[0].header.stamp.nanosec for m in packets]==[200000000,400000000]
    assert first.header.stamp.sec==10 and first.header.stamp.nanosec==200000000
    assert len(native)==102 and all(len(m.transforms)==1 for m in native)


def test_mixed_tf_batch_forwards_only_newest_relevant_native_transform():
    packets=[];native=[]
    node=SimpleNamespace(last_source_stamp=-1,publisher=SimpleNamespace(publish=packets.append),
                         native_publisher=SimpleNamespace(publish=native.append))
    original=TFMessage(transforms=[sample('/map','/odom',20),sample('odom','base_link',99),sample('/map','/odom',19)])
    TfIngressSampler.observe(node,original)
    assert len(packets)==1 and len(packets[0].transforms)==1
    assert packets[0].transforms[0].header.stamp.sec==20
    assert len(original.transforms)==3
    assert [t.header.stamp.sec for t in native[0].transforms]==[20,19]


def test_native_consumer_gets_valid_samples_after_an_invalid_future_without_gateway_ordering():
    packets=[];native=[]
    node=SimpleNamespace(last_source_stamp=-1,publisher=SimpleNamespace(publish=packets.append),
                         native_publisher=SimpleNamespace(publish=native.append))
    for stamp in (50,60,53,53,51):
        TfIngressSampler.observe(node,TFMessage(transforms=[sample('map','odom',stamp,200000000)]))
    assert [m.transforms[0].header.stamp.sec for m in native]==[50,60,53,53,51]
    assert [m.transforms[0].header.stamp.sec for m in packets]==[50,60]


def test_ap_sampler_packets_are_identical_to_the_previous_frozen_source():
    import ast,subprocess
    from pathlib import Path
    from rclpy.serialization import serialize_message
    root=next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
    path='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/tf_ingress_sampler.py'
    old=ast.parse(subprocess.check_output(['git','show','79f211323ade3e949f91ad3896e727beeeef7522:'+path],cwd=root))
    method=next(n for cls in old.body if isinstance(cls,ast.ClassDef) for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='observe')
    module=ast.Module(body=[method],type_ignores=[]);space={'TFMessage':TFMessage}
    exec(compile(module,'frozen_sampler','exec'),space)
    old_packets=[];new_packets=[];native=[]
    before=SimpleNamespace(last_source_stamp=-1,publisher=SimpleNamespace(publish=old_packets.append))
    after=SimpleNamespace(last_source_stamp=-1,publisher=SimpleNamespace(publish=new_packets.append),
                         native_publisher=SimpleNamespace(publish=native.append))
    for stamp in (10,10,11,9,50,60,53):
        message=TFMessage(transforms=[sample('map','odom',stamp,200000000),sample('odom','base_link',stamp)])
        space['observe'](before,message);TfIngressSampler.observe(after,message)
    assert [serialize_message(m) for m in old_packets]==[serialize_message(m) for m in new_packets]
    assert before.last_source_stamp==after.last_source_stamp and len(native)==7

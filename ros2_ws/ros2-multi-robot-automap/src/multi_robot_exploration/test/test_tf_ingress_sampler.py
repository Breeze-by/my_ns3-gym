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
    packets=[]
    node=SimpleNamespace(last_source_stamp=-1, publisher=SimpleNamespace(publish=packets.append))
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


def test_mixed_tf_batch_forwards_only_newest_relevant_native_transform():
    packets=[]
    node=SimpleNamespace(last_source_stamp=-1,publisher=SimpleNamespace(publish=packets.append))
    original=TFMessage(transforms=[sample('/map','/odom',20),sample('odom','base_link',99),sample('/map','/odom',19)])
    TfIngressSampler.observe(node,original)
    assert len(packets)==1 and len(packets[0].transforms)==1
    assert packets[0].transforms[0].header.stamp.sec==20
    assert len(original.transforms)==3

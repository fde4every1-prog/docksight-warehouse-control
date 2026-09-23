import pytest
from warehouse_control.legacy.allocator import choose_robot

@pytest.mark.xfail(reason='legacy allocator ignores expired safety certification')
def test_allocator_rejects_expired_safety_cert():
    robots=[{'robot_id':'R1','battery_soc':'99','connectivity':'ONLINE','health_status':'HEALTHY','safety_cert_status':'EXPIRED'},
            {'robot_id':'R2','battery_soc':'60','connectivity':'ONLINE','health_status':'HEALTHY','safety_cert_status':'VALID'}]
    assert choose_robot(robots,{})['robot_id']=='R2'

@pytest.mark.xfail(reason='legacy allocator has no payload constraint')
def test_allocator_respects_payload():
    robots=[{'robot_id':'R1','battery_soc':'99','connectivity':'ONLINE','health_status':'HEALTHY','payload_kg':'100'},
            {'robot_id':'R2','battery_soc':'60','connectivity':'ONLINE','health_status':'HEALTHY','payload_kg':'1500'}]
    assert choose_robot(robots,{'payload_kg':1000})['robot_id']=='R2'

@pytest.mark.xfail(reason='legacy allocator is local heuristic, not congestion aware')
def test_allocator_avoids_congested_zone():
    robots=[{'robot_id':'R1','battery_soc':'99','connectivity':'ONLINE','health_status':'HEALTHY','zone':'Z1'},
            {'robot_id':'R2','battery_soc':'60','connectivity':'ONLINE','health_status':'HEALTHY','zone':'Z2'}]
    assert choose_robot(robots,{'blocked_zone':'Z1'})['robot_id']=='R2'

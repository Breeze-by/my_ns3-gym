import hashlib,json
from pathlib import Path
import numpy as np
sep=.287;a=1.;reaction=.16;horizon=.76;padding=.02
v,w,c=np.meshgrid(np.linspace(-.3,.3,61),np.linspace(-1.2,1.2,49),np.linspace(-1,1,41),indexing="ij")
v,w,c=(x.ravel() for x in (v,w,c));left=v-w*sep/2;right=v+w*sep/2;tl=-c*sep/2;tr=c*sep/2
L=np.abs(tl-left)/a;R=np.abs(tr-right)/a;T=np.maximum(L,R);lo=np.minimum(L,R)
def speed(initial,target,t):return initial+np.sign(target-initial)*np.minimum(a*t,np.abs(target-initial))
def integral(initial,target,t):
 d=target-initial;limit=np.abs(d)/a;active=np.minimum(t,limit)
 return initial*t+np.sign(d)*(.5*a*active**2+np.abs(d)*np.maximum(t-limit,0))
def angle(t):return w*reaction+(integral(right,tr,t)-integral(left,tl,t))/sep
wlo=(speed(right,tr,lo)-speed(left,tl,lo))/sep
slope0=(np.sign(tr-right)-np.sign(tl-left))*a/sep
slope1=np.where(R>L,np.sign(tr-right),-np.sign(tl-left))*a/sep
root0=np.divide(-w,slope0,out=np.zeros_like(w),where=slope0!=0)
root0=np.where((root0>0)&(root0<lo),root0,0)
root1=lo+np.divide(-wlo,slope1,out=np.zeros_like(w),where=slope1!=0)
root1=np.where((root1>lo)&(root1<T),root1,lo)
angles=np.stack([np.zeros_like(w),w*reaction,angle(lo),angle(T),angle(root0),angle(root1)])
maxangle=np.max(np.abs(angles),axis=0)
V=np.abs(v);d=np.abs(c-w)*sep/2
path=np.where(d<=V,.5*(V**2+d**2)/a,V*d/a)+reaction*V
bound=np.maximum(np.abs(w),np.abs(c))*horizon
horizon_gap=maxangle-bound
imax=int(np.argmax(path));itime=int(np.argmax(T+reaction));igap=int(np.argmax(horizon_gap));ratio=np.divide(maxangle,bound,out=np.zeros_like(bound),where=bound>0);iratio=int(np.argmax(ratio))
def case(i):return {"v":float(v[i]),"w":float(w[i]),"cmd_v":0.,"cmd_w":float(c[i]),"left_initial":float(left[i]),"right_initial":float(right[i]),"left_target":float(tl[i]),"right_target":float(tr[i]),"stop_time_after_reaction_sec":float(T[i]),"stop_time_including_reaction_sec":float(T[i]+reaction),"path_length_including_reaction_m":float(path[i]),"max_abs_yaw_change_until_rest_rad":float(maxangle[i]),"existing_heading_half_angle_rad":float(bound[i]),"heading_bound_ratio":float(ratio[i])}
assert np.allclose(T,V+d,rtol=0,atol=2e-16)
assert np.max(T+reaction)<horizon+padding
assert np.max(path)<.138+.3*padding
assert np.max(horizon_gap)<2e-14
out={"schema":"mr3-ideal-independent-wheel-stop-scan-v1","scope":"independent finite ideal continuous wheel-rim acceleration model; no ROS, Gazebo dynamics, friction, transport, localization or native acceptance proof","grid":{"v_points":61,"w_points":49,"cmd_w_points":41,"cases":len(v),"bounds":{"v":[-.3,.3],"w":[-1.2,1.2],"cmd_w":[-1.,1.]}},"constants":{"wheel_separation_m":sep,"wheel_rim_acceleration_mps2":a,"reaction_sec":reaction,"existing_horizon_sec":horizon,"existing_reserve_per_robot_m":.138,"pair_geometry_margin_m":.02,"recommended_turn_stop_padding_sec":padding},"analytic_expressions":{"Tstop":"(|v| + sep/2*abs(cmd_w-w))/a","path":"reaction*abs(v) + (0.5*(v**2+d**2) if d<=abs(v) else abs(v)*d)/a; d=sep/2*abs(cmd_w-w)","yaw_extrema":"exact integrals of piecewise linear wheel speeds, endpoints plus roots of angular velocity"},"max_time_case":case(itime),"max_path_case":case(imax),"max_heading_ratio_case":case(iratio),"max_heading_bound_excess_rad":float(np.max(horizon_gap)),"analytic_corner":{"Tstop_including_reaction_sec":.7757,"path_length_including_reaction_m":.14271,"existing_horizon_shortfall_sec":.0157,"reserve_shortfall_per_robot_m":.00471,"pair_geometry_margin_remaining_after_shortfall_m":.01058},"recommendation":"Add explicit .02 sec turn-coupled stop padding to both declared horizon and reaction-distance reserve; do not describe .5 m/s2 as uniform instantaneous physical deceleration","script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with Path("/tmp/mr3_p2a0_v2_wheel_stop_bound_scan.json").open("x") as f:f.write(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))

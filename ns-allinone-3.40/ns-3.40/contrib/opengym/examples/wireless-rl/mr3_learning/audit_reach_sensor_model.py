"""Independent exact SDF/spawn gate for the genuine reach-only 20 Hz LiDAR.

The selected sensor rate and explicit initial-encoder tag have declared inverses.
Each inverse must restore all original model bytes; this gate neither changes a geometric predicate nor
proves actual delivery cadence or future physical response.
"""
import hashlib
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from .native_custody import Reader, parse, require
from .reach_audit_projection import project_module
from .supervisor import INITIAL_ENCODER_ACTUATION_PROFILE


SCHEMA = "mr3-reach-lidar20hz-model-audit-v1"
PROFILE = "mr3-reach-lidar-20hz-v1"
ORIGINAL_READER_SHA256 = "b9b6ef807c58e810feff036aab2b8efaf41d4eecfdb9fa13251287d50a5481ad"
BASE_MODEL_SHA256 = "c8131da065085475bdb0ce1e4c3abfc8c009811af6851fadf1fc33bd38b1d8a1"
ROS = Path("ros2_ws/ros2-multi-robot-automap")
LAUNCH = ROS/"src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"
MODEL = ROS/"src/multi_robot/models/turtlebot3_waffle/model.sdf"


def sensor_span(raw, rate):
    tree = ET.fromstring(raw)
    models = tree.findall("model")
    links = models[0].findall("link[@name='base_scan']") if len(models) == 1 else []
    sensors = links[0].findall("sensor[@name='hls_lfcd_lds']") if len(links) == 1 else []
    rates = sensors[0].findall("update_rate") if len(sensors) == 1 else []
    require(len(sensors) == 1 and sensors[0].attrib == {"name":"hls_lfcd_lds","type":"ray"}
            and len(rates) == 1 and rates[0].text == str(rate),
            "reach SDF lacks the unique exact-rate canonical ray sensor")
    link_start = raw.index(b'<link name="base_scan">')
    link_end = raw.index(b"</link>",link_start)
    start = raw.index(b'<sensor name="hls_lfcd_lds" type="ray">',link_start,link_end)
    end = raw.index(b"</sensor>",start,link_end)
    token = f"<update_rate>{rate}</update_rate>".encode()
    require(raw[start:end].count(token) == 1, "reach SDF rate token is ambiguous")
    return start,end,token


def _actuation_profile(value):
    require(value is None or type(value) is str and value == INITIAL_ENCODER_ACTUATION_PROFILE,
            "unknown reach SDF actuation inverse profile")
    return value


def inverse_initial_encoder_tag(restored):
    """Remove one declared launch insertion from its actual drive plugin only."""
    tree = ET.fromstring(restored)
    models = tree.findall("model")
    plugins = models[0].findall("plugin[@name='turtlebot3_diff_drive']") if len(models) == 1 else []
    tags = tree.findall(".//mr3_actuation_profile")
    direct = plugins[0].findall("mr3_actuation_profile") if len(plugins) == 1 else []
    require(len(plugins) == 1 and plugins[0].attrib == {
                "name":"turtlebot3_diff_drive","filename":"libmr3_gazebo_diff_drive.so"}
            and len(tags) == len(direct) == 1 and tags[0] is direct[0]
            and direct[0].text == INITIAL_ENCODER_ACTUATION_PROFILE
            and not direct[0].attrib and len(direct[0]) == 0,
            "reach SDF lacks the unique declared initial encoder drive profile")
    inserted = ("<mr3_actuation_profile>" + INITIAL_ENCODER_ACTUATION_PROFILE
                + "</mr3_actuation_profile>\n      ").encode()
    require(restored.count(inserted) == 1,
            "reach SDF initial encoder launch insertion bytes differ")
    return restored.replace(inserted,b"",1), {
        "schema":"mr3-initial-encoder-sdf-tag-inverse-v1",
        "actuation_profile":INITIAL_ENCODER_ACTUATION_PROFILE,
        "plugin_name":"turtlebot3_diff_drive","plugin_filename":"libmr3_gazebo_diff_drive.so",
        "removed_bytes":len(inserted),"removed_sha256":hashlib.sha256(inserted).hexdigest(),
        "detached_legacy_view_only":True,"actual_driver_build_proved_here":False,
        "actual_new_driver_build_independently_required":True}


def inverse_reach_lidar(generated, source, robot, epoch, episode, *, actuation_profile=None):
    """Return a detached 5 Hz view only after exact whole-file inverse proof."""
    _actuation_profile(actuation_profile)
    require(robot in ("tb1","tb2","tb3") and type(epoch) is str and epoch,
            "reach SDF requires the actual three-robot epoch")
    require(hashlib.sha256(source).hexdigest() == BASE_MODEL_SHA256,
            "reach sensor source is not the unchanged original 5 Hz model")
    sensor_span(source,5)
    start,end,token = sensor_span(generated,20)
    replacement = generated[start:end].replace(token,b"<update_rate>5</update_rate>",1)
    restored = generated[:start]+replacement+generated[end:]
    actuation_inverse = None
    if actuation_profile is not None:
        restored,actuation_inverse = inverse_initial_encoder_tag(restored)
    normalized = restored
    for tag,value in (("mr3_audit_path",str(Path(episode)/f"drive_{robot}.jsonl")),
                      ("mr3_epoch",epoch),("mr3_tagged_commands","true")):
        actual = f"<{tag}>{escape(value)}</{tag}>".encode()
        require(normalized.count(actual) == 1, "reach SDF actual protocol tag differs: "+tag)
        normalized = normalized.replace(actual,f"<{tag}/>".encode(),1)
    require(normalized == source, "reach SDF whole-byte inverse differs from original 5 Hz model")
    proof = {"profile":PROFILE,"sensor_link":"base_scan","sensor_name":"hls_lfcd_lds",
        "source_update_rate_hz":5,"effective_update_rate_hz":20,
        "source_sha256":hashlib.sha256(source).hexdigest(),
        "effective_sha256":hashlib.sha256(generated).hexdigest(),
        "whole_byte_inverse_sha256":hashlib.sha256(normalized).hexdigest(),
        "whole_byte_inverse_equal":True,"native_input_modified":False,
        "scope":"configured real ray sensor only; actual scan/TF delivery cadence remains independently required"}
    if actuation_inverse is not None:
        proof["actuation_profile_inverse"] = actuation_inverse
        proof["scope"] = ("configured real ray and exact declared drive-tag inverse only; "
                          "actual build, compound motor replay and delivery cadence remain independently required")
    return restored,proof


def load_spawn_impl(*, actuation_profile=None):
    _actuation_profile(actuation_profile)
    module,proof = project_module("audit_action_trace.py",ORIGINAL_READER_SHA256,(
        ("        tree = ET.fromstring(read(model))\n",
         "        restored_model, lidar_proof = inverse_reach_lidar(read(model), read(WORKSPACE / MODEL), robot, epoch, episode)\n"
         "        tree = ET.fromstring(restored_model)\n",1),
        ('                        "effective_sdf": str(model)}\n',
         '                        "effective_sdf": str(model), "reach_sensor_profile": lidar_proof}\n',1),
    ))
    if actuation_profile is None:
        module.inverse_reach_lidar = inverse_reach_lidar
    else:
        module.inverse_reach_lidar = lambda generated,source,robot,epoch,episode: inverse_reach_lidar(
            generated,source,robot,epoch,episode,actuation_profile=actuation_profile)
        proof["actuation_profile"] = actuation_profile
        proof["actual_new_driver_build_independently_required"] = True
    return module,proof


def audit_episode(directory,root,freeze,*,actuation_profile=None):
    _actuation_profile(actuation_profile)
    directory,root = Path(directory),Path(root)
    read = Reader()
    metadata = parse(read(directory/"metadata.json"))
    require(metadata.get("freeze") == freeze and metadata.get("safety_contract") == "mr3-reach-v1",
            "reach sensor gate rejects legacy or mixed-freeze native inputs")
    from .native_custody_reach import initial_encoder_profile
    require(initial_encoder_profile(metadata) == actuation_profile,
            "reach sensor metadata actuation profile differs from qualification dispatch")
    module,projection = load_spawn_impl(**({"actuation_profile":actuation_profile}
                                          if actuation_profile is not None else {}))
    module.WORKSPACE = root
    source_proof = {}
    for relative in (LAUNCH,MODEL,Path(__file__).resolve().relative_to(root),
                     Path(module.__file__).resolve().relative_to(root)):
        raw = read(root/relative)
        require(raw == subprocess.check_output(["git","show",freeze+":"+str(relative)],cwd=root),
                "reach sensor source differs from exact freeze: "+str(relative))
        source_proof[str(relative)] = hashlib.sha256(raw).hexdigest()
    result = module._spawn(directory,metadata["epoch"],read,False)
    read.finish()
    return {"schema":SCHEMA,"passed":True,"profile":PROFILE,"freeze":freeze,
        "spawn":result,"immutable_reader_projection":projection,"source_proof":source_proof,
        "artifact_proof":read.bindings,"original_mathematical_predicates_changed":False,
        "actual_scan_delivery_cadence_proved":False,"continuous_physical_model_proved":False,
        "scientific_native_admission":False}


def attach_native_gate(phase,root,freeze,*,actuation_profile=None):
    """Conjoin the new source/model gate with the private original native audit."""
    _actuation_profile(actuation_profile)
    original = phase.corrected_audit
    def corrected_audit(base,native,command,directories,*,matrix=False,expected_fault=False):
        result = original(base,native,command,directories,matrix=matrix,expected_fault=expected_fault)
        reports,errors = [],list(result.get("errors",[]))
        for directory in directories:
            directory = Path(directory)
            workers = sorted(path for path in directory.glob("worker*") if path.is_dir())
            episodes = []
            for worker in workers:
                attempts = sorted(path for path in worker.glob("episode*") if path.is_dir())
                if not attempts:
                    reports.append({"directory":str(worker),"passed":False,"error":"worker has no episode attempt"})
                    errors.append("reach sensor model: worker has no episode attempt: "+str(worker))
                episodes.extend(attempts)
            if ((directory/"metadata.json").exists()
                    or directory.name.startswith("episode") and directory.parent.name.startswith("worker")):
                if workers:
                    errors.append("reach sensor model: ambiguous episode/run layout: "+str(directory))
                episodes.insert(0,directory)
            if not episodes:
                errors.append("reach sensor model: no actual episodes: "+str(directory))
            for episode in episodes:
                row = {"directory":str(episode)}
                try:
                    row.update(audit_episode(episode,root,freeze,**({"actuation_profile":actuation_profile}
                        if actuation_profile is not None else {})))
                except (OSError,ValueError,TypeError,KeyError,IndexError,ET.ParseError,subprocess.SubprocessError) as error:
                    row.update(passed=False,error=repr(error))
                    errors.append("reach sensor model: "+str(episode)+": "+repr(error))
                reports.append(row)
        result.update(passed=result.get("passed") is True and not errors,errors=errors,
                      reach_sensor_models=reports)
        return result
    phase.corrected_audit = corrected_audit

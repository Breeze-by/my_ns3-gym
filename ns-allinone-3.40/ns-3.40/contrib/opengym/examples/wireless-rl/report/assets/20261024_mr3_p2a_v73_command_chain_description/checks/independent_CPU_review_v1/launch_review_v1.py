import json,os
from pathlib import Path
s=json.loads((Path(__file__).parent/'cpu_spec_v1.json').read_bytes())
os.chdir(s['cwd'])
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.execv(s['actual_argv'][0],s['actual_argv'])

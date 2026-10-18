from pathlib import Path
p=Path('/tmp/mr3_p2a0_v22_archive_actual_binary_v1.py')
old=p.read_text();new=old
for before,after in [
 ('Bind final canonical V22 library','Bind final canonical V24 library'),
 ('report/assets/20261018_mr3_p2a0_v22_ray_box','report/assets/20261018_mr3_p2a0_v24_install'),
 ('/tmp/mr3_p2a0_v22_canonical_build_v2/execution.json','/tmp/mr3_p2a0_v24_canonical_build_v1/execution.json'),
 ('389312','398080'),
 ('7be79c7f3d2cac53a9d1692aa868d91d4b9977e2b7541203ce4ffe90c605a08f','782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8'),
 ('b165ce49eaf5b3d52853cd759e4809962192d1922f0f210f5c82cff79c2a6b2a','f82646c8434b77c42f585ac1828eda84640bac873f70cc7de6848cfbd6493473')]:
    assert new.count(before)==1,before
    new=new.replace(before,after,1)
dest=Path('/tmp/mr3_p2a0_v24_archive_actual_binary_v1.py');assert not dest.exists();dest.write_text(new)
print('Prepared exact binary archive script; compatible custody schema unchanged.')

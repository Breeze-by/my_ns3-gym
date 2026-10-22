"""Post-wait opaque byte archive using the unchanged V45 copy verifier."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
LEGACY = W / 'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py'
LEGACY_SHA = '63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06'
FREEZE = '14719a72b96cff65b134b7d46ec6d2ccbf84e061'
DEST = A / 'closed_execution'
ROOTS = [(Path('/tmp/mr3_p2a_reach_v49_startup_driver'), 'driver'),
         (Path('/tmp/mr3_p2a_reach_v49_startup_wait'), 'actual_wait'),
         (ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v49', 'native')]


def main():
    raw = LEGACY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LEGACY_SHA:
        raise ValueError('immutable byte copy/verifier helper differs')
    spec = importlib.util.spec_from_file_location('_v49_original_byte_verifier', LEGACY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.A, m.DEST = A, DEST
    review, review_proof = m.metadata(A / 'independent_closed_review_v1.json')
    m.require(review.get('passed') is True and review.get('freeze') == FREEZE
              and review.get('present_including_zombies') == [] and review.get('errors') == [],
              'post-wait independent closure proof is missing')
    identities = review['absent_proc_stat'] + review['same_pid_different_start']
    for row in identities:
        m.require_absent(row)

    def discover():
        selected, links, directories = {}, [], {}
        for root, label in ROOTS:
            m.require(root.is_dir() and not root.is_symlink(), 'closed root missing/symlink: ' + str(root))
            for parent, names, files in os.walk(root, followlinks=False):
                parent = Path(parent)
                directories[str(parent)] = m.stamp(parent.lstat())
                names.sort(); files.sort()
                for name in list(names) + files:
                    source = parent / name
                    before = m.stamp(source.lstat())
                    if stat.S_ISLNK(before['mode']):
                        links.append(dict(original=str(source), target=os.readlink(source),
                                          stat=before, target_followed=False))
                        if name in names:
                            names.remove(name)
                    elif name in files:
                        m.require(stat.S_ISREG(before['mode']), 'special closed file: ' + str(source))
                        target, compressed = m.target_for(label, source.relative_to(root), source)
                        selected[source] = dict(target=target, compressed=compressed, stat=before)
                    else:
                        m.require(stat.S_ISDIR(before['mode']), 'special closed directory: ' + str(source))
        targets = [row['target'] for row in selected.values()]
        m.require(selected and len(set(targets)) == len(targets), 'empty/colliding archive')
        return selected, links, directories

    inventory = A / 'closed_inventory_v1.json'
    failure = A / 'closed_inventory_v1.failed.json'
    m.require(not any(p.exists() for p in (DEST, inventory, failure)), 'exclusive archive already exists')
    entries = []
    try:
        before = discover()
        selected, links, directories = before
        DEST.mkdir(exist_ok=False)
        for source, row in sorted(selected.items()):
            entries.append(m.archive(source, row))
        m.require(discover() == before, 'closed root membership/stat changed during opaque byte copy')
        for row in identities:
            m.require_absent(row)
        value = dict(schema='mr3-v49-closed-byte-archive-v1', freeze=FREEZE,
            byte_archive_complete=True, scientific_results_recomputed=False,
            fees_recomputed=False, models_loaded=False, closure_metadata=review_proof,
            unchanged_archive_implementation=dict(path=str(LEGACY), sha256=LEGACY_SHA),
            roots=[dict(original=str(p), label=label) for p, label in ROOTS],
            files=len(entries), original_bytes=sum(row['original_bytes'] for row in entries),
            canonical_bytes=sum(row['canonical_bytes'] for row in entries),
            links=links, link_count=len(links), entries=entries)
        m.write_json(inventory, value)
        print(json.dumps({key: value[key] for key in
                          ('byte_archive_complete', 'files', 'original_bytes', 'canonical_bytes', 'link_count')}))
    except BaseException as error:
        m.write_json(failure, dict(error=repr(error), completed_entries=entries,
                                  byte_archive_complete=False, originals_deleted=False))
        raise


if __name__ == '__main__':
    main()

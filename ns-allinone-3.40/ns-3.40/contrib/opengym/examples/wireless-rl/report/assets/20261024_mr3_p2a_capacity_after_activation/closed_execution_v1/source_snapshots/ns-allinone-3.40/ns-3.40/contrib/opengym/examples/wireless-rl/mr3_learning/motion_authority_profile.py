"""Fixed explicit receiving-authority profile; independent of motor actuation."""
MOTION_AUTHORITY_PROFILE = 'mr3-owned-stream-authority-v3'
REACH_CONTRACT = 'mr3-reach-v1'


def motion_authority_profile_for_safety_contract(contract):
    if type(contract) is not str:
        raise ValueError('safety contract must be an exact string')
    if contract == REACH_CONTRACT:
        return MOTION_AUTHORITY_PROFILE
    if contract == 'legacy':
        return None
    raise ValueError('unknown safety contract for receiving authority')


def selected_motion_authority_profile(metadata, *, required=False):
    if type(metadata) is not dict:
        raise ValueError('authority profile metadata is not an object')
    profile = metadata.get('motion_authority_profile')
    if profile is None:
        if required:
            raise ValueError('mandatory receiving-authority profile missing')
        return None
    if (type(profile) is not str or profile != MOTION_AUTHORITY_PROFILE
            or type(metadata.get('safety_contract')) is not str
            or metadata['safety_contract'] != REACH_CONTRACT):
        raise ValueError('unknown/mixed receiving-authority profile')
    return profile


def require_qualified_motion_authority(qualification):
    """Consumer check after the original qualifier reconstructed its evidence.

    This shape check does not itself give journal/source/scientific credit.
    validate_qualification must first reconstruct the complete qualification.
    """
    if selected_motion_authority_profile(qualification, required=True) != MOTION_AUTHORITY_PROFILE:
        raise ValueError('qualification authority profile differs')
    proof = qualification.get('motion_authority_replay')
    episodes = qualification.get('episodes')
    if (type(proof) is not dict or proof.get('schema') != 'mr3-independent-motion-authority-qualification-v1'
            or proof.get('profile') != MOTION_AUTHORITY_PROFILE or proof.get('passed') is not True
            or proof.get('freeze') != qualification.get('freeze')
            or proof.get('raw_generation_known') is not False
            or type(episodes) is not list or len(episodes) != 12
            or type(proof.get('episodes')) is not list or len(proof['episodes']) != 12):
        raise ValueError('missing complete independent authority qualification')
    expected = {(row['directory'], row['epoch']) for row in episodes}
    actual = set()
    for row in proof['episodes']:
        if (type(row) is not dict or row.get('passed') is not True
                or row.get('profile') != MOTION_AUTHORITY_PROFILE
                or row.get('robots') != ['tb1', 'tb2', 'tb3']
                or type(row.get('runtime_result_sha256')) is not str
                or len(row['runtime_result_sha256']) != 64):
            raise ValueError('incomplete independent authority episode proof')
        actual.add((row.get('directory'), row.get('epoch')))
    if len(expected) != 12 or actual != expected:
        raise ValueError('independent authority episode set differs')
    return proof

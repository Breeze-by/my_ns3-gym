"""Derive declared worker addresses from the exact actual benchmark argv."""


def derive_worker_bindings(stage):
    argv = stage['command']
    if type(argv) is not list or not all(type(value) is str for value in argv):
        raise ValueError('actual stage command must be a string argv')
    values = {}
    for key in ('--workers', '--base-domain', '--base-port'):
        if argv.count(key) != 1:
            raise ValueError('missing or repeated actual command option: ' + key)
        index = argv.index(key) + 1
        if index == len(argv) or not argv[index].isascii() or not argv[index].isdigit():
            raise ValueError('actual command option must be an unsigned integer: ' + key)
        values[key] = int(argv[index])
    count, domain, port = (values[key] for key in ('--workers', '--base-domain', '--base-port'))
    if count not in (1, 2) or not 0 <= domain <= domain + count - 1 <= 232 \
            or not 1024 <= port <= port + count - 1 <= 65535:
        raise ValueError('actual matrix worker/domain/port range differs')
    return [{'worker_id': index, 'robots': ['tb1', 'tb2', 'tb3'],
             'domain': domain + index, 'port': port + index} for index in range(count)]


def validate_worker_bindings(stage):
    expected = derive_worker_bindings(stage)
    actual = stage.get('worker_bindings')
    if type(actual) is not list or len(actual) != len(expected):
        raise ValueError('declared worker bindings differ from actual command')
    for row, wanted in zip(actual, expected):
        if type(row) is not dict or set(row) != set(wanted) \
                or any(type(row[key]) is not int for key in ('worker_id', 'domain', 'port')) \
                or type(row['robots']) is not list or row != wanted:
            raise ValueError('declared worker binding differs from actual argv/worker index')
    return expected

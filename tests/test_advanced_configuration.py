from configuration import AdvancedConfiguration, LockError, SymbolError
import pytest


@pytest.fixture(scope='module')
def mock_config(request):
    """Return the directory of the currently running test script"""
    # uses .join instead of .dirname so we get a LocalPath object instead of
    # a string. LocalPath.join calls normpath for us when joining the path
    return request.fspath.join('../mock_configs')


def test_as_dict():
    data = {'key1': 'value1', 'sub_data': {'one': 1, 'two': 2}}
    cfg = AdvancedConfiguration(data)
    assert cfg.as_dict() == data

    cfg.lock_key('key1')
    cfg.lock_key('sub_data.one')
    locked_data = {'#key1': 'value1', 'sub_data': {'#one': 1, 'two': 2}}
    assert cfg.as_dict(keep_locks=True) == locked_data


def test_merge(mock_config):
    path1 = mock_config.join('base_data.json')
    path2 = mock_config.join('advanced_override.json')
    cfg = AdvancedConfiguration.from_files(path1, path2)
    assert cfg.get('list') == ['two', 'three']
    assert cfg.get('exists') is True
    assert cfg.get('cat') == 'meows'
    assert cfg.get('group.two') == 6
    assert set(cfg.get('group').keys()) == {'one', 'two', 'three'}
    with pytest.raises(KeyError):
        cfg.get('rabbit')


def test_sources():
    data1 = {'list': [1, 2], 'int': 5, 'dict': {'str': 'A sentence'}}
    data2 = {'+list': [3, 4], 'dict': {'str': ' contains words'}}
    data3 = {'-list': [3]}
    cfg = AdvancedConfiguration.from_dicts([data1, data2], ['one', 'two'])
    cfg.merge(data3, 'three')
    sources = cfg.sources()

    # Order is not guaranteed, assert by set instead of list
    assert set(sources) == {'one', 'two', 'three'}, 'Missing source identifier(s)'
    assert set(sources['one']) == {'int', 'list'}
    assert set(sources['two']) == {'dict.str', 'list'}
    assert set(sources['three']) == {'list'}


# ============================================================================ #
#                                  LOCKING                                     #
# ============================================================================ #


def test_action_lock():
    data1 = {'list': [1, 2], 'int': 5, 'str': 'A sentence'}
    data2 = {'#list': [1, 2, 3], '=#str': None}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])

    # Values are still updated correctly
    assert cfg.get('list') == [1, 2, 3]
    assert cfg.get('int') == 5
    assert cfg.get('str') == 'A sentence'

    cfg.set('int', 10)

    with pytest.raises(LockError):
        cfg.set('list', [1, 2])

    with pytest.raises(LockError):
        cfg.set('str', 'override')


def test_is_locked():
    data = {'#list': [1, 2], 'int': 5, 'dict': {'#str': 'A sentence'}}
    cfg = AdvancedConfiguration(data)
    assert cfg.is_locked('list')
    assert cfg.is_locked('dict.str')
    assert cfg.is_locked('int') is False
    assert cfg.is_locked('dict') is False


def test_lock_key():
    data1 = {'list': [1, 2], 'int': 5, 'dict': {'str': 'A sentence'}}
    cfg = AdvancedConfiguration(data1)

    cfg.lock_key('int')
    assert cfg.is_locked('int')

    cfg.lock_key('dict.str')
    assert cfg.is_locked('dict.str')


def test_locked():
    data = {'#list': [1, 2], 'int': 5, 'dict': {'#str': 'A sentence'}}
    cfg = AdvancedConfiguration(data)
    assert set(cfg.locked()) == {'list', 'dict.str'}


def test_lock_merge():
    data1 = {'#list': [1, 2], 'int': 5, 'dict': {'#str': 'A sentence'}}
    cfg = AdvancedConfiguration(data1)

    # Cannot merge a list override as it should be locked
    data2 = {'list': [3, 4]}
    with pytest.raises(LockError):
        cfg.merge(data2)


def test_lock_set():
    data1 = {'#list': [1, 2], 'int': 5, 'dict': {'#str': 'A sentence'}}
    cfg = AdvancedConfiguration(data1)

    with pytest.raises(LockError):
        cfg.set('list', [3, 4])

    cfg.lock_key('int')
    with pytest.raises(LockError):
        cfg.set('int', 1)

# ============================================================================ #
#                                  ACTIONS                                     #
# ============================================================================ #


def test_action_add():
    data1 = {'list': [1, 2], 'int': 5, 'str': 'A sentence'}
    data2 = {'+list': [3, 4], '+int': 5, '+str': ' with more words'}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])
    assert cfg.get('list') == [1, 2, 3, 4]
    assert cfg.get('int') == 10
    assert cfg.get('str') == 'A sentence with more words'


def test_action_copy():
    data1 = {'list': [1, 2], 'int': 5, 'str': 'A sentence'}
    data2 = {'=list': ['Value is ignored'], '=int': 0, '=str': 'Value is ignored'}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])
    assert cfg.get('list') == [1, 2]
    assert cfg.get('int') == 5
    assert cfg.get('str') == 'A sentence'


def test_action_subtract():
    data1 = {'list': [1, 2], 'int': 5, 'str': 'A sentence'}
    data2 = {'-list': [1], '-int': 5, '-str': 'e'}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])
    assert cfg.get('list') == [2]
    assert cfg.get('int') == 0
    assert cfg.get('str') == 'A sntnc'


def test_register_action():
    def custom_action(orig, new):
        """ Concatenates integers """
        return int(str(orig) + str(new))

    AdvancedConfiguration.register_action('$', custom_action)

    # Symbol shouldn't be able to be registered twice
    with pytest.raises(SymbolError):
        AdvancedConfiguration.register_action('$', custom_action)

    data1 = {'key': 1}
    data2 = {'$key': 2}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])
    assert cfg.get('key') == 12


# ============================================================================ #
#                                 MODIFIERS                                    #
# ============================================================================ #


def test_modifier_exists():
    data1 = {'exists': 1, 'null': None, 'non_truth': False}
    data2 = {'?exists': 2, '?not_exists': 3, '?null': 4, '?non_truth': True}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])

    # Should override because it exists
    assert cfg.get('exists') == 2
    assert cfg.get('non_truth') is True

    # Shouldn't override, as they don't exist (None value counts)
    assert cfg.get('null') is None
    with pytest.raises(KeyError):
        cfg.get('not_exists')


def test_modifier_not_exists():
    data1 = {'exists': 1, 'null': None, 'non_truth': False}
    data2 = {'!exists': 2, '!not_exists': 3, '!null': 4, '!non_truth': True}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])

    # Should override because it didn't exist (None value counts)
    assert cfg.get('not_exists') == 3
    assert cfg.get('null') == 4

    # Shouldn't override, as they already exist
    assert cfg.get('non_truth') is False
    assert cfg.get('exists') == 1


def test_register_modifier():
    def custom_modifier(action, key, orig, new):
        """ Only overrides if new value is greater """
        return orig < new

    AdvancedConfiguration.register_modifier('<', custom_modifier)

    # Symbol shouldn't be able to be registered twice
    with pytest.raises(SymbolError):
        AdvancedConfiguration.register_modifier('<', custom_modifier)

    data1 = {'key1': 1, 'key2': 10}
    data2 = {'<key1': 2, '<key2': 2}
    cfg = AdvancedConfiguration.from_dicts([data1, data2])
    assert cfg.get('key1') == 2
    assert cfg.get('key2') == 10

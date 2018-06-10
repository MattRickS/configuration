from configuration import Configuration
import pytest


@pytest.fixture(scope='module')
def mock_config(request):
    """Return the directory of the currently running test script"""
    # uses .join instead of .dirname so we get a LocalPath object instead of
    # a string. LocalPath.join calls normpath for us when joining the path
    return request.fspath.join('../mock_configs')


# ============================================================================ #
#                                PROPERTIES                                    #
# ============================================================================ #


def test_merge_count():
    data1 = {'a': 1}
    data2 = {'b': 1}
    data3 = {'c': 1}
    cfg = Configuration.from_dicts([data1, data2], ['one', 'two'])
    cfg.merge(data3, 'three')
    assert cfg.merge_count == 3


def test_merge_order():
    data1 = {'a': 1}
    data2 = {'b': 1}
    data3 = {'c': 1}
    cfg = Configuration.from_dicts([data1, data2], ['one', 'two'])
    cfg.merge(data3, 'three')
    assert cfg.merge_order == ['one', 'two', 'three']


# ============================================================================ #
#                               CLASS METHODS                                  #
# ============================================================================ #


def test_from_cache():
    data = {'key1': 'value1'}
    cfg1 = Configuration(data)
    cfg1.cache('test_cache')

    cfg2 = Configuration.from_cache('test_cache')
    assert cfg1 == cfg2


def test_from_dicts():
    data1 = {'key1': 'value1'}
    data2 = {'key2': 'value2'}
    cfg = Configuration.from_dicts([data1, data2], ['one', 'two'])
    assert cfg.get('key1') == 'value1'
    assert cfg.get('key2') == 'value2'

    cfg = Configuration.from_dicts([data1, data2], ['one'])
    assert set(cfg.sources().keys()) == {'one', 1}


def test_from_env_var(mock_config):
    import os

    path1 = mock_config.join('base_data.json')
    path2 = mock_config.join('simple_override.json')
    os.environ['TEST_CONFIG'] = os.pathsep.join(str(x) for x in [path1, path2])
    cfg = Configuration.from_environment('TEST_CONFIG')
    assert cfg.get('list') == ['one']


def test_from_files(mock_config):
    path1 = mock_config.join('base_data.json')
    path2 = mock_config.join('simple_override.json')
    cfg = Configuration.from_files(path1, path2)
    assert cfg.get('list') == ['one']
    assert cfg.get('source') is None
    assert cfg.get('extra') is None


# ============================================================================ #
#                                  METHODS                                     #
# ============================================================================ #


def test_as_dict():
    data1 = {'key1': 'value1', 'sub_data': {'one': 1, 'two': 2}}
    cfg = Configuration(data1)
    assert cfg.as_dict() == data1


def test_get():
    data1 = {'key1': 'value1', 'sub_data': {'one': 1, 'two': 2}}
    cfg = Configuration(data1)
    assert cfg.get('sub_data.one') == 1

    data2 = {'key1': 'value2', 'sub_data': {'one': 3, 'two': 2}}
    cfg.merge(data2)
    assert cfg.get('sub_data.one') == 3

    with pytest.raises(KeyError):
        cfg.get('sub_data.three')


def test_merge():
    data1 = {'key1': 'value1', 'sub_data': {'one': 1, 'two': 2}, 'source': None}
    data2 = {'key1': 'value2', 'sub_data': {'one': 3, 'two': 2}, 'extra': None}

    cfg = Configuration(data1)
    assert cfg.get('key1') == 'value1'
    assert cfg.get('source') is None
    assert cfg.get('sub_data') == {'one': 1, 'two': 2}
    with pytest.raises(KeyError):
        cfg.get('extra')

    cfg.merge(data2)
    assert cfg.get('key1') == 'value2'
    assert cfg.get('sub_data') == {'one': 3, 'two': 2}
    assert cfg.get('source') is None
    assert cfg.get('extra') is None


def test_set():
    data1 = {'key1': 'value1', 'sub_data': {'one': 1, 'two': 2}}
    cfg = Configuration(data1)
    assert cfg.get('sub_data.one') == 1

    cfg.set('sub_data.one', 2)
    assert cfg.get('sub_data.one') == 2
    # Ensure the source data is unmodified
    assert data1['sub_data']['one'] == 1

    cfg.set('sub_data', 'string instead of dict')
    assert cfg.get('sub_data') == 'string instead of dict'


def test_source():
    data1 = {'key1': 'value1', 'shared': 'value', 'sub_data': {'one': 1, 'two': 2}}
    data2 = {'key2': 'value2', 'shared': 'value', 'sub_data': {'two': 3}}
    cfg = Configuration.from_dicts([data1, data2], ['one', 'two'])
    assert cfg.source('key1') == 'one'
    assert cfg.source('key2') == 'two'
    assert cfg.source('shared') == 'two'
    assert cfg.source('sub_data.one') == 'one'
    assert cfg.source('sub_data.two') == 'two'
    assert set(cfg.source('sub_data')) == {'one', 'two'}


def test_sources():
    data1 = {'key1': 'value1', 'shared': 'value', 'sub_data': {'key2': 'value2'}}
    data2 = {'key2': 'value2', 'shared': 'value', 'sub_data': 'leaf'}
    cfg = Configuration.from_dicts([data1, data2], ['one', 'two'])
    sources = cfg.sources()
    # Order is not guaranteed, assert by set instead of list
    assert set(sources) == {'one', 'two'}, 'Missing source identifier(s)'
    assert set(sources['one']) == {'key1'}
    assert set(sources['two']) == {'key2', 'shared', 'sub_data'}

import os
import json

# Python 2 and 3 compatible zip_longest
import sys
if sys.version_info[0] < 3:
    from itertools import izip_longest as zip_longest
else:
    from itertools import zip_longest


class Configuration(object):
    """
    Provides an easy to use configuration interface for any dictionary data. The
    default load format for files is json but can be changed by subclassing
    Configuration and overriding the _load_file() method.

    Nested keys can be retrieved with a single call by joining the keys using
    the separator value passed to the Configuration (defaults to '.'). Any key
    in the dictionary can be represented as a single string in this way.
    Iterating over the Configuration returns the nested key for each leaf value.

    Configurations can be merged to override values. This preserves old values
    that are not present in the new data, while creating new values and
    overriding conflicts. The merge is recursive, so only leaf keys will be
    modified.

    Names can be provided with each data being merged in that are used to track
    the source for each value in the dictionary. If names are omitted, an
    integer count is used as the source identifier. Count is incremented whether
    or not a name is provided.

    Configurations can be cached and retrieved using an identifier name. The
    Configuration.from_environment() method includes a cached keyword that uses
    the environment variable name as the cached identifier.

    Example:
        >>> data1 = {'group': {'one': 1, 'two': 2}}
        >>> config = Configuration(data1, name='original')
        >>> config.get('group.two')
        2
        >>> data2 = {'group': {'two': 3}}
        >>> config.merge(data2, name='override')
        >>> config.get('group.two')
        3
        >>> config.get('group.one')
        1
        >>> config.sources()
        {'original': ['group.one'], 'override': ['group.two']}
    """
    _caches = {}

    def __init__(self, data=None, name=None, separator='.'):
        """
        :param dict     data:       Dictionary of seed data
        :param object   name:       Identifier for the seed data
        :param str      separator:  String separator for nested keys
        """
        self._data = {}
        self._merge_order = []
        self._separator = separator
        self._sources = {}

        if data:
            self.merge(data, name)

    def __getitem__(self, item):
        return self.get(item)

    def __iter__(self):
        return iter(self._sources)

    def __setitem__(self, key, value):
        self.set(key, value)

    @property
    def merge_count(self):
        """
        Number of dictionaries that have been merged together

        :rtype: int
        """
        return len(self._merge_order)

    @property
    def merge_order(self):
        """
        List of data identifiers in the order they were merged

        :rtype: list
        """
        return self._merge_order[:]

    @classmethod
    def from_cache(cls, name):
        """
        Retrieves the Configuration cached under the given name. Returns None if
        no Configuration exists for that name.

        :param str name:
        :rtype: Configuration
        """
        return cls._caches.get(name)

    @classmethod
    def from_dicts(cls, dicts, names=None):
        """
        :param list[dict] dicts:    List of dictionaries to merge together.
                                    Dictionaries are merged from first to last.
        :param list[str]  names:    Optional set of names to use as a source for
                                    each dict they're zipped with.
        :rtype: Configuration
        """
        config = cls()
        for data, name in zip_longest(dicts, names or []):
            config.merge(data, name=name)
        return config

    @classmethod
    def from_environment(cls, env_var, cached=True):
        """
        Reads paths from a given environment variable and merges their data into
        a single Configuration. Files are read in order, with the last path
        providing final override values. Each path is used as the source name.

        Configurations can be cached so that they are only evaluated when needed

        :param str  env_var:    Name of the environment variable to read
        :param bool cached:     Retrieves the cached Configuration if it exists,
                                otherwise resolves the environment and caches
                                the result.
        :rtype: Configuration
        """
        config = cls._caches.get(env_var)
        if config and cached:
            return config

        paths = os.getenv(env_var)
        config = cls.from_files(*paths.split(os.pathsep))
        if cached:
            config.cache(env_var)

        return config

    @classmethod
    def from_files(cls, *files):
        """
        Files are read in order, with the last path providing final override
        values. Each path is used as the source name.

        :param str files:   File paths to read data from.
        :rtype: Configuration
        """
        dict_list = [(cls._load_file(path), path) for path in files]
        config = cls.from_dicts(*zip(*dict_list))
        return config

    @classmethod
    def _load_file(cls, path):
        """
        Loads the dictionary data from the given file path.

        :param str path:
        :rtype: dict
        """
        with open(path) as f:
            return json.load(f)

    def as_dict(self):
        """
        Returns a deep copy of the configuration in it's current state

        :rtype: dict
        """
        from copy import deepcopy
        return deepcopy(self._data)

    def cache(self, name):
        """
        Caches the configuration under the given name. This can be retrieved
        using the Configuration.from_cache() method.

        :param str  name:
        """
        Configuration._caches[name] = self

    def get(self, key):
        """
        Retrieves a value from the configuration. Can be a nested key joined
        by the configuration separator (default '.').

        :param str      key:    Nested path of key names
        :return: Value stored at the given key location
        """
        data, key = self._walk(key)
        return data[key]

    def merge(self, data, name=None):
        """
        Writes the leaf keys of the data into the Configuration, overriding
        conflicts. A name value can be provided as an identifier for where the
        values originated. If omitted, an integer count is used instead.

        :param dict     data:   Dictionary of data to merge in
        :param object   name:   Identifier for the source data
        """
        identifier = name or len(self._merge_order)
        self._merge(data, self._data, identifier)
        self._merge_order.append(identifier)

    def set(self, key, value):
        """
        Sets a value in the configuration. This is not written to file and is
        only stored as long as the Configuration instance is in scope.

        :param str      key:    Nested path of key names
        :param object   value:
        """
        data, key = self._walk(key)
        data[key] = value

    def source(self, key):
        """
        Returns the source identifier for the given key. If the key is not a
        leaf key, then a list of sources that contributed to the data will be
        returned.

        :param str      key:    Nested path of key names
        :return:
            Return type varies based on the key type, and the given identifiers.
            Leaf keys will return the identifier their data was provided with,
            or the integer count if the identifier was None (see merge).
            Non-leaf keys will return a list of all identifiers that contributed
            to it's data.
        """
        try:
            return self._sources[key]
        except KeyError:
            all_sources = []
            for source_key, source_name in self._sources.items():
                if source_key.startswith(key):
                    all_sources.append(source_name)
            return all_sources

    def sources(self):
        """
        Return a dictionary mapping the source identifiers to all the leaf keys
        it contributed to the current state.

        :rtype: dict
        """
        sources = {key: [] for key in self._merge_order}
        for nested_key, source_id in self._sources.items():
            sources[source_id].append(nested_key)

        return sources

    def _merge(self, source, dest, name, path=''):
        """
        :param dict     source: Dictionary to merge from
        :param dict     dest:   Dictionary to merge into
        :param object   name:   Identifier for the source data
        :param str      path:   Nested key path
        """
        for key, value in source.items():
            key_path = path + self._separator + key if path else key
            if isinstance(value, dict):
                node = dest.setdefault(key, {})
                self._merge(value, node, name, key_path)
            else:
                # If a leaf key replaces a dict, remove all sources that were lost
                if isinstance(dest.get(key), dict):
                    removed = {key for key in self._sources if key.startswith(key_path)}
                    for key in removed:
                        self._sources.pop(key, None)

                dest[key] = value
                self._sources[key_path] = name

    def _walk(self, key):
        """
        Walks through the segments of the key to return the last segment of the
        key and the dict to retrieve it from.

        :param str      key:    Nested path of key names
        :rtype: tuple[dict, str]
        """
        parts = key.split(self._separator)

        data = self._data
        for part in parts[:-1]:
            data = data[part]

        return data, parts[-1]

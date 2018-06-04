import re
from collections import namedtuple
from configuration import Configuration


'''
Merge methods:
    + : Adds the value to existing values, sets the value if it doesn't exist
    - : Removes the value from existing values if it exists

Special methods:
    # : Locks a key so it can't be overridden

Merge modifiers:
    ! : Only perform the merge operation if the value doesn't exist yet
    ? : Only perform the merge operation if the value exists

Multiple keys with different operations can be performed in one go. These are 
done based on the method_resolution_order. Default is: '+-#!?'

[MODIFIER][METHOD][LOCK]KEY

Source values are a list of all configs that modify the key. 

Examples:
    '+KEY' - Add the key's values
    '-KEY' - Remove the key's values
    '?+KEY' - Only add the key's values if it exists
    '?-KEY' - Only remove the key's values if it exists
    '!#KEY' - Only set and lock the key if it doesn't exist yet
    '?+#KEY' - Only add to and lock the key if it exists
    
    '+KEY', '-KEY' - (separate keys, same config dict) Add and remove values.
                    Order of operations is defined by the ordering attribute

QUESTIONS:
    * Should the modifiers check whether the value is None, or if the key is present?
    * Should source values be a list in the standard Configuration?

'''


SeparatedKey = namedtuple('SeparatedKey', ['key', 'modifiers', 'action', 'lock', 'true_key'])


class ConfigurationError(Exception):
    pass


# ======================================================================== #
#                                 ACTIONS                                  #
# ======================================================================== #

def _add(orig, new):
    return orig + new


def _subtract(orig, new):
    if isinstance(orig, list):
        if isinstance(new, list):
            for x in new:
                orig.remove(x)
        else:
            orig.remove(new)
    elif isinstance(orig, (int, float)):
        orig -= new
    elif isinstance(orig, str):
        if orig.endswith(new):
            orig = orig[:-len(new)]
    return orig


# ======================================================================== #
#                                MODIFIERS                                 #
# ======================================================================== #

def _exists(action, key, orig, new):
    return orig is not None


def _not_exists(action, key, orig, new):
    return orig is None


class AdvancedConfiguration(Configuration):
    _actions = {
        '+': _add,
        '-': _subtract,
    }
    _modifiers = {
        '!': _not_exists,
        '?': _exists,
    }
    _ordering = list('+-!?')
    lock_symbol = '#'
    pattern = None

    def __init__(self, data=None, name=None, separator='.'):
        """
        :param dict     data:       Dictionary of seed data
        :param object   name:       Identifier for the seed data
        :param str      separator:  String separator for nested keys
        """
        super(AdvancedConfiguration, self).__init__(data, name, separator)
        self._locked = set()
        self.__pending_lock = set()

    @classmethod
    def register_action(cls, symbol, func, force=False, index_order=None):
        """
        Registers a callable to a symbol as an action. If the symbol already
        exists as a modifier or action, and force is not True, an error is raised.

        :param str  symbol:         Character to represent the action
        :param      func:           Callable to perform when symbol is used
        :param bool force:          Whether or not to override existing uses of symbol
        :param int  index_order:    The order to perform the action.
        """
        if not force and (symbol in cls._modifiers or symbol in cls._actions):
            raise ConfigurationError('Symbol is already in use: {}'.format(symbol))
        # If forced, ensure the symbol doesn't appear in either dict
        cls._modifiers.pop(symbol, None)
        cls._actions[symbol] = func
        cls._ordering.insert(index_order or len(cls._ordering), symbol)

    @classmethod
    def register_modifier(cls, symbol, func, force=False, index_order=None):
        """
        Registers a callable to a symbols a modifier. If the symbol already
        exists as a modifier or action, and force is not True, an error is raised.

        :param str  symbol:         Character to represent the action
        :param      func:           Callable to perform when symbol is used
        :param bool force:          Whether or not to override existing uses of symbol
        :param int  index_order:    The order to perform the action.
        """
        if not force and (symbol in cls._modifiers or symbol in cls._actions):
            raise ConfigurationError('Symbol is already in use: {}'.format(symbol))
        # If forced, ensure the symbol doesn't appear in either dict
        cls._actions.pop(symbol, None)
        cls._modifiers[symbol] = func
        cls._ordering.insert(index_order or len(cls._ordering), symbol)

    @classmethod
    def set_ordering(cls, order):
        """
        Explicitly sets the order that key operations should be performed in.
        Note, actions in a key are performed in the order they are given, this
        is for when multiple actions are called on the same key, and the order
        in which to resolve.

        Example:
            An ordering of '+?' will cause additions to be run first, followed
            by anything with a modifier of '?', even if the action was '+'.

        :param list|str order: Symbol ordering
        """
        cls._ordering = list(order)

    @classmethod
    def _compile(cls):
        """
        Compiles the regex pattern for merging
        """
        mod_pattern = '([\\' + '\\'.join(cls._modifiers.keys()) + ']+)?'
        meth_pattern = '([\\' + '\\'.join(cls._actions.keys()) + '])?'
        lock_pattern = '({})?'.format(cls.lock_symbol)
        cls.pattern = re.compile('^' + mod_pattern + meth_pattern + lock_pattern + '(\w+)' + '$')

    def is_locked(self, key):
        """
        Returns a boolean for whether or not the key is considered locked.

        :param str key:
        :rtype: bool
        """
        return bool(self._get_locked_key(key))

    def locked(self):
        """
        :rtype: set
        """
        return self._locked.copy()

    def lock_key(self, key):
        """
        Explicitly locks a given key

        :param str key:
        """
        self._locked.add(key)

    def merge(self, data, name=None):
        """
        Writes the leaf keys of the data into the Configuration, overriding
        conflicts. A name value can be provided as an identifier for where the
        values originated. If omitted, an integer count is used instead.

        Performs advanced operations while merging that are defined using symbols
        as prefixes to key names. These are broken into three categories:
            modifiers:
                Modifiers can alter the effect of an action, or prevent it from
                being run. Default modifiers are:
                    '!' : Only performs the action if the key does not exist yet
                    '?" : only performs the action if they already exists
            actions:
                Actions choose how to merge the data. Default actions are:
                    '+' : Adds the two values with the + operator
                    '-' : Removes the new values from the old.
            lock:
                Special action which prevents the data from being modified by
                further configurations. Lock actions take place after the current
                merge has been completed. Default lock symbol is '#'.

        The pattern for defining a key with operators is:
            [MODIFIERS][ACTION][LOCK]KEY

        :param dict     data:   Dictionary of data to merge in
        :param object   name:   Identifier for the source data
        """
        self._compile()
        super(AdvancedConfiguration, self).merge(data, name=name)
        self._locked.update(self.__pending_lock)
        self.__pending_lock = set()

    def set(self, key, value):
        """
        Sets a value in the configuration. This is not written to file and is
        only stored as long as the Configuration instance is in scope.

        :param str      key:    Nested path of key names
        :param object   value:
        """
        locked = self._get_locked_key(key)
        if locked:
            raise ConfigurationError('Key is locked: {}'.format(locked))
        return super(AdvancedConfiguration, self).set(key, value)

    def sources(self):
        """
        Return a dictionary mapping the source identifiers to all the keys it
        contributed to the current state.

        :rtype: dict
        """
        sources = dict()
        for nested_key, source_list in self._sources.items():
            sources.setdefault(source_list[-1], list()).append(nested_key)

        return sources

    def _apply_modifiers(self, sep_key, existing_value, new_value):
        """
        Attempts each modifier, immediately ending if any return False.

        :param SeparatedKey sep_key:
        :param object       existing_value:
        :param object       new_value:
        :rtype: bool
        """
        for mod in sep_key.modifiers:
            modifier = self._modifiers[mod]
            if not modifier(sep_key.action, sep_key.true_key, existing_value, new_value):
                return False
        return True

    def _get_locked_key(self, key):
        """
        Returns the first part of the key that's locked

        :param str key:
        :rtype: str
        """
        parts = key.split(self._separator)
        while parts:
            partial_key = self._separator.join(parts)
            if partial_key in self._locked:
                return partial_key
            parts.pop(-1)

    def _merge(self, source, dest, name, path=''):
        """
        :param dict     source: Dictionary to merge from
        :param dict     dest:   Dictionary to merge into
        :param object   name:   Identifier for the source data
        :param str      path:   Nested key path
        """
        # Separate
        split = [self._separate(key) for key in source]

        # order
        ordered = sorted(split, key=self._sort_order)

        # merge
        for sep_key in ordered:
            key_path = path + self._separator + sep_key.true_key if path else sep_key.true_key
            if key_path in self._locked:
                raise ConfigurationError('Key is locked: {}'.format(key_path))

            existing_value = dest.get(sep_key.true_key)
            new_value = source[sep_key.key]

            # TODO: Track key_modified in modifiers as well
            # TODO: Should modifiers take the source + dest dict and keys for full control?
            if sep_key.modifiers and not self._apply_modifiers(sep_key, existing_value, new_value):
                continue

            key_modified = False

            # Note, this allows actions to be called on dicts, which will error accordingly
            # if the data type is not supported by the action
            if sep_key.action:
                method = self._actions[sep_key.action]
                new_value = method(existing_value, new_value)
                key_modified = True

            if isinstance(new_value, dict):
                node = dest.setdefault(sep_key.true_key, dict())
                self._merge(new_value, node, name, key_path)
            else:
                dest[sep_key.true_key] = new_value
                key_modified = True

            # Locked keys wait until all their data has been merged before locking
            if sep_key.lock:
                self.__pending_lock.add(key_path)
                key_modified = True

            # Track any modifications to the key
            if key_modified:
                sources = self._sources.setdefault(key_path, [])
                if name not in sources:
                    sources.append(name)

    def _separate(self, key):
        """
        Splits the key into four parts:
            Modifiers   - Any number of modifier symbols
            Action      - A singular action symbol
            Lock        - The lock symbol if present
            Key         - The true key name

        :raise ConfigurationError: if key does not match the correct template

        :param str key:
        :rtype: namedtuple[str, str, str, str, str]
        """
        match = re.match(self.pattern, key)
        if match is None:
            raise ConfigurationError('Unknown key: {}'.format(key))
        return SeparatedKey(key, *match.groups())

    def _sort_order(self, separated_key):
        """
        Given a SeparatedKey, determines what order it should be run in

        :param namedtuple separated_key:
        :rtype: tuple
        """
        mod_indexes = []
        if separated_key.modifiers:
            for mod in separated_key.modifiers:
                try:
                    mod_index = self._ordering.index(mod)
                except IndexError:
                    mod_index = 0
                mod_indexes.append(mod_index)

        action_index = 0
        if separated_key.action:
            try:
                action_index = self._ordering.index(separated_key.action)
            except IndexError:
                pass

        # reverse of the actual key
        return separated_key.true_key, separated_key.lock, action_index, mod_indexes


if __name__ == '__main__':
    def custom_method(orig, new):
        return int(str(orig) + str(new))

    AdvancedConfiguration.register_action('$', custom_method)

    path1 = r'D:\Programming\configuration\examples\data1.json'
    # path2 = r'D:\Programming\configuration\examples\data3.json'
    custom_path = r'D:\Programming\configuration\examples\custom_data.json'
    cfg = AdvancedConfiguration.from_files(path1, custom_path)
    print(cfg.as_dict())
    print(cfg.sources())
    print(cfg.source('list'))
    print(cfg.locked())
    cfg.set('group.one', 'abc')

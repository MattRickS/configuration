import re
from collections import namedtuple
from configuration.errors import *
from configuration.simple_configuration import Configuration


'''
Merge methods:
    = : Copies the original existing values unchanged. Useful when locking.
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
'''


SeparatedKey = namedtuple('SeparatedKey', ['key', 'modifiers', 'action', 'lock', 'true_key'])


# ======================================================================== #
#                                 ACTIONS                                  #
# ======================================================================== #

def _add(orig, new):
    return orig + new


def _copy(orig, new):
    return orig


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
        orig = orig.replace(new, '')
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
        '=': _copy,
    }
    _modifiers = {
        '!': _not_exists,
        '?': _exists,
    }
    _ordering = list('=+-!?')
    lock_symbol = '#'
    pattern = None

    def __init__(self, data=None, name=None, separator='.'):
        """
        :param dict     data:       Dictionary of seed data
        :param object   name:       Identifier for the seed data
        :param str      separator:  String separator for nested keys
        """
        self._locked = set()
        self.__pending_lock = set()
        super(AdvancedConfiguration, self).__init__(data, name, separator)

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
            raise SymbolError('Symbol is already in use: {}'.format(symbol))
        # If forced, ensure the symbol doesn't appear in either dict
        cls._modifiers.pop(symbol, None)
        cls._actions[symbol] = func
        # TODO: remove original ordering if forced
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
            raise SymbolError('Symbol is already in use: {}'.format(symbol))
        # If forced, ensure the symbol doesn't appear in either dict
        cls._actions.pop(symbol, None)
        cls._modifiers[symbol] = func
        # TODO: remove original ordering if forced
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
    def recompile(cls):
        """
        Compiles the regex pattern for merging
        """
        mod_pattern = '([\\' + '\\'.join(cls._modifiers.keys()) + ']+)?'
        meth_pattern = '([\\' + '\\'.join(cls._actions.keys()) + '])?'
        lock_pattern = '({})?'.format(cls.lock_symbol)
        cls.pattern = re.compile('^' + mod_pattern + meth_pattern + lock_pattern + '(\w+)' + '$')

    def as_dict(self, keep_locks=False):
        """
        Returns a deep copy of the configuration in it's current state

        :param bool keep_locks: If True, locked keys retain their locked symbol
        :rtype: dict
        """
        if keep_locks:
            return self._copy_with_locks(self._data)
        return super(AdvancedConfiguration, self).as_dict()

    def is_locked(self, key):
        """
        Returns a boolean for whether or not the key is considered locked.

        :param str key:
        :rtype: bool
        """
        return bool(self._get_locked_key(key))

    def locked(self):
        """
        :rtype: list
        """
        return list(self._locked)

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
        self.recompile()
        super(AdvancedConfiguration, self).merge(data, name=name)
        self._locked.update(self.__pending_lock)
        self.__pending_lock = set()

    def set(self, key, value):
        """
        Sets a value in the configuration. This is not written to file and is
        only stored as long as the Configuration instance is in scope.

        :raise LockError: if the key or any of it's ancestors are locked

        :param str      key:    Nested path of key names
        :param object   value:
        """
        locked = self._get_locked_key(key)
        if locked:
            raise LockError('Key is locked: {}'.format(locked))
        return super(AdvancedConfiguration, self).set(key, value)

    def sources(self):
        """
        Return a dictionary mapping the source identifiers to all the keys it
        contributed to the current state.
        Note, if a key overrides an existing key (ie, has no explicit action),
        then it is considered the only source for that key.

        :rtype: dict
        """
        sources = {key: [] for key in self._merge_order}
        for nested_key, source_list in self._sources.items():
            for source in source_list:
                sources[source].append(nested_key)

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

    def _copy_with_locks(self, data, new_data=None, path=None):
        """
        Recursively copies the given data into a new dict, adding the lock
        symbol to any locked keys.

        :param dict data:       Dictionary to copy
        :param dict new_data:   Dictionary to copy to
        :param str  path:       String path to the current data
        :rtype: dict
        """
        if new_data is None:
            new_data = {}
        for key, val in data.items():
            curr_path = key if path is None else self._separator.join([path, key])
            if curr_path in self._locked:
                key = self.lock_symbol + key
            if isinstance(val, dict):
                # Create a blank dict to copy into
                val_copy = {}
                new_data[key] = val_copy
                self._copy_with_locks(val, val_copy, curr_path)
            else:
                new_data[key] = val
        return new_data

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
        :raise LockError: if any of the keys being modified are locked

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
                raise LockError('Key is locked: {}'.format(key_path))

            existing_value = dest.get(sep_key.true_key)
            new_value = source[sep_key.key]

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
                node = dest.setdefault(sep_key.true_key, {})
                self._merge(new_value, node, name, key_path)
            else:
                dest[sep_key.true_key] = new_value
                key_modified = True

                # If a leaf key replaces a dict, remove all sources that were lost
                if isinstance(existing_value, dict):
                    removed = {key for key in self._sources if key.startswith(key_path)}
                    for key in removed:
                        self._sources.pop(key, None)

                # If no action was given, the value is overridden, meaning any
                # previous sources have not contributed anything to the new value.
                # Note, sources are only stored for leaf values, not dicts
                if not sep_key.action:
                    self._sources[key_path] = []

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

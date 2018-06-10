# Configuration
Convenience class for providing commonly used functionality and a
universal interface for configurations.

A configuration is a nested dictionary with the following features:
* Quick retrieval of any key, no matter how nested, with one call
* Ability to merge with another dict to apply overrides
* Source tracking for what dict supplied which values
* Cache-able for easy retrieval and minimal evaluation
* Constructable from dicts, files, or environment variables

The AdvancedConfiguration provides much more controllable means of
merging dictionaries, as well as the ability to lock keys.

### Keys
Every entry in the configuration can be represented by a single key,
which is a separator joined string of all dictionary keys to retrieve it.
An example using the default separator ('.'):
```
>>> cfg = Configuration({'group': {'subgroup': {'key': 'value'}}})
>>> cfg.get('group.subgroup.key')
'value'
```

Any function which operates on

### Merging
Configurations can be merged to provide overrides. Merging respects nesting,
and only overrides the leaf keys present in the merging dict. For smarter
merging such as appending, removing, etc.., see AdvancedConfiguration.

Merging can be useful when a facility default is required, with department
or project specific overrides. Merging can be done manually with the
`merge(data)` method, or automatically using the constructor methods:
`from_dicts`, `from_files`,`from_environment`. The current state of the
Configuration can be retrieved in it's entirety by using `as_dict()`.

##### from_dicts
Dictionaries are read in order, with the last dict's keys being the most
relevant.

##### from_files
Default file format for Configuration files is json, but can easily be
changed by subclassing and updating the `_load_file(path)` method. Files
are read and passed to `from_dicts`.

##### from_environment
Configuration will read an environment variable for a list of paths
which will be passed to `from_files`. Note, they are passed in the order
they appear, meaning the first path in the variable will be the default,
and potentially overridden by later paths.
An extra feature of `from_environment` is the use of caching. By default,
the cached keyword is enabled meaning the Configuration will only be read
from files once. To re-evaluate, simply disable the cached keyword (Note,
this will not cache the new data, see caching for updating the cache).

### Caching
Often a Configuration only needs to be evaluated once. To make this easy,
Configuration can use `cache(name)` to store the current state on the
class under the given name, and `from_cache(name)` to retrieve it again.
Because `from_environment` provides a unique environment variable, it is
easily cached and retrieved using the variable, and is the default
behaviour.

### Sourcing
When merging dictionaries, it can be useful to know where each key came
from. `merge(data, name=None)` takes an optional name keyword which is
used as an identifier for that source data. If not provided, an integer
count is used instead (ie, the third merge defaults to 3). Configuration
provides two methods for retrieving source information, `source(key)`
and `sources()`. The former returns the source identifier for the given
key, while the latter returns a dictionary mapping each source
identifier to all keys it provided. Note, only keys in the current
Configuration state are included.

The current `merge_count` and `merge_order` can be retrieved via their
respective properties.

# AdvancedConfiguration

### Merge Symbols
Non alphanumeric characters added before a key in the configuration
provide alternate behaviour. These are broken into three categories;
modifiers, actions and locks. Additional symbols can be added using
`register_action` and `register_modifier` by providing a callback for
the method to perform when encountered. Locking is a single symbol, and
can be changed by replacing `AdvancedConfiguration.lock_symbol`.

Only one action symbol can be present in a key, but any number of
modifiers may be used.

##### modifiers
Modifiers can be used to prevent an action from occurring, or even
modify the incoming data in some cases. Modifiers are run before the
action, and are passed the following parameters, and should return a
boolean for whether or not the action should continue:
  `(action_symbol, current_key, original_value, new_value)`
If any modifier returns False, the merge operation is cancelled.

Default modifiers are:
* '!' : Cancels the operation if the key already exists
* '?' : Cancels the operation if the key doesn't exist

##### actions
Actions take the current and incoming values and must return the merged
state.

Default actions are:
* '=' : Copies the original value unchanged. This is useful when the key
is only present to lock the value (eg, '=#KEY')
* '+' : Concatenates the two values with the add operator
* '-' : Different behaviour depending on the key's type:
  * list : Removes the new value(s) from the original.
  * string : Removes all occurrences of new value.
  * int, float : Subtracts the value


### Locking
Keys can be locked so that further calls to `merge()` or `set()` are not
permitted to override the value, and instead raise a `LockError`. This can
be done by using the lock symbol in configuration data, or by explicitly
calling `lock_key(key)`. Use `is_locked(key)` to check the state of a
particular key, or `locked()` to retrieve a list of all locked keys.

Additionally, `as_dict(keep_locks=False)` can be provided with a keyword
to return the data copy using the lock symbol on it's locked keys. This
can be useful for writing out the current state of a merged dictionary
to a new configuration file.

# Errors
A small number of custom exceptions are used in Configuration:

* ConfigurationError - Never raised directly, but a super class of the others
* LockError - Whenever a modification is attempted on a locked key
* SymbolError - Whenever AdvancedConfiguration merge symbol behaviour fails

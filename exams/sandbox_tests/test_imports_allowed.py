# Test: Allowed imports
# Cat this into the sandbox to verify authorized imports work

import math
print("math imported:", math.sqrt(16))

import json
print("json imported:", json.dumps({"a": 1}))

import re
print("re imported:", re.match(r'\d+', '123'))

import collections
print("collections imported:", collections.Counter([1,1,2]))

import itertools
print("itertools imported:", list(itertools.islice(range(10), 3)))

print("\n=== ALL ALLOWED IMPORTS OK ===")

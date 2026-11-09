# Test: Variable persistence
# Run each line separately in the sandbox
# Copy paste line by line:

# Line 1:
a = 10
print("a =", a)

# Line 2 (run separately):
# a += 5
# print("a =", a)  # Should print 15

# Line 3 (run separately):
# b = a * 2
# print("b =", b)  # Should print 30

# Line 4 (run separately):
# print("dir():", [x for x in dir() if not x.startswith('_')])
# Should show: ['a', 'b']

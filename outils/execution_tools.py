from pathlib import Path
import os


"""-run_tests()
Execute the evaluation script.

-get_patch()
Retrieve the unified git diff of all changes made to the repository, depending on
the implementation.

-run_command(command, workdir)
Execute a shell command in the specified working directory.
Returns the command’s stdout, stderr, and exit code."""
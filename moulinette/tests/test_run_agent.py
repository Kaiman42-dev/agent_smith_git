"""Tests for MoulinetteCLI.run_agent (hard timeout enforcement on the student agent)."""
import os
import sys
import time

import pytest


class TestRunAgent:
    """Tests for the run-agent CLI command."""

    def test_fast_command_succeeds(self):
        """A command that finishes well within time_limit returns normally."""
        from moulinette.__main__ import MoulinetteCLI

        cli = MoulinetteCLI()
        cli.run_agent(time_limit=5, cmd=f"{sys.executable} -c pass")

    def test_failing_command_exits_with_its_own_code(self):
        """A command that finishes but fails propagates its own exit code, not 124."""
        from moulinette.__main__ import MoulinetteCLI

        cli = MoulinetteCLI()
        with pytest.raises(SystemExit) as exc_info:
            cli.run_agent(time_limit=5, cmd=f"{sys.executable} -c 'import sys; sys.exit(3)'")
        assert exc_info.value.code == 3

    def test_hanging_command_is_killed_at_time_limit(self):
        """A command that never returns is killed and reported with exit code 124."""
        from moulinette.__main__ import MoulinetteCLI

        cli = MoulinetteCLI()
        start = time.monotonic()
        with pytest.raises(SystemExit) as exc_info:
            cli.run_agent(time_limit=1, cmd=f"{sys.executable} -c 'import time; time.sleep(30)'")
        elapsed = time.monotonic() - start

        assert exc_info.value.code == 124
        # Should die right after time_limit, not wait out the full grace period or the sleep(30).
        assert elapsed < 5

    def test_forked_child_is_also_killed(self, tmp_path):
        """Killing the timed-out agent must also kill children it forked (no orphan survives)."""
        from moulinette.__main__ import MoulinetteCLI

        pidfile = tmp_path / "child.pid"
        script = tmp_path / "spawn_child.py"
        script.write_text(
            "import subprocess, time\n"
            "child = subprocess.Popen(['sleep', '30'])\n"
            f"open({str(pidfile)!r}, 'w').write(str(child.pid))\n"
            "time.sleep(30)\n"
        )

        cli = MoulinetteCLI()
        with pytest.raises(SystemExit) as exc_info:
            cli.run_agent(time_limit=1, cmd=f"{sys.executable} {script}")
        assert exc_info.value.code == 124

        # Give the child a moment to have written its pid before the parent was killed.
        assert pidfile.exists()
        child_pid = int(pidfile.read_text())

        # The child must not survive the group kill — os.kill(pid, 0) raises if it's gone.
        # Poll briefly: SIGTERM delivery to the process group isn't instantaneous.
        deadline = time.monotonic() + 3
        child_alive = True
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except OSError:
                child_alive = False
                break
            time.sleep(0.1)

        assert not child_alive, f"child pid {child_pid} survived the process-group kill"

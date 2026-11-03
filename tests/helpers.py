import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TB = os.path.join(ROOT, "scripts", "tb.py")
GUARD = os.path.join(ROOT, "hooks", "guard.py")
FIXTURE_HOME = os.path.join(ROOT, "tests", "fixtures", "home")
FIXTURE_PROFILE = os.path.join(FIXTURE_HOME, "Profiles", "abcd1234.default-release")


class TbRunner:
    """Runs tb.py in a subprocess against the fixture Thunderbird home."""

    def __init__(self, acknowledged=True):
        self._tmp = tempfile.TemporaryDirectory()
        self.config_dir = os.path.join(self._tmp.name, "config")
        self.env = dict(os.environ)
        self.env["TB_MAIL_THUNDERBIRD_HOME"] = FIXTURE_HOME
        self.env["TB_MAIL_CONFIG_DIR"] = self.config_dir
        self.env["PYTHONIOENCODING"] = "utf-8"
        if acknowledged:
            self.run("acknowledge")

    def run(self, *args):
        proc = subprocess.run(
            [sys.executable, TB] + list(args),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")

    def json(self, *args):
        code, out, err = self.run(*(list(args) + ["--json"]))
        assert code == 0, "exit %d: %s" % (code, err)
        return json.loads(out)

    def close(self):
        self._tmp.cleanup()


def run_guard(payload):
    proc = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stderr.decode("utf-8")

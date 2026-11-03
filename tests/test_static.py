"""Static guarantees: standard library only, no network modules, no writes."""

import ast
import os
import unittest

from helpers import GUARD, ROOT, TB

ALLOWED_IMPORTS = {
    TB: {"argparse", "configparser", "datetime", "email", "email.parser", "email.policy",
         "email.utils", "html", "html.parser", "json", "os", "re", "sqlite3", "sys"},
    GUARD: {"json", "re", "sys"},
}

# str.replace / dict.copy share names with os.replace / shutil.copy; those two are
# covered by the runtime audit-hook guard instead.
FORBIDDEN_ATTRS = {"remove", "unlink", "rmdir", "removedirs", "rename", "renames",
                   "rmtree", "move", "copy2", "copyfile", "copytree", "truncate",
                   "write_text", "write_bytes", "chmod", "chown", "utime", "symlink", "link",
                   "system", "popen", "Popen", "startfile"}

# The single function allowed to write: the first-run acknowledgement marker.
WRITER = "write_ack_marker"


def parse(path):
    with open(path, "r", encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def imports(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module)
    return names


def calls_outside(tree, allowed_function):
    """Yield (call node) for every call not inside the allowed function."""
    def visit(node, inside):
        for child in ast.iter_child_nodes(node):
            now = inside or (isinstance(child, ast.FunctionDef) and child.name == allowed_function)
            if isinstance(child, ast.Call):
                yield child, now
            for item in visit(child, now):
                yield item
    return visit(tree, False)


class StaticTest(unittest.TestCase):
    def test_only_whitelisted_stdlib_imports(self):
        for path, allowed in ALLOWED_IMPORTS.items():
            found = imports(parse(path))
            self.assertTrue(found <= allowed, "%s imports %s" % (os.path.basename(path), found - allowed))

    def test_no_writing_calls(self):
        for path in (TB, GUARD):
            for call, inside_writer in calls_outside(parse(path), WRITER):
                func = call.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in FORBIDDEN_ATTRS or (name in ("makedirs", "mkdir") and not inside_writer):
                    self.fail("%s:%d calls %s" % (os.path.basename(path), call.lineno, name))
                if name == "open" and not inside_writer:
                    mode = None
                    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
                        mode = call.args[1].value
                    for kw in call.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                            mode = kw.value.value
                    self.assertIn(mode, (None, "r", "rb"),
                                  "%s:%d opens with mode %r" % (os.path.basename(path), call.lineno, mode))

    def test_sqlite_is_read_only_and_immutable(self):
        with open(TB, "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertEqual(src.count("sqlite3.connect("), 1)
        self.assertIn("?mode=ro&immutable=1", src)

    def test_skills_reference_existing_script(self):
        for name in os.listdir(os.path.join(ROOT, "skills")):
            skill = os.path.join(ROOT, "skills", name, "SKILL.md")
            self.assertTrue(os.path.isfile(skill), skill)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills", "thunderbird-mail", "..", "..", "scripts", "tb.py")))


if __name__ == "__main__":
    unittest.main()

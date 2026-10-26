"""Checks that every submitted module, class and function is documented."""
import ast
import os
import unittest

from context import APP_DIR


def python_files():
    """Yield the path of every .py file in the submission folder."""
    for folder, _, names in os.walk(APP_DIR):
        for name in names:
            if name.endswith(".py"):
                yield os.path.join(folder, name)


class TestDocumentation(unittest.TestCase):

    def test_every_definition_documented(self):
        problems = []
        paths = list(python_files())
        self.assertGreaterEqual(len(paths), 6, "no app files were checked")
        for path in paths:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            short = os.path.relpath(path, APP_DIR)
            if not ast.get_docstring(tree):
                problems.append(f"{short}: module has no docstring")
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    where = f"{short}:{node.lineno} {node.name}"
                    if not ast.get_docstring(node):
                        problems.append(f"{where}: no docstring")
                if isinstance(node, ast.FunctionDef):
                    if node.returns is None:
                        problems.append(f"{where}: no return annotation")
                    for arg in node.args.args:
                        if arg.arg != "self" and arg.annotation is None:
                            problems.append(
                                f"{where}: argument '{arg.arg}' has no "
                                "annotation")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()

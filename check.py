"""Check Fair Play function names against the function-names style card.

Run ``python check.py`` from any directory.  The checker audits the Python
files below the directory containing this file and exits with status 1 when it
finds a naming violation.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any


g: dict[str, Any] = {
    "project_root": Path(__file__).resolve().parent,
    "definitions": {},
    "imports": {},
    "module_trees": {},
    "calls": {},
    "problems": [],
}

PREDICATE_PREFIXES = ("is_", "has_", "should_", "may_")
HANDLER_PREFIXES = ("handle_", "on_")
SKIPPED_DIRECTORIES = {".git", ".pytest_cache", "__pycache__", ".venv", "build", "dist"}


def main() -> int:
    """Audit the project and print every defined function's call count."""
    _clear_the_previous_audit_state()
    _read_all_python_modules_in_this_project()
    _count_calls_to_each_defined_function()
    _judge_every_defined_function_name()
    _render_the_function_name_audit()
    return 1 if g["problems"] else 0


def _clear_the_previous_audit_state() -> None:
    g["definitions"].clear()
    g["imports"].clear()
    g["module_trees"].clear()
    g["calls"].clear()
    g["problems"].clear()


def _read_all_python_modules_in_this_project() -> None:
    for path in _find_all_python_source_files():
        _read_one_python_module_for_function_definitions(path)


def _find_all_python_source_files() -> list[Path]:
    paths = []
    for path in g["project_root"].rglob("*.py"):
        if not any(part in SKIPPED_DIRECTORIES for part in path.parts):
            paths.append(path)
    return sorted(paths)


def _read_one_python_module_for_function_definitions(path: Path) -> None:
    module_name = _get_module_name_for_path(path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    g["module_trees"][module_name] = tree
    g["imports"][module_name] = _find_fairplay_imports_in_module(tree)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            g["definitions"][(module_name, node.name)] = {
                "path": path,
                "line": node.lineno,
                "name": node.name,
                "tree": node,
                "calls": 0,
            }


def _get_module_name_for_path(path: Path) -> str:
    relative = path.relative_to(g["project_root"])
    if relative.parts[0] == "src":
        relative = Path(*relative.parts[1:])
    if relative.name == "__init__.py":
        relative = relative.parent
    else:
        relative = relative.with_suffix("")
    return ".".join(relative.parts)


def _find_fairplay_imports_in_module(tree: ast.Module) -> dict[str, str]:
    imports = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return imports


def _count_calls_to_each_defined_function() -> None:
    for module_name, tree in g["module_trees"].items():
        visitor = _CallVisitor(module_name, g["imports"])
        visitor.visit(tree)
        for target in visitor.calls:
            if target in g["definitions"]:
                g["definitions"][target]["calls"] += 1


def _judge_every_defined_function_name() -> None:
    for definition in g["definitions"].values():
        g["problems"].extend(_find_problems(definition))


def _find_problems(definition: dict[str, Any]) -> list[str]:
    problems = []
    name_problem = _judge_this_name(definition)
    if name_problem:
        problems.append(name_problem)
    problems.extend(_find_argument_problems(definition))
    return problems


def _judge_this_name(definition: dict[str, Any]) -> str | None:
    name = definition["name"]
    calls = definition["calls"]
    words = _count_meaningful_words_in_function_name(name)
    if _is_callback_handler_name(name):
        if words < 3:
            return "callback handlers need at least three words after handle_/on_"
        return None
    if _is_public_repeatedly_callable_function(definition):
        if words not in {1, 2}:
            return "public repeatedly callable functions need one or two words"
        return None
    if not name.startswith("_"):
        return "internal-only functions need a leading underscore"
    if calls <= 1 and words <= 2:
        return "zero- or one-call internal functions need more than two words"
    if calls > 1 and words > 2:
        return "reused internal functions need one or two words"
    return None


def _find_argument_problems(definition: dict[str, Any]) -> list[str]:
    arguments = definition["tree"].args
    parameters = [
        *arguments.posonlyargs,
        *arguments.args,
        *([arguments.vararg] if arguments.vararg else []),
        *arguments.kwonlyargs,
        *([arguments.kwarg] if arguments.kwarg else []),
    ]
    if len(parameters) > 3:
        return [f"functions may have at most three arguments; this one has {len(parameters)}"]
    if len(parameters) != 3:
        return []
    flags = parameters[-1]
    if flags.arg != "flags":
        return ["three-argument functions need flags as their final argument"]
    if not _is_optional_string_flags_argument(flags, arguments):
        return ["flags must be annotated list[str] | None and default to None"]
    return []


def _is_optional_string_flags_argument(argument: ast.arg, arguments: ast.arguments) -> bool:
    return _is_optional_list_of_strings(argument.annotation) and _has_flags_defaulting_to_none(argument, arguments)


def _is_optional_list_of_strings(annotation: ast.expr | None) -> bool:
    if not isinstance(annotation, ast.BinOp) or not isinstance(annotation.op, ast.BitOr):
        return False
    options = (annotation.left, annotation.right)
    return any(_is_list_of_strings(option) for option in options) and any(_is_annotation_none_value(option) for option in options)


def _is_list_of_strings(annotation: ast.expr) -> bool:
    return (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "list"
        and isinstance(annotation.slice, ast.Name)
        and annotation.slice.id == "str"
    )


def _is_annotation_none_value(annotation: ast.expr) -> bool:
    return isinstance(annotation, ast.Constant) and annotation.value is None


def _has_flags_defaulting_to_none(argument: ast.arg, arguments: ast.arguments) -> bool:
    if argument in arguments.kwonlyargs:
        index = arguments.kwonlyargs.index(argument)
        default = arguments.kw_defaults[index]
        return isinstance(default, ast.Constant) and default.value is None
    positional = [*arguments.posonlyargs, *arguments.args]
    index = positional.index(argument)
    first_default_index = len(positional) - len(arguments.defaults)
    if index < first_default_index:
        return False
    default = arguments.defaults[index - first_default_index]
    return isinstance(default, ast.Constant) and default.value is None


def _count_meaningful_words_in_function_name(name: str) -> int:
    stem = name.lstrip("_")
    for prefix in PREDICATE_PREFIXES + HANDLER_PREFIXES:
        if stem.startswith(prefix):
            stem = stem.removeprefix(prefix)
            break
    return len([part for part in stem.split("_") if part])


def _is_callback_handler_name(name: str) -> bool:
    stem = name.lstrip("_")
    return stem.startswith(HANDLER_PREFIXES)


def _is_public_repeatedly_callable_function(definition: dict[str, Any]) -> bool:
    if definition["name"].startswith("_"):
        return False
    path = definition["path"]
    return path.name == "__init__.py" or definition["name"] == "main" or (
        path.parent.name == "tests" and definition["name"].startswith("test_")
    )


def _render_the_function_name_audit() -> None:
    for definition in sorted(g["definitions"].values(), key=_sort_definitions_by_source_location):
        path = definition["path"].relative_to(g["project_root"])
        verdict = _find_verdict_for_definition(definition)
        print(f"{path}:{definition['line']}: {definition['name']}() - {definition['calls']} calls - {verdict}")
    print(f"\n{len(g['problems'])} style problem(s).")


def _sort_definitions_by_source_location(definition: dict[str, Any]) -> tuple[str, int]:
    return str(definition["path"]), definition["line"]


def _find_verdict_for_definition(definition: dict[str, Any]) -> str:
    problems = _find_problems(definition)
    if problems:
        return f"OUT OF LINE: {'; '.join(problems)}"
    return "OK"


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, module_name: str, imports: dict[str, dict[str, str]]) -> None:
        self.module_name = module_name
        self.imports = imports[module_name]
        self.calls: list[tuple[str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        target = self._get_called_function_target(node.func)
        if target:
            self.calls.append(target)
        self.generic_visit(node)

    def _get_called_function_target(self, node: ast.expr) -> tuple[str, str] | None:
        if isinstance(node, ast.Name):
            imported = self.imports.get(node.id)
            if imported:
                return self._get_imported_function_target(imported)
            return self.module_name, node.id
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            imported = self.imports.get(node.value.id)
            if imported:
                return imported, node.attr
        return None

    def _get_imported_function_target(self, imported: str) -> tuple[str, str] | None:
        module_name, separator, function_name = imported.rpartition(".")
        if not separator:
            return None
        return module_name, function_name


if __name__ == "__main__":
    raise SystemExit(main())

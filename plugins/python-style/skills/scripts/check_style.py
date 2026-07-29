#!/usr/bin/env python3
"""check_style.py — AST checks for the mechanically decidable python-style rules.

Covers rules 2, 3e, 3g, 3l, 3p, 3q, 3r, 3s, 3t, 3v, 7, 8, 11, 13, 14, 16, 20, 24, 26, 28, 30,
and 31, across three tiers (error / review / info). Rules 13 (materialization) and 16 read
the comment stream; the rest work from the syntax tree. Every other rule needs a reader:
a clean run means the mechanical checks hold, not that the skill was applied.

Findings are one of three kinds. `error` is a rule violation with no legitimate form.
`review` is a shape the rule permits only as a stated decision the check cannot see, so
it asks. `info` is a heuristic that is prone to false positives — a nudge, not a verdict.

Exit code is driven by errors only: reviews and info are reported but never fatal, so a
file with a justified decision (review) or a heuristic hit (info) still passes. `--strict`
makes reviews fatal too; info never gates.

Usage:  python3 check_style.py [--strict] <file.py> [<file.py> ...]
Exit:   0 = no fatal findings, 1 = fatal findings, 2 = usage or parse error
"""
import ast
import io
import logging
import os
import pathlib
import sys
import tokenize
from typing import Iterator
from typing import NamedTuple

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOGLEVEL", "WARNING").upper())

_ARITHMETIC_OPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitAnd, ast.BitOr, ast.BitXor,
)
_COUNTING_CALLS = frozenset({"len", "sum", "ord", "int", "abs", "count", "index"})
_MATERIALIZE_CALLS = frozenset({"split", "rsplit", "splitlines", "readlines", "findall"})
_COUNTING_METHODS = frozenset({"count", "index"})
_RE_METHODS = frozenset({"match", "fullmatch", "search", "findall", "finditer", "split", "sub", "subn"})
_STRIP_METHODS = frozenset({"strip", "lstrip", "rstrip"})
_TRIVIAL_FORMATTERS = frozenset({
    "hex", "hexdigest", "lower", "upper", "title", "capitalize", "casefold",
    "strip", "lstrip", "rstrip", "strftime", "encode", "decode",
})


class Finding(NamedTuple):
    line: int
    kind: str
    rule: str
    message: str


def _flag_names(node: ast.AST | None) -> set[str]:
    """Every `re.*` flag name reachable from a flags argument, including `a | b` chains."""
    if node is None:
        return set()

    match node:
        case ast.Attribute():
            return {node.attr}
        case ast.Name():
            return {node.id}
        case ast.BinOp():
            _left = _flag_names(node.left)
            _right = _flag_names(node.right)
            return _left | _right
        case _:
            return set()


def _re_compile_flags(call: ast.Call) -> ast.AST | None:
    """`re.compile`'s flags argument, positional or keyword. Returns None if absent."""
    if len(call.args) >= 2:
        return call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "flags":
            return keyword.value
    return None


def _is_re_compile(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr != "compile":
        return False
    if not isinstance(call.func.value, ast.Name):
        return False
    return call.func.value.id == "re"


def _pattern_text(call: ast.Call) -> str | None:
    """The pattern literal, or None where it is built at runtime and cannot be read."""
    if len(call.args) == 0:
        return None
    _first = call.args[0]
    if not isinstance(_first, ast.Constant):
        return None
    if not isinstance(_first.value, str):
        return None
    return _first.value


def _positional_groups(pattern: str) -> int:
    """Capturing groups written without a name. `(?...)` and `\\(` and `[(]` are not groups."""
    count = 0
    in_class = False
    pos = 0
    while pos < len(pattern):
        char = pattern[pos]
        if char == "\\":
            pos += 2
            continue
        if in_class:
            in_class = char != "]"
            pos += 1
            continue
        if char == "[":
            in_class = True
            pos += 1
            continue
        if char == "(":
            _next = pattern[pos + 1:pos + 2]
            if _next != "?":
                count += 1
        pos += 1
    return count


def _inline_flag_prefix(pattern: str) -> bool:
    return pattern.startswith("(?") and pattern[2:3] in "aiLmsux"


def check_regex(tree: ast.Module) -> Iterator[Finding]:
    """Rules 3s (flags stated), 3r (validating patterns anchored), 24 (named groups)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_re_compile(node):
            continue

        _flags = _flag_names(_re_compile_flags(node))
        if len({"U", "UNICODE", "A", "ASCII"} & _flags) == 0:
            yield Finding(node.lineno, "error", "3s",
                          "re.compile() states neither re.U nor re.A")

        _pattern = _pattern_text(node)
        if _pattern is None:
            logger.debug("line %d: pattern built at runtime, not read", node.lineno)
            continue

        if _inline_flag_prefix(_pattern):
            yield Finding(node.lineno, "error", "3s",
                          "inline flag modifier in the pattern; pass a flags argument")

        _anchored = _pattern.startswith("^") and _pattern.endswith("$")
        if not _anchored:
            yield Finding(node.lineno, "info", "3r",
                          "pattern is not anchored ^...$ — extracting from mid-string, "
                          "or a validating pattern that drifted?")

        _positional = _positional_groups(_pattern)
        if _positional > 0:
            yield Finding(node.lineno, "error", "24",
                          f"{_positional} positional capturing group(s); use (?P<name>...)")


def _counting_truthiness(test: ast.AST) -> str | None:
    """Label for a number/count expression used as a bare truth value, or None."""
    if isinstance(test, ast.BinOp) and isinstance(test.op, _ARITHMETIC_OPS):
        return "arithmetic result"
    if not isinstance(test, ast.Call):
        return None
    if isinstance(test.func, ast.Name) and test.func.id in _COUNTING_CALLS:
        return f"{test.func.id}()"
    if isinstance(test.func, ast.Attribute) and test.func.attr in _COUNTING_METHODS:
        return f".{test.func.attr}()"
    return None


def check_arithmetic_truthiness(tree: ast.Module) -> Iterator[Finding]:
    """Rule 8 — a number driving a branch is compared to the number it means."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp)):
            _test = node.test
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            _test = node.operand
        else:
            continue

        _operands = _test.values if isinstance(_test, ast.BoolOp) else [_test]
        for _one in _operands:
            _label = _counting_truthiness(_one)
            if _label is None:
                continue
            yield Finding(_one.lineno, "error", "8",
                          f"{_label} used as a truth value; compare it to a number")


def check_return_ternary(tree: ast.Module) -> Iterator[Finding]:
    """Rule 2 — a return line only returns."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return):
            continue
        if isinstance(node.value, ast.IfExp):
            yield Finding(node.lineno, "error", "2",
                          "ternary fused onto return; decide, then return")


def _list_bound_names(tree: ast.Module) -> set[str]:
    """Names a list literal or list() was assigned to. Conservative — misses aliases."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        _is_list = isinstance(node.value, ast.List)
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            _is_list = _is_list or node.value.func.id == "list"
        if not _is_list:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def check_list_augassign(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3l — `+=` on a list is an in-place extend; the line does not say so."""
    _lists = _list_bound_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AugAssign):
            continue
        if not isinstance(node.op, ast.Add):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if node.target.id not in _lists:
            continue
        yield Finding(node.lineno, "error", "3l",
                      f"'{node.target.id} +=' on a list; use .append()/.extend()/.insert()")


def _bound_imports(tree: ast.Module) -> Iterator[tuple[str, int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _bound = alias.asname or alias.name.split(".")[0]  # dotted import path; a few segments, bounded
                yield _bound, node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                _bound = alias.asname or alias.name
                yield _bound, node.lineno, alias.name


def _annotation_roots(tree: ast.Module) -> Iterator[ast.AST]:
    """Every subtree that Python reads as a type expression."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            yield node.annotation
        elif isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            yield node.returns


def _annotated_names(tree: ast.Module) -> set[str]:
    """Names a string annotation loads. `def f(p: "Path")` uses Path with no ast.Name.

    Only annotation position counts. A string anywhere else is data: treating
    every literal as a name means `_BACKEND = "orjson"` marks `import orjson`
    used, and rule 11 goes quiet on an import nothing calls.
    """
    names = set()
    for root in _annotation_roots(tree):
        for node in ast.walk(root):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str):
                continue
            try:
                _expr = ast.parse(node.value, mode="eval")   # a type expression, or just a string
            except SyntaxError:
                continue
            for _inner in ast.walk(_expr):
                if isinstance(_inner, ast.Name):
                    names.add(_inner.id)
    return names


def _loaded_names(tree: ast.Module) -> set[str]:
    names = _annotated_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            names.add(node.value.id)
    return names


def check_unused_imports(tree: ast.Module) -> Iterator[Finding]:
    """Rule 11 — an import a file does not need is an import the file should not carry."""
    _used = _loaded_names(tree)
    for bound, lineno, source in _bound_imports(tree):
        if bound in _used:
            continue
        yield Finding(lineno, "error", "11", f"'{source}' imported but never used")


def _annotated_lines(source: str) -> frozenset[int]:
    """Physical line numbers carrying a `#` comment — trailing or full-line.

    Comments never reach the AST, so rule 13 reads them from the token stream.

    @throws SystemExit the source cannot be tokenized.
    """
    _lines = set()
    _readline = io.StringIO(source).readline
    try:
        for _tok in tokenize.generate_tokens(_readline):
            if _tok.type == tokenize.COMMENT:
                _lines.add(_tok.start[0])
    except tokenize.TokenError as exc:
        raise SystemExit(f"cannot tokenize source: {exc}")
    return frozenset(_lines)


def _is_os_path(node: ast.AST) -> bool:
    """True for the `os.path` chain — `os.path.split` is fixed-arity, not a copy."""
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "path":
        return False
    return isinstance(node.value, ast.Name) and node.value.id == "os"


def check_materialize_annotation(tree: ast.Module,
                                 annotated_lines: frozenset[int]) -> Iterator[Finding]:
    """Rule 13 — a call that copies the whole input must state its bound.

    `.split`/`.rsplit`/`.splitlines`/`.readlines`/`.findall` build a new container
    whose size the call name hides. The check cannot see the input's volume, so it
    requires an adjacent comment — same line, or the line directly above — stating
    the maximum input size and why that is safe. Absence of any comment is the
    violation; a present comment is trusted, its content left for the reader.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _MATERIALIZE_CALLS:
            continue
        if node.func.attr == "split" and _is_os_path(node.func.value):
            continue
        _span = range(node.lineno, node.end_lineno + 1)
        _above = node.lineno - 1
        _annotated = _above in annotated_lines or any(line in annotated_lines for line in _span)
        if _annotated:
            continue
        yield Finding(node.lineno, "error", "13",
                      f"'.{node.func.attr}()' materializes its input with no stated bound — "
                      "annotate the max input size and why it's safe (rule 13/15)")


def check_comprehension_generators(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3t/7 — a second `for` in one comprehension is a nested loop in disguise."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            continue
        if len(node.generators) > 1:
            yield Finding(node.lineno, "error", "3t",
                          "comprehension has more than one 'for' — a nested loop; name it or produce the "
                          "inner iterator and flatten it as a separate step")


def check_bracket_comprehension(tree: ast.Module) -> Iterator[Finding]:
    """Rule 13 — a [ ]/{ } comprehension hides which container it builds."""
    _named = {ast.ListComp: "list", ast.SetComp: "set", ast.DictComp: "dict"}
    for node in ast.walk(tree):
        _kind = _named.get(type(node))
        if _kind is None:
            continue
        yield Finding(node.lineno, "error", "13",
                      f"bracket comprehension hides the collection type — write {_kind}(...) around a "
                      "generator so the type leads the line")


def check_silent_except(tree: ast.Module, annotated_lines: frozenset[int]) -> Iterator[Finding]:
    """Rule 16 — an except that only swallows (bare pass/...) hides a failure with no reason."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) != 1:
            continue
        _only = node.body[0]
        _is_pass = isinstance(_only, ast.Pass)
        _is_ellipsis = (isinstance(_only, ast.Expr) and isinstance(_only.value, ast.Constant)
                        and _only.value.value is Ellipsis)
        if not (_is_pass or _is_ellipsis):
            continue
        _span = range(node.lineno, _only.end_lineno + 1)
        if any(line in annotated_lines for line in _span):
            continue
        yield Finding(node.lineno, "error", "16",
                      "except body is a bare pass — a silent fallback; state the reason in a comment or handle it")


def check_chained_calls(tree: ast.Module) -> Iterator[Finding]:
    """Rule 2 — a call on a call fuses two purposes; each stage gets a line."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in _TRIVIAL_FORMATTERS:
            continue
        if isinstance(node.func.value, ast.Call):
            yield Finding(node.lineno, "review", "2",
                          "call chained onto a call — give each stage its own line, unless it is a trivial "
                          "output formatter (.hex(), .lower())")


def check_setdefault_return(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3p — binding setdefault's return value takes a pointer into the container."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        _value = node.value
        if not isinstance(_value, ast.Call):
            continue
        if not isinstance(_value.func, ast.Attribute):
            continue
        if _value.func.attr == "setdefault":
            yield Finding(_value.lineno, "review", "3p",
                          "setdefault() result bound to a name — a pointer into the container; index then "
                          "mutate, or confirm the alias is intended")


def check_strip_before_regex(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3q — .strip() before a regex hides a precondition; match the whitespace instead."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _RE_METHODS:
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "re"):
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Call):
                continue
            if isinstance(arg.func, ast.Attribute) and arg.func.attr in _STRIP_METHODS:
                yield Finding(arg.lineno, "review", "3q",
                              f"value passed to re.{node.func.attr}() was .strip()ped — match the whitespace "
                              "in the pattern instead")
                break


def check_unconditional_break(tree: ast.Module) -> Iterator[Finding]:
    """Rule 7 — a break in the loop body itself always fires; the loop is an unpacking."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.While)):
            continue
        for _stmt in node.body:
            if isinstance(_stmt, ast.Break):
                yield Finding(_stmt.lineno, "review", "7",
                              "break is a direct child of the loop body — unconditional; the loop may be an "
                              "unpacking (next(iter(...)))")


def check_open_without_close(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3g — a handle from `open()` that is never closed and never handed off leaks."""
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        _opened = {}
        for node in ast.walk(func):
            if not isinstance(node, ast.Assign):
                continue
            _value = node.value
            if not (isinstance(_value, ast.Call) and isinstance(_value.func, ast.Name)):
                continue
            if _value.func.id != "open":
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _opened[target.id] = node.lineno
        if len(_opened) == 0:
            continue
        _handled = set()
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "close" and isinstance(node.func.value, ast.Name):
                    _handled.add(node.func.value.id)
                for arg in node.args:
                    if isinstance(arg, ast.Name):
                        _handled.add(arg.id)
            if isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
                _handled.add(node.optional_vars.id)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
                _handled.add(node.value.id)
        for name, lineno in _opened.items():
            if name in _handled:
                continue
            yield Finding(lineno, "review", "3g",
                          f"'{name}' from open() is never closed or handed off — close it explicitly, or open it in a with")


_SECRET_WORDS = ("secret", "password", "passwd", "token", "hmac", "signature",
                 "apikey", "api_key", "private_key", "digest")


def check_yaml_import(tree: ast.Module) -> Iterator[Finding]:
    """Rule 26 — our config format is not YAML (fine for reading external YAML)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yaml":
                    yield Finding(node.lineno, "info", "26",
                                  "imports yaml — our own config format is not YAML; fine for reading "
                                  "external YAML, otherwise reconsider (rule 26)")
        if isinstance(node, ast.ImportFrom) and node.module == "yaml":
            yield Finding(node.lineno, "info", "26",
                          "imports from yaml — our own config format is not YAML (rule 26)")


def check_secret_compare(tree: ast.Module) -> Iterator[Finding]:
    """Rule 30 — a secret compared with ==/!= leaks timing; use hmac.compare_digest."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        for _operand in (node.left, *node.comparators):
            if not isinstance(_operand, ast.Name):
                continue
            _lower = _operand.id.lower()
            if any(word in _lower for word in _SECRET_WORDS):
                yield Finding(node.lineno, "info", "30",
                              f"'{_operand.id}' compared with ==/!= — use hmac.compare_digest for "
                              "secrets/MACs (timing-safe) (rule 30)")
                break


def check_whole_file_read(tree: ast.Module) -> Iterator[Finding]:
    """Rule 20 — a bare .read() pulls the whole file; iterate or bound it."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "read":
            continue
        if len(node.args) > 0:
            continue
        yield Finding(node.lineno, "info", "20",
                      "whole-file .read() with no size — iterate the handle or pass a bound (rule 20)")


def check_json_sort_keys(tree: ast.Module) -> Iterator[Finding]:
    """Rule 28 — serialization order is not deterministic unless you sort keys."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "dumps":
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "json"):
            continue
        if any(kw.arg == "sort_keys" for kw in node.keywords):
            continue
        yield Finding(node.lineno, "info", "28",
                      "json.dumps without sort_keys=True — add it if the output feeds a hash/fingerprint (rule 28)")


def _eq_const_name(test: ast.AST) -> str | None:
    """The name in a `name == <constant>` test, or None."""
    if not isinstance(test, ast.Compare):
        return None
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return None
    if not isinstance(test.left, ast.Name):
        return None
    if len(test.comparators) != 1 or not isinstance(test.comparators[0], ast.Constant):
        return None
    return test.left.id


def check_equality_chain(tree: ast.Module) -> Iterator[Finding]:
    """Rule 7 — three+ if/elif branches testing one name against constants want match/dispatch."""
    _elif_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            _elif_ids.add(id(node.orelse[0]))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if id(node) in _elif_ids:
            continue
        _name = _eq_const_name(node.test)
        if _name is None:
            continue
        _count = 1
        _cursor = node
        while len(_cursor.orelse) == 1 and isinstance(_cursor.orelse[0], ast.If):
            _next = _cursor.orelse[0]
            if _eq_const_name(_next.test) != _name:
                break
            _count += 1
            _cursor = _next
        if _count >= 3:
            yield Finding(node.lineno, "info", "7",
                          f"{_count}-branch if/elif all testing {_name!r} against constants — "
                          "consider match/case or a dict dispatch (rule 7)")


def check_str_augassign_in_loop(tree: ast.Module) -> Iterator[Finding]:
    """Rule 14 — building a string with += in a loop rebuilds it each time; collect and join."""
    _str_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, (str, bytes)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                _str_names.add(target.id)
    if len(_str_names) == 0:
        return
    _seen = set()
    for loop in ast.walk(tree):
        if not isinstance(loop, (ast.For, ast.While)):
            continue
        for node in ast.walk(loop):
            if not isinstance(node, ast.AugAssign):
                continue
            if not isinstance(node.op, ast.Add):
                continue
            if not isinstance(node.target, ast.Name):
                continue
            if node.target.id not in _str_names:
                continue
            if id(node) in _seen:
                continue
            _seen.add(id(node))
            yield Finding(node.lineno, "info", "14",
                          f"'{node.target.id} +=' in a loop on a string/bytes value — accumulate into a "
                          "list and join once (rule 14)")


def check_docstring_raises(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3v — a docstring names what the function raises; flag a raise it omits."""
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        _doc = ast.get_docstring(func) or ""
        for node in ast.walk(func):
            if not isinstance(node, ast.Raise):
                continue
            _exc = node.exc
            _name = None
            if isinstance(_exc, ast.Call) and isinstance(_exc.func, ast.Name):
                _name = _exc.func.id
            elif isinstance(_exc, ast.Name):
                _name = _exc.id
            if _name is None:
                continue
            if _name in _doc:
                continue
            yield Finding(node.lineno, "info", "3v",
                          f"raises {_name} but the docstring does not name it (rule 3v)")


def check_loop_var_leak(tree: ast.Module) -> Iterator[Finding]:
    """Rule 31 — a for-loop target read after the loop is a leaked block scope."""
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for loop in ast.walk(func):
            if not isinstance(loop, ast.For):
                continue
            _targets = set()
            for bound in ast.walk(loop.target):
                if isinstance(bound, ast.Name):
                    _targets.add(bound.id)
            if len(_targets) == 0:
                continue
            _inside = set()
            _rebound = set()
            for inner in ast.walk(loop):
                if isinstance(inner, ast.Name):
                    _inside.add(id(inner))
            for other in ast.walk(func):
                if not isinstance(other, ast.Name):
                    continue
                if id(other) in _inside:
                    continue
                if isinstance(other.ctx, ast.Store):
                    _rebound.add(other.id)
            _loads = (other for other in ast.walk(func)
                      if isinstance(other, ast.Name) and isinstance(other.ctx, ast.Load)
                      and id(other) not in _inside
                      and other.id in _targets and other.id not in _rebound)
            _leak = next(_loads, None)
            if _leak is not None:
                yield Finding(_leak.lineno, "info", "31",
                              f"loop variable {_leak.id!r} read after its for-loop — a leaked block scope (rule 31)")


def check_function_length(tree: ast.Module) -> Iterator[Finding]:
    """Rule 3e — a long function is doing too much; prefer small, simple ones."""
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        _statements = 0
        for node in ast.walk(func):
            if isinstance(node, ast.stmt):
                _statements += 1
        if _statements > 60:
            yield Finding(func.lineno, "info", "3e",
                          f"function {func.name!r} has {_statements} statements — split it into smaller "
                          "functions (rule 3e)")


_CHECKS = (
    check_regex,
    check_arithmetic_truthiness,
    check_return_ternary,
    check_list_augassign,
    check_unused_imports,
    check_comprehension_generators,
    check_bracket_comprehension,
    check_chained_calls,
    check_setdefault_return,
    check_strip_before_regex,
    check_unconditional_break,
    check_open_without_close,
    check_yaml_import,
    check_secret_compare,
    check_whole_file_read,
    check_json_sort_keys,
    check_equality_chain,
    check_str_augassign_in_loop,
    check_docstring_raises,
    check_loop_var_leak,
    check_function_length,
)


def _read_source(path: str) -> str:
    """Read a file whole; the try wraps one operation and hands the value out (rule 31).

    No handle is held, so there is no `__exit__` to trust and nothing to close
    explicitly (rule 3g) — `read_text` owns its own.

    @throws SystemExit the file cannot be read.
    """
    _path = pathlib.Path(path)
    try:
        return _path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def _parse_source(source: str, path: str) -> ast.Module:
    """Build the syntax tree; `path` is carried only for the error message.

    @throws SystemExit the file is not valid Python.
    """
    try:
        return ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise SystemExit(f"cannot parse {path}: {exc}")


def _run_checks(tree: ast.Module, annotated_lines: frozenset[int]) -> Iterator[Finding]:
    """Flatten every check's findings into one stream."""
    for check in _CHECKS:
        for finding in check(tree):
            yield finding
    for finding in check_materialize_annotation(tree, annotated_lines):
        yield finding
    for finding in check_silent_except(tree, annotated_lines):
        yield finding


def scan(path: str) -> list[Finding]:
    """Every finding in one file, ordered by line then rule.

    @throws SystemExit the file cannot be read, or is not valid Python.
    """
    logger.debug("reading python source: %s", path)
    source = _read_source(path)          # raises SystemExit if path is unreadable
    tree = _parse_source(source, path)   # raises SystemExit if path is not Python
    _annotated = _annotated_lines(source)

    _findings = _run_checks(tree, _annotated)
    return sorted(_findings, key=lambda f: (f.line, f.rule))


def main(argv: list[str]) -> int:
    _paths = list(arg for arg in argv[1:] if not arg.startswith("-"))
    _strict = "--strict" in argv[1:]
    if len(_paths) == 0:
        print(__doc__)
        return 2

    errors = 0
    reviews = 0
    infos = 0
    for path in _paths:
        findings = scan(path)
        if len(findings) == 0:
            continue
        errors += sum(1 for f in findings if f.kind == "error")
        reviews += sum(1 for f in findings if f.kind == "review")
        infos += sum(1 for f in findings if f.kind == "info")
        print(f"\n{path}")
        for finding in findings:
            print(f"  {finding.line:4}  [{finding.kind}]  rule {finding.rule}: {finding.message}")

    total = errors + reviews + infos
    print(f"\n{'-' * 66}")
    print(f"scanned {len(_paths)} files, {total} findings "
          f"({errors} error, {reviews} review, {infos} info)")

    _fatal = errors > 0 or (_strict and reviews > 0)
    if _fatal:
        return 1
    if total == 0:
        print("clean on rules 2, 3e, 3g, 3l, 3p, 3q, 3r, 3s, 3t, 3v, 7, 8, 11, 13, 14, 16, 20, 24, 26, 28, 30, 31 — every other rule needs a reader")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

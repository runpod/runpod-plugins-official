"""Table-driven unit tests for the pure helpers in ``rp_api_inventory``.

These cover the small, side-effect-free functions the scanner is built from —
signal matching, per-file context derivation, quote-aware comment detection,
suppression-marker parsing, markdown escaping and the hit-marker suffix. The
end-to-end CLI behaviour is exercised separately by
``hooks/check_migrate_scanner.py`` against the fixture corpora, so nothing here
tries to re-test the whole command.

Every case carries a ``description`` and an ``expected`` value (or an expected
exception type) and is iterated with ``subTest``.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rp_api_inventory import (
    V2_CONTEXT,
    CompiledSignal,
    Finding,
    Gen,
    _file_context,
    _hit_marker_suffix,
    _signal_match,
    comment_index,
    intentional_lines,
    iter_files,
    md_cell,
)

REPO_ROOT = Path("/repo")


def _compiled(
    regex: str,
    *,
    unless: str | None = None,
    defers_to_v2: bool = False,
    generation: Gen = Gen.V1,
    resource: str = "pod",
    note: str = "note",
) -> CompiledSignal:
    """Build a ``CompiledSignal`` for a single-regex match test."""

    return CompiledSignal(
        generation=generation,
        resource=resource,
        regex=re.compile(regex),
        note=note,
        unless=re.compile(unless) if unless is not None else None,
        defers_to_v2=defers_to_v2,
    )


def _finding(*, marker: str | None, prose: bool) -> Finding:
    """A fully-populated ``Finding`` differing only in ``marker``/``prose``."""

    return Finding(
        prose=prose,
        file="app.py",
        line=7,
        generation=Gen.V1,
        resource="pod",
        match="/pods",
        text="/pods",
        marker=marker,
        notes=["note"],
        matches=["/pods"],
    )


@dataclass(frozen=True)
class SignalMatchCase:
    description: str
    signal: CompiledSignal
    line: str
    file_v2_ctx: re.Pattern[str] | None
    expected: str | None  # matched substring, or None when the signal does not fire


SIGNAL_MATCH_CASES: list[SignalMatchCase] = [
    SignalMatchCase(
        description="positive: plain regex fires and returns the matched text",
        signal=_compiled(r"/pods\b"),
        line="requests.get(url + '/pods')",
        file_v2_ctx=None,
        expected="/pods",
    ),
    SignalMatchCase(
        description="negative: regex does not match the line",
        signal=_compiled(r"/pods\b"),
        line="requests.get(url + '/endpoints')",
        file_v2_ctx=None,
        expected=None,
    ),
    SignalMatchCase(
        description="negative: unless veto suppresses an otherwise-matching line",
        signal=_compiled(r"/pods\b", unless=V2_CONTEXT, defers_to_v2=True),
        line="requests.get('https://api.runpod.io/v2/pods')",
        file_v2_ctx=None,
        expected=None,
    ),
    SignalMatchCase(
        description="positive: unless present but does not match, so the hit stands",
        signal=_compiled(r"/pods\b", unless=V2_CONTEXT, defers_to_v2=True),
        line="requests.get(base + '/pods')",
        file_v2_ctx=None,
        expected="/pods",
    ),
    SignalMatchCase(
        description="negative: v2 deferral fires when the file's v2 base name is on the line",
        signal=_compiled(r"/pods\b", defers_to_v2=True),
        line="requests.get(BASE + '/pods')",
        file_v2_ctx=re.compile(r"\bBASE\b"),
        expected=None,
    ),
    SignalMatchCase(
        description="corner: defers_to_v2 but file has no derived v2 context (None)",
        signal=_compiled(r"/pods\b", defers_to_v2=True),
        line="requests.get(BASE + '/pods')",
        file_v2_ctx=None,
        expected="/pods",
    ),
    SignalMatchCase(
        description="corner: defers_to_v2 with a v2 context that does not match this line",
        signal=_compiled(r"/pods\b", defers_to_v2=True),
        line="requests.get(other + '/pods')",
        file_v2_ctx=re.compile(r"\bBASE\b"),
        expected="/pods",
    ),
    SignalMatchCase(
        description="corner: signal that does not defer ignores the v2 context entirely",
        signal=_compiled(r"/pods\b", defers_to_v2=False),
        line="requests.get(BASE + '/pods')",
        file_v2_ctx=re.compile(r"\bBASE\b"),
        expected="/pods",
    ),
]


@dataclass(frozen=True)
class FileContextCase:
    description: str
    rel: str
    text: str
    exp_rel: str
    exp_is_py: bool
    exp_is_doc: bool
    exp_marker: str | None
    exp_marked: dict[int, str]
    exp_v2_name: str | None  # a token file_v2_ctx must match, or None if no v2 context


FILE_CONTEXT_CASES: list[FileContextCase] = [
    FileContextCase(
        description="positive: plain python module, no markers, no v2 base",
        rel="app.py",
        text="x = 1\n",
        exp_rel="app.py",
        exp_is_py=True,
        exp_is_doc=False,
        exp_marker=None,
        exp_marked={},
        exp_v2_name=None,
    ),
    FileContextCase(
        description="positive: markdown doc is prose, not python",
        rel="docs/readme.md",
        text="hello\n",
        exp_rel="docs/readme.md",
        exp_is_py=False,
        exp_is_doc=True,
        exp_marker=None,
        exp_marked={},
        exp_v2_name=None,
    ),
    FileContextCase(
        description="corner: .pyi stub counts as python",
        rel="stub.pyi",
        text="x: int\n",
        exp_rel="stub.pyi",
        exp_is_py=True,
        exp_is_doc=False,
        exp_marker=None,
        exp_marked={},
        exp_v2_name=None,
    ),
    FileContextCase(
        description="positive: a v2 base-URL assignment yields a file v2 context",
        rel="client.py",
        text='BASE = "https://api.runpod.io/v2"\n',
        exp_rel="client.py",
        exp_is_py=True,
        exp_is_doc=False,
        exp_marker=None,
        exp_marked={},
        exp_v2_name="BASE",
    ),
    FileContextCase(
        description="corner: same name bound to both v1 and v2 drops the v2 context",
        rel="client.py",
        text='X = "https://api.runpod.io/v2"\nX = "https://rest.runpod.io/v1"\n',
        exp_rel="client.py",
        exp_is_py=True,
        exp_is_doc=False,
        exp_marker=None,
        exp_marked={},
        exp_v2_name=None,
    ),
    FileContextCase(
        description="positive: whole-file ignore marker is captured",
        rel="legacy.py",
        text="# rp-migrate: ignore file\nx = 1\n",
        exp_rel="legacy.py",
        exp_is_py=True,
        exp_is_doc=False,
        exp_marker="ignore",
        exp_marked={},
        exp_v2_name=None,
    ),
    FileContextCase(
        description="positive: a per-line keep-v1 marker is recorded by line number",
        rel="legacy.py",
        text="call_v1()  # rp-migrate: keep-v1\n",
        exp_rel="legacy.py",
        exp_is_py=True,
        exp_is_doc=False,
        exp_marker=None,
        exp_marked={1: "keep-v1"},
        exp_v2_name=None,
    ),
    FileContextCase(
        description="boundary: empty text in a .txt prose file",
        rel="notes.txt",
        text="",
        exp_rel="notes.txt",
        exp_is_py=False,
        exp_is_doc=True,
        exp_marker=None,
        exp_marked={},
        exp_v2_name=None,
    ),
]


@dataclass(frozen=True)
class CommentIndexCase:
    description: str
    line: str
    expected: int


COMMENT_INDEX_CASES: list[CommentIndexCase] = [
    CommentIndexCase(
        description="positive: hash comment on a whole line starts at 0",
        line="# full line comment",
        expected=0,
    ),
    CommentIndexCase(
        description="positive: trailing hash comment after code",
        line="x = 1  # c",
        expected=7,
    ),
    CommentIndexCase(
        description="positive: double-slash comment after code",
        line="a = b // c",
        expected=6,
    ),
    CommentIndexCase(
        description="positive: sql double-dash comment at line start",
        line="-- sql comment",
        expected=0,
    ),
    CommentIndexCase(
        description="negative: no comment on a plain code line",
        line="code = 5",
        expected=-1,
    ),
    CommentIndexCase(
        description="negative: // inside a URL string is not a comment",
        line='see = "https://example.com"',
        expected=-1,
    ),
    CommentIndexCase(
        description="negative: double-dash mid-line (not at start) is not a comment",
        line="x -- not at start",
        expected=-1,
    ),
    CommentIndexCase(
        description="corner: a hash inside a string literal is ignored",
        line='val = "a # b" # real',
        expected=14,
    ),
    CommentIndexCase(
        description="corner: hash inside a backtick string is ignored",
        line="q = `a#b`",
        expected=-1,
    ),
    CommentIndexCase(
        description="boundary: empty line has no comment",
        line="",
        expected=-1,
    ),
]


@dataclass(frozen=True)
class IntentionalLinesCase:
    description: str
    text: str
    expected: tuple[str | None, dict[int, str]]


INTENTIONAL_LINES_CASES: list[IntentionalLinesCase] = [
    IntentionalLinesCase(
        description="positive: whole-file ignore marker",
        text="# rp-migrate: ignore file\nx = 1\n",
        expected=("ignore", {}),
    ),
    IntentionalLinesCase(
        description="positive: whole-file keep-v1 marker",
        text="# rp-migrate: keep-v1 file\nx = 1\n",
        expected=("keep-v1", {}),
    ),
    IntentionalLinesCase(
        description="positive: single-line ignore marker",
        text="x = 1  # rp-migrate: ignore\ny = 2\n",
        expected=(None, {1: "ignore"}),
    ),
    IntentionalLinesCase(
        description="corner: keep-v1 wins over ignore on the same line",
        text="code  # rp-migrate: keep-v1 rp-migrate: ignore\n",
        expected=(None, {1: "keep-v1"}),
    ),
    IntentionalLinesCase(
        description="corner: start/end region marks every line inclusive",
        text=("# rp-migrate: ignore start\na = 1\nb = 2\n# rp-migrate: ignore end\nc = 3\n"),
        expected=(None, {1: "ignore", 2: "ignore", 3: "ignore", 4: "ignore"}),
    ),
    IntentionalLinesCase(
        description="negative: code without any marker",
        text="just = code\n",
        expected=(None, {}),
    ),
    IntentionalLinesCase(
        description="boundary: empty text",
        text="",
        expected=(None, {}),
    ),
]


@dataclass(frozen=True)
class MdCellCase:
    description: str
    value: str
    expected: str


MD_CELL_CASES: list[MdCellCase] = [
    MdCellCase(
        description="positive: pipe is escaped for a table cell",
        value="a|b",
        expected="a\\|b",
    ),
    MdCellCase(
        description="positive: newline becomes a space",
        value="line1\nline2",
        expected="line1 line2",
    ),
    MdCellCase(
        description="corner: both pipe and newline are handled",
        value="a|b\nc",
        expected="a\\|b c",
    ),
    MdCellCase(
        description="negative: plain text is unchanged",
        value="plain",
        expected="plain",
    ),
    MdCellCase(
        description="boundary: empty string stays empty",
        value="",
        expected="",
    ),
]


@dataclass(frozen=True)
class HitMarkerCase:
    description: str
    finding: Finding = field(compare=False)
    expected: str


HIT_MARKER_CASES: list[HitMarkerCase] = [
    HitMarkerCase(
        description="positive: keep-v1 marker renders the kept-on-purpose suffix",
        finding=_finding(marker="keep-v1", prose=False),
        expected=" _(kept on purpose)_",
    ),
    HitMarkerCase(
        description="positive: ignore marker renders the false-positive suffix",
        finding=_finding(marker="ignore", prose=False),
        expected=" _(false positive)_",
    ),
    HitMarkerCase(
        description="corner: no marker but prose renders the comment/doc suffix",
        finding=_finding(marker=None, prose=True),
        expected=" _(comment/doc)_",
    ),
    HitMarkerCase(
        description="negative: no marker and not prose renders no suffix",
        finding=_finding(marker=None, prose=False),
        expected="",
    ),
]


@dataclass(frozen=True)
class IterFilesCase:
    description: str
    files: tuple[str, ...]
    expected: tuple[str, ...]


ITER_FILES_CASES: list[IterFilesCase] = [
    IterFilesCase(
        description="positive: nested files are yielded in sorted walk order",
        files=("src/b.py", "src/a.py", "README.md", "src/pkg/c.ts"),
        expected=("README.md", "src/a.py", "src/b.py", "src/pkg/c.ts"),
    ),
    IterFilesCase(
        description="negative: skipped directories are not descended into",
        files=("app.py", "node_modules/dep.js", ".git/config", ".github/workflows/ci.yml"),
        expected=("app.py",),
    ),
    IterFilesCase(
        description="negative: skipped suffixes are not yielded",
        files=("app.py", "yarn.lock", "bundle.min.js", "logo.png"),
        expected=("app.py",),
    ),
    IterFilesCase(
        description="boundary: an empty tree yields nothing",
        files=(),
        expected=(),
    ),
]


class SignalMatchTests(unittest.TestCase):
    def test_signal_match(self) -> None:
        for case in SIGNAL_MATCH_CASES:
            with self.subTest(case.description):
                match = _signal_match(case.signal, case.line, case.file_v2_ctx)
                actual = match.group(0) if match is not None else None
                self.assertEqual(actual, case.expected)


class FileContextTests(unittest.TestCase):
    def test_file_context(self) -> None:
        for case in FILE_CONTEXT_CASES:
            with self.subTest(case.description):
                ctx = _file_context(REPO_ROOT / case.rel, REPO_ROOT, case.text)
                self.assertEqual(ctx.rel, case.exp_rel)
                self.assertEqual(ctx.is_py, case.exp_is_py)
                self.assertEqual(ctx.is_doc, case.exp_is_doc)
                self.assertEqual(ctx.whole_file_marker, case.exp_marker)
                self.assertEqual(ctx.marked, case.exp_marked)
                if case.exp_v2_name is None:
                    self.assertIsNone(ctx.file_v2_ctx)
                else:
                    self.assertIsNotNone(ctx.file_v2_ctx)
                    assert ctx.file_v2_ctx is not None
                    self.assertIsNotNone(ctx.file_v2_ctx.search(case.exp_v2_name))


class CommentIndexTests(unittest.TestCase):
    def test_comment_index(self) -> None:
        for case in COMMENT_INDEX_CASES:
            with self.subTest(case.description):
                self.assertEqual(comment_index(case.line), case.expected)


class IntentionalLinesTests(unittest.TestCase):
    def test_intentional_lines(self) -> None:
        for case in INTENTIONAL_LINES_CASES:
            with self.subTest(case.description):
                self.assertEqual(intentional_lines(case.text), case.expected)


class MdCellTests(unittest.TestCase):
    def test_md_cell(self) -> None:
        for case in MD_CELL_CASES:
            with self.subTest(case.description):
                self.assertEqual(md_cell(case.value), case.expected)


class HitMarkerSuffixTests(unittest.TestCase):
    def test_hit_marker_suffix(self) -> None:
        for case in HIT_MARKER_CASES:
            with self.subTest(case.description):
                self.assertEqual(_hit_marker_suffix(case.finding), case.expected)


class IterFilesTests(unittest.TestCase):
    """Walks a real temporary tree, so it also proves the directory walk runs on
    the oldest Python the skill scripts support (see validate.yml)."""

    def test_iter_files(self) -> None:
        for case in ITER_FILES_CASES:
            with self.subTest(case.description), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for rel in case.files:
                    path = root / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("x\n", encoding="utf-8")
                actual = tuple(p.relative_to(root).as_posix() for p in iter_files(root))
                self.assertEqual(actual, case.expected)


if __name__ == "__main__":
    unittest.main()

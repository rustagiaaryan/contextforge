"""Python AST parser for symbols and best-effort relationships."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from contextforge.models import EdgeType, NodeType, ParsedFile, RelationHint, SourceUnit


def _module_name(relative: str) -> str:
    path = relative.removesuffix(".py").replace("/", ".")
    if path.endswith(".__init__"):
        path = path[: -len(".__init__")]
    return path or "__init__"


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({ast.unparse(node.args)})"


def _is_test(path: str, name: str) -> bool:
    parts = Path(path).parts
    return (
        any(part in {"test", "tests"} for part in parts)
        or Path(path).name.startswith("test_")
        or name.startswith("test_")
    )


@dataclass
class _Extractor(ast.NodeVisitor):
    relative_path: str
    source: str
    module_name: str
    module_id: str
    units: list[SourceUnit] = field(default_factory=list)
    relations: list[RelationHint] = field(default_factory=list)
    scope: list[tuple[str, str, NodeType]] = field(default_factory=list)
    relation_keys: set[tuple[str, EdgeType, str]] = field(default_factory=set)
    unit_id_counts: dict[str, int] = field(default_factory=dict)
    source_bytes: bytes = field(init=False, repr=False)
    line_byte_offsets: tuple[int, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.source_bytes = self.source.encode("utf-8")
        offsets = [0]
        for line in self.source_bytes.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        self.line_byte_offsets = tuple(offsets)

    def _source_segment(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Slice a symbol in O(symbol size) using AST UTF-8 byte offsets."""
        if node.end_lineno is None or node.end_col_offset is None:
            return ""
        start = self.line_byte_offsets[node.lineno - 1] + node.col_offset
        end = self.line_byte_offsets[node.end_lineno - 1] + node.end_col_offset
        return self.source_bytes[start:end].decode("utf-8", errors="replace")

    def _parent(self) -> tuple[str, str, NodeType]:
        return self.scope[-1] if self.scope else (self.module_id, self.module_name, NodeType.MODULE)

    def _add_relation(
        self,
        source_id: str,
        edge_type: EdgeType,
        target: str,
        line: int | None,
        confidence: float,
    ) -> None:
        key = (source_id, edge_type, target)
        if target and key not in self.relation_keys:
            self.relation_keys.add(key)
            self.relations.append(
                RelationHint(
                    source_id=source_id,
                    edge_type=edge_type,
                    target=target,
                    line=line,
                    confidence=confidence,
                )
            )

    def _visit_symbol(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent_id, parent_qualname, parent_type = self._parent()
        qualname = f"{parent_qualname}.{node.name}"
        if isinstance(node, ast.ClassDef):
            node_type = NodeType.CLASS
        elif parent_type is NodeType.CLASS:
            node_type = (
                NodeType.TEST if _is_test(self.relative_path, node.name) else NodeType.METHOD
            )
        else:
            node_type = (
                NodeType.TEST if _is_test(self.relative_path, node.name) else NodeType.FUNCTION
            )
        base_unit_id = SourceUnit.make_id(node_type, self.relative_path, qualname)
        occurrence = self.unit_id_counts.get(base_unit_id, 0) + 1
        self.unit_id_counts[base_unit_id] = occurrence
        unit_id = base_unit_id if occurrence == 1 else f"{base_unit_id}#{occurrence}"
        content = self._source_segment(node)
        unit = SourceUnit(
            unit_id=unit_id,
            node_type=node_type,
            path=self.relative_path,
            name=node.name,
            qualname=qualname,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=_signature(node),
            docstring=ast.get_docstring(node, clean=True) or "",
            content=content,
            content_hash=SourceUnit.hash_content(content),
            parent_id=parent_id,
            is_test=_is_test(self.relative_path, node.name),
        )
        self.units.append(unit)
        self._add_relation(parent_id, EdgeType.DEFINES, unit_id, node.lineno, 1.0)
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                self._add_relation(unit_id, EdgeType.INHERITS, ast.unparse(base), node.lineno, 0.8)
        self.scope.append((unit_id, qualname, node_type))
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_symbol(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_symbol(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_symbol(node)

    def visit_Import(self, node: ast.Import) -> None:
        source_id = self._parent()[0]
        for alias in node.names:
            self._add_relation(source_id, EdgeType.IMPORTS, alias.name, node.lineno, 0.95)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        source_id = self._parent()[0]
        module = "." * node.level + (node.module or "")
        self._add_relation(source_id, EdgeType.IMPORTS, module, node.lineno, 0.95)
        for alias in node.names:
            target = f"{module}.{alias.name}" if module else alias.name
            self._add_relation(source_id, EdgeType.REFERENCES, target, node.lineno, 0.75)

    def visit_Call(self, node: ast.Call) -> None:
        if self.scope:
            self._add_relation(
                self.scope[-1][0], EdgeType.CALLS, _call_name(node.func), node.lineno, 0.65
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if self.scope and isinstance(node.ctx, ast.Load):
            self._add_relation(self.scope[-1][0], EdgeType.REFERENCES, node.id, node.lineno, 0.35)


class PythonParser:
    """Extract Python symbols using the standard library AST."""

    extensions = frozenset({".py", ".pyi"})

    def parse(self, repository: Path, path: Path) -> ParsedFile:
        """Parse a Python file and return source units plus unresolved edges."""
        relative = path.resolve().relative_to(repository.resolve()).as_posix()
        source = path.read_text(encoding="utf-8", errors="replace")
        content_hash = SourceUnit.hash_content(source)
        tree = ast.parse(source, filename=relative, type_comments=True)
        end_line = max(1, len(source.splitlines()))
        module_name = _module_name(relative)
        file_id = SourceUnit.make_id(NodeType.FILE, relative, relative)
        module_id = SourceUnit.make_id(NodeType.MODULE, relative, module_name)
        file_unit = SourceUnit(
            unit_id=file_id,
            node_type=NodeType.FILE,
            path=relative,
            name=Path(relative).name,
            qualname=relative,
            start_line=1,
            end_line=end_line,
            content=source,
            content_hash=content_hash,
            is_test=_is_test(relative, Path(relative).stem),
        )
        module_docstring = ast.get_docstring(tree, clean=True) or ""
        module_unit = SourceUnit(
            unit_id=module_id,
            node_type=NodeType.MODULE,
            path=relative,
            name=module_name.rsplit(".", 1)[-1],
            qualname=module_name,
            start_line=1,
            end_line=end_line,
            docstring=module_docstring,
            content=module_docstring,
            content_hash=SourceUnit.hash_content(module_docstring),
            parent_id=file_id,
            is_test=_is_test(relative, module_name),
        )
        extractor = _Extractor(relative, source, module_name, module_id)
        extractor.visit(tree)
        relations = [
            RelationHint(
                source_id=file_id,
                edge_type=EdgeType.CONTAINS,
                target=module_id,
                confidence=1.0,
            ),
            *extractor.relations,
        ]
        return ParsedFile(
            path=relative,
            content_hash=content_hash,
            units=(file_unit, module_unit, *extractor.units),
            relations=tuple(relations),
        )

"""Tree-sitter source extraction for the graph-artifact pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType

from tree_sitter import Language, Node, Parser

from contextforge.codegraph.models import (
    ArtifactEdge,
    ArtifactNode,
    ConfidenceLabel,
    Extraction,
)


@dataclass(frozen=True)
class LanguageSpec:
    """Describe a Tree-sitter grammar and its source extensions."""

    name: str
    module: str
    loader: str = "language"


LANGUAGES: dict[str, LanguageSpec] = {
    ".bash": LanguageSpec("bash", "tree_sitter_bash"),
    ".c": LanguageSpec("c", "tree_sitter_c"),
    ".cc": LanguageSpec("cpp", "tree_sitter_cpp"),
    ".cjs": LanguageSpec("javascript", "tree_sitter_javascript"),
    ".cpp": LanguageSpec("cpp", "tree_sitter_cpp"),
    ".cs": LanguageSpec("csharp", "tree_sitter_c_sharp"),
    ".cxx": LanguageSpec("cpp", "tree_sitter_cpp"),
    ".ex": LanguageSpec("elixir", "tree_sitter_elixir"),
    ".exs": LanguageSpec("elixir", "tree_sitter_elixir"),
    ".f": LanguageSpec("fortran", "tree_sitter_fortran"),
    ".f03": LanguageSpec("fortran", "tree_sitter_fortran"),
    ".f08": LanguageSpec("fortran", "tree_sitter_fortran"),
    ".f90": LanguageSpec("fortran", "tree_sitter_fortran"),
    ".f95": LanguageSpec("fortran", "tree_sitter_fortran"),
    ".go": LanguageSpec("go", "tree_sitter_go"),
    ".groovy": LanguageSpec("groovy", "tree_sitter_groovy"),
    ".h": LanguageSpec("c", "tree_sitter_c"),
    ".hpp": LanguageSpec("cpp", "tree_sitter_cpp"),
    ".java": LanguageSpec("java", "tree_sitter_java"),
    ".jl": LanguageSpec("julia", "tree_sitter_julia"),
    ".js": LanguageSpec("javascript", "tree_sitter_javascript"),
    ".json": LanguageSpec("json", "tree_sitter_json"),
    ".jsx": LanguageSpec("javascript", "tree_sitter_javascript"),
    ".kt": LanguageSpec("kotlin", "tree_sitter_kotlin"),
    ".kts": LanguageSpec("kotlin", "tree_sitter_kotlin"),
    ".lua": LanguageSpec("lua", "tree_sitter_lua"),
    ".m": LanguageSpec("objective-c", "tree_sitter_objc"),
    ".mjs": LanguageSpec("javascript", "tree_sitter_javascript"),
    ".mm": LanguageSpec("objective-c", "tree_sitter_objc"),
    ".php": LanguageSpec("php", "tree_sitter_php", "language_php"),
    ".ps1": LanguageSpec("powershell", "tree_sitter_powershell"),
    ".psm1": LanguageSpec("powershell", "tree_sitter_powershell"),
    ".py": LanguageSpec("python", "tree_sitter_python"),
    ".pyi": LanguageSpec("python", "tree_sitter_python"),
    ".rb": LanguageSpec("ruby", "tree_sitter_ruby"),
    ".rs": LanguageSpec("rust", "tree_sitter_rust"),
    ".scala": LanguageSpec("scala", "tree_sitter_scala"),
    ".sh": LanguageSpec("bash", "tree_sitter_bash"),
    ".swift": LanguageSpec("swift", "tree_sitter_swift"),
    ".ts": LanguageSpec("typescript", "tree_sitter_typescript", "language_typescript"),
    ".tsx": LanguageSpec("tsx", "tree_sitter_typescript", "language_tsx"),
    ".v": LanguageSpec("verilog", "tree_sitter_verilog"),
    ".verilog": LanguageSpec("verilog", "tree_sitter_verilog"),
    ".zig": LanguageSpec("zig", "tree_sitter_zig"),
}

DEFINITION_KINDS: dict[str, str] = {
    "class_declaration": "class",
    "class_definition": "class",
    "class_specifier": "class",
    "class_definition2": "class",
    "data_class_definition": "class",
    "enum_declaration": "enum",
    "enum_item": "enum",
    "enum_specifier": "enum",
    "function_declaration": "function",
    "function_definition": "function",
    "function_item": "function",
    "function_statement": "function",
    "interface_declaration": "interface",
    "method_declaration": "method",
    "method_definition": "method",
    "method_declaration2": "method",
    "method": "method",
    "struct_item": "class",
    "struct_specifier": "class",
    "trait_item": "interface",
    "impl_item": "class",
    "module_declaration": "module",
    "namespace_definition": "module",
}

CALL_NODE_TYPES = frozenset(
    {
        "call",
        "call_expression",
        "command",
        "function_call",
        "invocation_expression",
        "method_invocation",
    }
)
IMPORT_NODE_TYPES = frozenset(
    {
        "import_declaration",
        "import_from_statement",
        "import_statement",
        "include_directive",
        "preproc_include",
        "require_statement",
        "use_declaration",
        "using_declaration",
    }
)
INHERITANCE_FIELDS = ("superclasses", "superclass", "base", "bases", "interfaces")
_IDENTIFIER_TYPES = frozenset(
    {
        "constant",
        "identifier",
        "namespace_identifier",
        "scoped_identifier",
        "simple_identifier",
        "type_identifier",
    }
)
_REFERENCE_CLEANUP = re.compile(r"[^A-Za-z0-9_.$:/@#-]+")


def extract_file(repository: Path, path: Path) -> Extraction:
    """Parse one supported source file without importing or executing it."""
    root = repository.resolve(strict=True)
    resolved = path.resolve(strict=True)
    relative = resolved.relative_to(root).as_posix()
    spec = LANGUAGES.get(resolved.suffix.lower())
    if spec is None:
        raise ValueError(f"Unsupported graph language: {resolved.suffix}")
    source = resolved.read_bytes()
    parser = Parser(_load_language(spec))
    tree = parser.parse(source)
    file_id = f"file:{relative}"
    file_node: ArtifactNode = {
        "id": file_id,
        "label": Path(relative).name,
        "kind": "file",
        "source_file": relative,
        "source_location": "L1",
        "language": spec.name,
        "qualname": relative,
        "start_line": 1,
        "end_line": max(1, source.count(b"\n") + 1),
    }
    nodes: list[ArtifactNode] = [file_node]
    edges: list[ArtifactEdge] = []
    seen_nodes = {file_id}
    seen_edges: set[tuple[str, str, str]] = set()

    def visit(node: Node, parents: tuple[tuple[str, str], ...]) -> None:
        active = parents[-1][0] if parents else file_id
        next_parents = parents
        kind = DEFINITION_KINDS.get(node.type)
        if kind:
            name = _definition_name(node, source)
            if name:
                qualname = ".".join([*(item[1] for item in parents), name])
                node_id = f"{kind}:{relative}:{qualname}"
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    artifact_node: ArtifactNode = {
                        "id": node_id,
                        "label": name,
                        "kind": kind,
                        "source_file": relative,
                        "source_location": f"L{node.start_point.row + 1}",
                        "language": spec.name,
                        "qualname": qualname,
                        "signature": _signature(node, source),
                        "start_line": node.start_point.row + 1,
                        "end_line": node.end_point.row + 1,
                    }
                    nodes.append(artifact_node)
                    _append_edge(
                        edges,
                        seen_edges,
                        source_id=active,
                        target=node_id,
                        relation="defines",
                        confidence=ConfidenceLabel.EXTRACTED,
                        line=node.start_point.row + 1,
                    )
                    for inherited in _inheritance_references(node, source):
                        _append_edge(
                            edges,
                            seen_edges,
                            source_id=node_id,
                            target="",
                            target_ref=inherited,
                            relation="inherits",
                            confidence=ConfidenceLabel.INFERRED,
                            line=node.start_point.row + 1,
                        )
                active = node_id
                next_parents = (*parents, (node_id, name))

        if node.type in IMPORT_NODE_TYPES:
            target_ref = _import_reference(node, source)
            if target_ref:
                _append_edge(
                    edges,
                    seen_edges,
                    source_id=file_id,
                    target="",
                    target_ref=target_ref,
                    relation="imports",
                    confidence=ConfidenceLabel.EXTRACTED,
                    line=node.start_point.row + 1,
                )
        elif node.type in CALL_NODE_TYPES:
            target_ref = _call_reference(node, source)
            if target_ref:
                _append_edge(
                    edges,
                    seen_edges,
                    source_id=active,
                    target="",
                    target_ref=target_ref,
                    relation="calls",
                    confidence=ConfidenceLabel.INFERRED,
                    line=node.start_point.row + 1,
                )

        for child in node.named_children:
            visit(child, next_parents)

    visit(tree.root_node, ())
    parse_errors = (
        ["Tree-sitter recovered from one or more syntax errors"] if tree.root_node.has_error else []
    )
    extraction: Extraction = {
        "path": relative,
        "language": spec.name,
        "nodes": nodes,
        "edges": edges,
        "parse_errors": parse_errors,
    }
    return extraction


def _load_language(spec: LanguageSpec) -> Language:
    module: ModuleType = import_module(spec.module)
    loader = getattr(module, spec.loader, None)
    if not callable(loader):
        raise RuntimeError(f"{spec.module} does not expose {spec.loader}()")
    return Language(loader())


def _definition_name(node: Node, source: bytes) -> str:
    for field in ("name", "declarator", "type"):
        child = node.child_by_field_name(field)
        if child is None:
            continue
        direct = _first_identifier(child, source)
        if direct:
            return direct
    return _first_identifier(node, source)


def _first_identifier(node: Node, source: bytes) -> str:
    if node.type in _IDENTIFIER_TYPES:
        return _node_text(node, source).strip()
    for child in node.named_children:
        value = _first_identifier(child, source)
        if value:
            return value
    return ""


def _signature(node: Node, source: bytes) -> str:
    line_end = source.find(b"\n", node.start_byte, min(len(source), node.end_byte))
    end = node.end_byte if line_end < 0 else line_end
    return source[node.start_byte : end].decode("utf-8", errors="replace").strip()[:500]


def _inheritance_references(node: Node, source: bytes) -> tuple[str, ...]:
    values: list[str] = []
    for field in INHERITANCE_FIELDS:
        child = node.child_by_field_name(field)
        if child is None:
            continue
        for descendant in _walk(child):
            if descendant.type in _IDENTIFIER_TYPES:
                cleaned = _clean_reference(_node_text(descendant, source))
                if cleaned and cleaned not in values:
                    values.append(cleaned)
    return tuple(values[:20])


def _import_reference(node: Node, source: bytes) -> str:
    for field in ("source", "module_name", "path", "name"):
        child = node.child_by_field_name(field)
        if child is not None:
            value = _clean_reference(_node_text(child, source))
            if value:
                return value
    text = _node_text(node, source).strip()
    text = re.sub(r"^(from|import|include|require|use|using)\s+", "", text)
    text = text.split(" import ", 1)[0]
    return _clean_reference(text.splitlines()[0] if text else "")


def _call_reference(node: Node, source: bytes) -> str:
    for field in ("function", "name", "method"):
        child = node.child_by_field_name(field)
        if child is not None:
            return _clean_reference(_node_text(child, source))
    first = node.named_children[0] if node.named_children else None
    return _clean_reference(_node_text(first, source)) if first is not None else ""


def _clean_reference(value: str) -> str:
    cleaned = value.strip().strip("'\"`<>()[]{}")
    cleaned = _REFERENCE_CLEANUP.sub(" ", cleaned).strip()
    if not cleaned or len(cleaned) > 180 or " " in cleaned:
        return ""
    return cleaned


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node) -> tuple[Node, ...]:
    result: list[Node] = [node]
    for child in node.named_children:
        result.extend(_walk(child))
    return tuple(result)


def _append_edge(
    edges: list[ArtifactEdge],
    seen: set[tuple[str, str, str]],
    *,
    source_id: str,
    target: str,
    relation: str,
    confidence: ConfidenceLabel,
    line: int,
    target_ref: str | None = None,
) -> None:
    identity = (source_id, target or target_ref or "", relation)
    if identity in seen:
        return
    seen.add(identity)
    edge: ArtifactEdge = {
        "source": source_id,
        "target": target,
        "relation": relation,
        "confidence": confidence.value,
        "source_location": f"L{line}",
    }
    if target_ref:
        edge["target_ref"] = target_ref
    edges.append(edge)

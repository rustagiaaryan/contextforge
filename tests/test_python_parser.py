from pathlib import Path

from contextforge.models import EdgeType, NodeType
from contextforge.parsers import PythonParser

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_parser_extracts_symbols_and_relationships() -> None:
    result = PythonParser().parse(FIXTURE, FIXTURE / "app" / "routing.py")

    by_qualname = {unit.qualname: unit for unit in result.units}
    assert by_qualname["app.routing.Mount"].node_type is NodeType.CLASS
    assert by_qualname["app.routing.Mount.resolve"].node_type is NodeType.METHOD
    assert by_qualname["app.routing.Mount.resolve"].signature == "def resolve(self, path: str)"
    assert by_qualname["app.routing.Mount.resolve"].docstring == "Build the delegated path."
    assert any(
        relation.edge_type is EdgeType.CALLS and relation.target == "join_path"
        for relation in result.relations
    )
    assert any(
        relation.edge_type is EdgeType.IMPORTS and relation.target == "app.utils"
        for relation in result.relations
    )


def test_test_function_is_typed_as_test() -> None:
    result = PythonParser().parse(FIXTURE, FIXTURE / "tests" / "test_routing.py")
    test_unit = next(
        unit for unit in result.units if unit.name == "test_mounted_prefix_is_preserved"
    )
    assert test_unit.node_type is NodeType.TEST
    assert test_unit.is_test


def test_parser_assigns_unique_ids_to_overloads(tmp_path: Path) -> None:
    source = tmp_path / "overloads.py"
    source.write_text(
        "from typing import overload\n\n"
        "@overload\n"
        "def convert(value: str) -> str: ...\n\n"
        "@overload\n"
        "def convert(value: int) -> int: ...\n\n"
        "def convert(value: str | int) -> str | int:\n"
        "    return value\n",
        encoding="utf-8",
    )

    result = PythonParser().parse(tmp_path, source)
    overloads = [unit for unit in result.units if unit.qualname == "overloads.convert"]

    assert len(overloads) == 3
    assert len({unit.unit_id for unit in overloads}) == 3
    assert overloads[0].unit_id.endswith(":overloads.convert")
    assert overloads[2].unit_id.endswith(":overloads.convert#3")


def test_parser_slices_unicode_source_with_ast_byte_offsets(tmp_path: Path) -> None:
    source = tmp_path / "unicode.py"
    source.write_text(
        'def greeting():\n    message = "こんにちは"\n    return message\n',
        encoding="utf-8",
    )

    result = PythonParser().parse(tmp_path, source)
    function = next(unit for unit in result.units if unit.name == "greeting")

    assert function.content.endswith("return message")
    assert 'message = "こんにちは"' in function.content

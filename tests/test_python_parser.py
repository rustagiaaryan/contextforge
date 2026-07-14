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

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


SYMBOL_KINDS: dict[int, str] = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Constructor",
    10: "Enum",
    11: "Interface",
    12: "Function",
    13: "Variable",
    14: "Constant",
    15: "String",
    16: "Number",
    17: "Boolean",
    18: "Array",
    19: "Object",
    20: "Key",
    21: "Null",
    22: "EnumMember",
    23: "Struct",
    24: "Event",
    25: "Operator",
    26: "TypeParameter",
}

CLASSLIKE_KINDS = {5, 10, 11, 23}
FUNCTIONLIKE_KINDS = {6, 9, 12, 20, 25}


@dataclass(frozen=True)
class Position:
    line: int
    character: int

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Position":
        return cls(line=int(value["line"]), character=int(value["character"]))

    def to_lsp(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Range":
        return cls(
            start=Position.from_lsp(value["start"]),
            end=Position.from_lsp(value["end"]),
        )

    def to_lsp(self) -> dict[str, dict[str, int]]:
        return {"start": self.start.to_lsp(), "end": self.end.to_lsp()}


@dataclass(frozen=True)
class Location:
    path: Path
    range: Range

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Location":
        from .uri import uri_to_path

        if "targetUri" in value:
            uri = value["targetUri"]
            range_value = value.get("targetSelectionRange") or value["targetRange"]
        else:
            uri = value["uri"]
            range_value = value["range"]
        return cls(path=uri_to_path(uri), range=Range.from_lsp(range_value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "range": self.range.to_lsp(),
            "line": self.range.start.line + 1,
            "character": self.range.start.character + 1,
        }


@dataclass(frozen=True)
class SymbolCandidate:
    name: str
    container_name: str
    kind: int
    location: Location
    score: tuple[int, int, int]

    @property
    def full_name(self) -> str:
        if self.container_name:
            return f"{self.container_name}::{self.name}"
        return self.name

    def kind_name(self) -> str:
        return SYMBOL_KINDS.get(self.kind, f"Kind{self.kind}")


@dataclass(frozen=True)
class QueryResult:
    name: str
    full_name: str
    kind: int
    location: Location
    source: str
    source_range: Range | None
    resolution: str
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "kind": self.kind,
            "kind_name": SYMBOL_KINDS.get(self.kind, f"Kind{self.kind}"),
            "location": self.location.to_dict(),
            "source": self.source,
            "source_range": self.source_range.to_lsp() if self.source_range else None,
            "resolution": self.resolution,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }

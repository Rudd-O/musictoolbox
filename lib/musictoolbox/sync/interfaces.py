import typing

from ..files import AbsolutePath


class PathMappingProtocol(typing.Protocol):
    def map(self, __arg: AbsolutePath) -> AbsolutePath:
        pass


class PathComparisonProtocol(typing.Protocol):
    def compare(self, __arg1: AbsolutePath, __arg2: AbsolutePath) -> int:
        pass

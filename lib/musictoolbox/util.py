import typing

AnyIn = typing.TypeVar("AnyIn")
AnyOut = typing.TypeVar("AnyOut")


def transform_keys(
    f: typing.Callable[[AnyIn], AnyIn], d: typing.Dict[AnyIn, AnyOut]
) -> typing.Dict[AnyIn, AnyOut]:
    for k, v in list(d.items()):
        newk = f(k)
        if newk != k:
            del d[k]
            d[newk] = v
    return d


__all__ = ["transform_keys"]

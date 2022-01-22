import logging
import typing


class CLIFormatter(logging.Formatter):
    def __init__(
        self,
        main_module_name: str,
        fmt: typing.Optional[str] = "%(levelname)s: (%(name)s) \t%(message)s",
    ) -> None:
        self.main_module_name = main_module_name
        self.normal_formatter = logging.Formatter(fmt)
        self.main_formatter = logging.Formatter("%(message)s")

    def format(self, record: logging.LogRecord) -> str:
        f = (
            self.main_formatter
            if (record.name == self.main_module_name and record.levelno == logging.INFO)
            else self.normal_formatter
        )
        return f.format(record)


def basicConfig(main_module_name: str, level: int) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(CLIFormatter(main_module_name))
    logging.basicConfig(handlers=[handler], level=level)

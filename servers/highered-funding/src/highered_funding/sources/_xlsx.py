"""Shared safe-download helpers for the .xlsx sources: size caps, zip-bomb check, in-memory read-only parse."""
import io
import warnings
import zipfile

import openpyxl

from ..http import UpstreamError

MAX_FILE_BYTES = 25_000_000
MAX_UNZIPPED = 250_000_000


class ParseError(UpstreamError):
    pass


def open_workbook(data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 500 or sum(i.file_size for i in infos) > MAX_UNZIPPED:
                raise ParseError("Spreadsheet is larger than the safety limit.")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)  # openpyxl notes print-area names it does not use
            return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise ParseError("Download is not a valid .xlsx workbook.") from None

import abc

import typing

from genophenocorr.model import Patient

from ._audit import Auditor


T = typing.TypeVar('T')


class PatientCreator(typing.Generic[T], Auditor[T, Patient], metaclass=abc.ABCMeta):
    """
    `PatientCreator` can create a `Patient` from some input `T`.

    `PatientCreator` is an `Auditor`, hence the input is sanitized and any errors are reported to the caller.
    """
    pass

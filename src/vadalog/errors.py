"""Error hierarchy for the Vadalog-Portable engine (SPECIFICATION.md sec. 12.5)."""


class VadalogError(Exception):
    """Base class for every engine error."""

    exit_code = 1

    def __init__(self, message, line=None, col=None, source=None):
        self.message = message
        self.line = line
        self.col = col
        self.source = source
        super().__init__(str(self))

    def __str__(self):
        where = ""
        if self.source is not None:
            where = str(self.source)
        if self.line is not None:
            where = "%s:%d" % (where, self.line) if where else "line %d" % self.line
            if self.col is not None:
                where += ":%d" % self.col
        return "%s: %s" % (where, self.message) if where else self.message


class LexError(VadalogError):
    """Malformed token."""


class ParseError(VadalogError):
    """Malformed program."""


class ParameterError(ParseError):
    """A placeholder `${name}` with no value, or an unusable value (sec. 11.8).

    `names` lists the parameters concerned, so that a caller (the web UI)
    can ask for them.
    """

    def __init__(self, message, line=None, col=None, source=None, names=None):
        self.names = list(names or [])
        super().__init__(message, line=line, col=col, source=source)


class StaticError(VadalogError):
    """Failure of a static check: arity, safety, stratification, EGD harmlessness."""


class RuntimeFailure(VadalogError):
    """Reasoning aborted: #F fired, EGD unification failed, arithmetic failure."""

    exit_code = 2


class ReasoningFailure(RuntimeFailure):
    """A failure rule `#F :- body` was activated."""


class UnificationFailure(RuntimeFailure):
    """An EGD tried to equate two distinct constants."""


class ArithmeticFailure(RuntimeFailure):
    """Division by zero, or a NaN result."""


class TypeFailure(RuntimeFailure):
    """An operator was applied to incompatible data types."""


class ResourceExceeded(VadalogError):
    """A guard from SPECIFICATION.md sec. 7.7 tripped."""

    exit_code = 3


class DataSourceError(VadalogError):
    """CSV or file-system problem."""

    exit_code = 4

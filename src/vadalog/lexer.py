"""Hand-written tokeniser for Vadalog (SPECIFICATION.md sec. 1).

No third-party dependency: the grammar of the language is implemented here
as a small scanner.
"""

from . import params as _params
from .errors import LexError
from .values import escape_string, format_date

# Token kinds
ID, VAR, ANON, STRING, INTEGER, DOUBLE, DATE, TRUE, FALSE = (
    "ID", "VAR", "ANON", "STRING", "INTEGER", "DOUBLE", "DATE", "TRUE", "FALSE")
OP, PUNCT, IMPLIES, AT, HASH, NOT_KW, IN_KW, NOTIN_KW, EOF = (
    "OP", "PUNCT", "IMPLIES", "AT", "HASH", "NOT", "IN", "NOTIN", "EOF")

# Longest-first so that ">=" wins over ">".
_OPERATORS = [">=", "<=", "==", "!=", "<>", "&&", "||", ":-",
              ">", "<", "=", "+", "-", "*", "/", "!", "|", "&"]

_PUNCT = set("(),.[]{}")


class Token:
    __slots__ = ("kind", "text", "value", "line", "col")

    def __init__(self, kind, text, value, line, col):
        self.kind = kind
        self.text = text
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return "Token(%s,%r,%d:%d)" % (self.kind, self.text, self.line, self.col)


def _is_id_start(c):
    return c.islower() and c.isalpha() and c.isascii()


def _is_id_body(c):
    return (c.isascii() and (c.isalnum() or c in "_:")) or False


def _is_var_start(c):
    return c.isupper() and c.isalpha() and c.isascii()


def _value_tokens(value, line, col):
    """The literal token(s) a parameter value stands for (sec. 11.8)."""
    if value is True:
        return [Token(TRUE, "#T", True, line, col)]
    if value is False:
        return [Token(FALSE, "#F", False, line, col)]
    if isinstance(value, str):
        return [Token(STRING, escape_string(value), None, line, col)]
    if isinstance(value, int):
        lit = Token(INTEGER, str(abs(value)), None, line, col)
    elif isinstance(value, float):
        lit = Token(DOUBLE, repr(abs(value)), None, line, col)
    else:
        return [Token(DATE, format_date(value), None, line, col)]
    # A negative number is written `-n`, exactly as the parser expects it.
    return [Token(OP, "-", None, line, col), lit] if value < 0 else [lit]


def tokenize(text, source=None, params=None, report=None):
    """Turn program text into a list of tokens ending with EOF.

    `params` maps placeholder names to values (sec. 11.8).  `report`, a
    `params.ParamReport`, is shared across the files of one load: when it is
    given the caller decides what a missing value means; otherwise a missing
    value is an error at the end of this text.
    """
    own_report = report is None
    if own_report:
        report = _params.ParamReport(params)
    tokens = []
    i, line, col = 0, 1, 1
    n = len(text)

    def err(msg):
        raise LexError(msg, line=line, col=col, source=source)

    while i < n:
        c = text[i]

        if c in " \t\r":
            i += 1
            col += 1
            continue
        if c == "\n":
            i += 1
            line += 1
            col = 1
            continue
        if c == "%":                                   # line comment
            while i < n and text[i] != "\n":
                i += 1
            continue

        start_line, start_col = line, col

        # -- string ------------------------------------------------------- #
        if c == '"':
            j = i + 1
            buf = []
            while True:
                if j >= n:
                    err("unterminated string literal")
                d = text[j]
                if d == "\\" and j + 1 < n:
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if d == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        buf.append('""')
                        j += 2
                        continue
                    break
                if d == "$" and text.startswith("$${", j):     # escaped
                    buf.append("${")
                    j += 3
                    continue
                if d == "$" and text.startswith("${", j):
                    k = text.find("}", j + 2)
                    name = text[j + 2:k] if k > 0 else ""
                    if _params.is_name(name):
                        report.met_string(name, source, line, col + (j - i))
                        if report.has(name):
                            buf.append(_params.string_text(report.value(name)))
                        else:                               # left as written
                            buf.append(text[j:k + 1])
                        j = k + 1
                        continue
                if d == "\n":
                    line += 1
                buf.append(d)
                j += 1
            raw = "".join(buf)
            tokens.append(Token(STRING, raw, None, start_line, start_col))
            col += (j + 1 - i)
            i = j + 1
            continue

        # -- parameter placeholder ${name} ---------------------------------- #
        if c == "$" and text.startswith("${", i):
            k = text.find("}", i + 2)
            name = text[i + 2:k] if k > 0 else ""
            if not _params.is_name(name):
                err("malformed parameter placeholder: write ${name}, with a name "
                    "made of letters, digits and underscores")
            end = k + 1
            before = text[i - 1] if i > 0 else ""
            after = text[end] if end < n else ""
            if before.isalnum() or before == "_" or after.isalnum() or after == "_":
                err("parameter ${%s} stands for a whole constant; it cannot be "
                    "part of a name or a number" % name)
            m = end
            while m < n and text[m] in " \t\r\n":
                m += 1
            if m < n and text[m] == "(":
                err("parameter ${%s} stands for a constant; it cannot name a "
                    "predicate or a function" % name)
            report.met_term(name, source, start_line, start_col)
            if report.has(name):
                tokens.extend(_value_tokens(report.value(name), start_line, start_col))
            else:
                # A stand-in, so that the rest of the load can go on and every
                # missing name can be reported at once.
                tokens.append(Token(STRING, "", None, start_line, start_col))
            col += end - i
            i = end
            continue

        # -- date / number -------------------------------------------------- #
        if c.isdigit():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            # date:  dddd-dd-dd  [ dd:dd:dd ]
            if (j - i == 4 and j + 5 < n and text[j] == "-"
                    and text[j + 1:j + 3].isdigit() and text[j + 3] == "-"
                    and text[j + 4:j + 6].isdigit()):
                end = j + 6
                if (end + 9 <= n and text[end] == " "
                        and text[end + 1:end + 3].isdigit() and text[end + 3] == ":"
                        and text[end + 4:end + 6].isdigit() and text[end + 6] == ":"
                        and text[end + 7:end + 9].isdigit()):
                    end += 9
                tokens.append(Token(DATE, text[i:end], None, start_line, start_col))
                col += end - i
                i = end
                continue
            # double
            if j < n and text[j] == "." and j + 1 < n and text[j + 1].isdigit():
                j += 1
                while j < n and text[j].isdigit():
                    j += 1
                tokens.append(Token(DOUBLE, text[i:j], None, start_line, start_col))
            else:
                tokens.append(Token(INTEGER, text[i:j], None, start_line, start_col))
            col += j - i
            i = j
            continue

        # -- identifiers, variables, keywords -------------------------------- #
        if _is_id_start(c):
            j = i + 1
            while j < n:
                d = text[j]
                if d == ":":
                    # A colon belongs to a library alias (`m:sum`) only when a
                    # name follows it; otherwise it opens `:-`.
                    if j + 1 < n and text[j + 1].isascii() and (
                            text[j + 1].isalnum() or text[j + 1] == "_"):
                        j += 1
                        continue
                    break
                if _is_id_body(d):
                    j += 1
                    continue
                break
            word = text[i:j]
            if word == "not":
                tokens.append(Token(NOT_KW, word, None, start_line, start_col))
            elif word == "in":
                tokens.append(Token(IN_KW, word, None, start_line, start_col))
            else:
                tokens.append(Token(ID, word, None, start_line, start_col))
            col += j - i
            i = j
            continue

        if _is_var_start(c):
            j = i + 1
            while j < n and text[j].isascii() and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(Token(VAR, text[i:j], None, start_line, start_col))
            col += j - i
            i = j
            continue

        if c == "_" and not (i + 1 < n and (text[i + 1].isalnum() or text[i + 1] == "_")):
            tokens.append(Token(ANON, "_", None, start_line, start_col))
            i += 1
            col += 1
            continue

        # -- #T / #F / skolem prefix ----------------------------------------- #
        if c == "#":
            if text[i:i + 2] == "#T":
                tokens.append(Token(TRUE, "#T", True, start_line, start_col))
                i += 2
                col += 2
                continue
            if text[i:i + 2] == "#F":
                tokens.append(Token(FALSE, "#F", False, start_line, start_col))
                i += 2
                col += 2
                continue
            tokens.append(Token(HASH, "#", None, start_line, start_col))
            i += 1
            col += 1
            continue

        if c == "@":
            tokens.append(Token(AT, "@", None, start_line, start_col))
            i += 1
            col += 1
            continue

        # -- !in --------------------------------------------------------------- #
        if text[i:i + 3] == "!in" and (i + 3 >= n or not _is_id_body(text[i + 3])):
            tokens.append(Token(NOTIN_KW, "!in", None, start_line, start_col))
            i += 3
            col += 3
            continue

        # -- operators and punctuation ------------------------------------------ #
        for op in _OPERATORS:
            if text.startswith(op, i):
                kind = IMPLIES if op == ":-" else OP
                tokens.append(Token(kind, op, None, start_line, start_col))
                i += len(op)
                col += len(op)
                break
        else:
            if c in _PUNCT:
                tokens.append(Token(PUNCT, c, None, start_line, start_col))
                i += 1
                col += 1
            else:
                err("unexpected character %r" % c)

    if own_report:
        report.raise_if_missing()
    tokens.append(Token(EOF, "", None, line, col))
    return tokens

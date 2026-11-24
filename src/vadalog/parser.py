"""Recursive-descent parser for Vadalog (SPECIFICATION.md sec. 3, 4.2)."""

from . import lexer as lx
from .ast import (AGGREGATES, Annotation, Atom, Condition, Const, EAgg, EBinary,
                  ECall, EConst, ESkolem, EUnary, EVar, FAILURE, EGD, Literal,
                  Program, Rule, TGD, Var)
from .errors import ParseError
from .values import parse_date, unescape_string, vtype

COMPARISONS = {">", "<", ">=", "<=", "=", "<>", "!="}

# expression precedence, lowest binding first
_LEVELS = [
    ("||",),
    ("&&",),
    ("==", "!=", "<>", "<", "<=", ">", ">="),
    ("|", "&"),
    ("+", "-"),
    ("*", "/"),
]


class Parser:
    def __init__(self, tokens, source=None):
        self.toks = tokens
        self.pos = 0
        self.source = source

    # -- token helpers ----------------------------------------------------- #

    @property
    def tok(self):
        return self.toks[self.pos]

    def peek(self, offset=0):
        idx = min(self.pos + offset, len(self.toks) - 1)
        return self.toks[idx]

    def advance(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def at(self, kind, text=None):
        t = self.tok
        return t.kind == kind and (text is None or t.text == text)

    def accept(self, kind, text=None):
        if self.at(kind, text):
            return self.advance()
        return None

    def expect(self, kind, text=None):
        if self.at(kind, text):
            return self.advance()
        self.fail("expected %s but found %r" % (text or kind, self.tok.text or "end of input"))

    def fail(self, message, tok=None):
        t = tok or self.tok
        raise ParseError(message, line=t.line, col=t.col, source=self.source)

    # -- program ------------------------------------------------------------ #

    def parse_program(self, program=None):
        program = program if program is not None else Program()
        while not self.at(lx.EOF):
            self.parse_clause(program)
        return program

    def parse_clause(self, program):
        anns = []
        while self.at(lx.AT):
            self.advance()
            anns.append(self.parse_annotation_body())
            if self.at(lx.PUNCT, "."):
                self.advance()
                program.annotations.extend(anns)
                return
        if not anns and self.at(lx.PUNCT, "."):
            self.advance()
            return
        self.parse_fact_or_rule(program, anns)

    def parse_annotation_body(self):
        t = self.expect(lx.ID)
        args = []
        if self.accept(lx.PUNCT, "("):
            if not self.at(lx.PUNCT, ")"):
                args.append(self.parse_annotation_arg())
                while self.accept(lx.PUNCT, ","):
                    args.append(self.parse_annotation_arg())
            self.expect(lx.PUNCT, ")")
        return Annotation(t.text, args, line=t.line, source=self.source)

    def parse_annotation_arg(self):
        # bare identifiers are accepted as strings: `@output(conn).`
        if self.at(lx.ID) and not self.peek(1).text == "(":
            return self.advance().text
        term = self.parse_term(allow_var=False)
        return term.value

    # -- facts and rules ----------------------------------------------------- #

    def parse_fact_or_rule(self, program, anns):
        start = self.tok

        if self.at(lx.FALSE):                                   # `#F :- body.`
            self.advance()
            self.expect(lx.IMPLIES)
            body, conds = self.parse_body()
            self.expect(lx.PUNCT, ".")
            rule = Rule(FAILURE, [], body, conds, line=start.line, source=self.source)
            rule.annotations = anns
            program.add_rule(rule)
            return

        if self.at(lx.VAR) and self.peek(1).kind == lx.OP and self.peek(1).text == "=":
            left = self.advance().text
            self.advance()
            if not self.at(lx.VAR):
                self.fail("the right-hand side of an EGD head must be a variable")
            right = self.advance().text
            self.expect(lx.IMPLIES)
            body, conds = self.parse_body()
            self.expect(lx.PUNCT, ".")
            rule = Rule(EGD, [], body, conds, line=start.line, source=self.source)
            rule.egd_vars = (left, right)
            rule.annotations = anns
            program.add_rule(rule)
            return

        head = [self.parse_atom()]
        while self.accept(lx.PUNCT, ","):
            head.append(self.parse_atom())

        if self.accept(lx.IMPLIES):
            body, conds = self.parse_body()
            self.expect(lx.PUNCT, ".")
            rule = Rule(TGD, head, body, conds, line=start.line, source=self.source)
            rule.annotations = anns
            program.add_rule(rule)
            return

        self.expect(lx.PUNCT, ".")
        if len(head) != 1:
            self.fail("a fact must consist of a single atom", start)
        atom = head[0]
        values = []
        for t in atom.terms:
            if not isinstance(t, Const):
                self.fail("facts must be ground; %r is not a constant" % t, start)
            values.append(t.value)
        program.facts.append((atom.name, tuple(values), start.line, self.source, anns))

    def parse_atom(self):
        t = self.expect(lx.ID)
        if t.text == "dom" and self.at(lx.PUNCT, "(") and self.peek(1).text == "*":
            self.fail("`dom(*)` belongs to the warded rewriting, which this engine "
                      "does not implement (SPECIFICATION.md sec. 3)", t)
        terms = []
        if self.accept(lx.PUNCT, "("):
            if not self.at(lx.PUNCT, ")"):
                terms.append(self.parse_term())
                while self.accept(lx.PUNCT, ","):
                    terms.append(self.parse_term())
            self.expect(lx.PUNCT, ")")
        return Atom(t.text, terms, line=t.line)

    def parse_body(self):
        literals, conditions = [], []
        while True:
            if self.at(lx.NOT_KW):
                self.advance()
                literals.append(Literal(self.parse_atom(), negated=True))
            elif self.at(lx.ID):
                literals.append(Literal(self.parse_atom(), negated=False))
            elif self.at(lx.VAR):
                conditions.append(self.parse_condition())
            else:
                self.fail("expected a literal or a condition, found %r" % self.tok.text)
            if not self.accept(lx.PUNCT, ","):
                break
        return literals, conditions

    def parse_condition(self):
        v = self.expect(lx.VAR)
        if self.at(lx.IN_KW):
            self.advance()
            return Condition(v.text, "in", self.parse_expression())
        if self.at(lx.NOTIN_KW):
            self.advance()
            return Condition(v.text, "!in", self.parse_expression())
        if self.at(lx.OP) and self.tok.text in COMPARISONS | {"=="}:
            op = self.advance().text
            if op == "==":
                op = "="
            return Condition(v.text, op, self.parse_expression())
        self.fail("expected a comparison operator after %s" % v.text)

    # -- terms ------------------------------------------------------------- #

    def parse_term(self, allow_var=True):
        t = self.tok
        if t.kind == lx.VAR:
            if not allow_var:
                self.fail("a variable is not allowed here")
            self.advance()
            return Var(t.text)
        if t.kind == lx.ANON:
            if not allow_var:
                self.fail("an anonymous variable is not allowed here")
            self.advance()
            return Var("_%d" % self.pos)          # each `_` is a fresh variable
        return Const(self.parse_constant())

    def parse_constant(self):
        t = self.tok
        if t.kind == lx.STRING:
            self.advance()
            return unescape_string(t.text)
        if t.kind == lx.INTEGER:
            self.advance()
            return int(t.text)
        if t.kind == lx.DOUBLE:
            self.advance()
            return float(t.text)
        if t.kind == lx.DATE:
            self.advance()
            return parse_date(t.text)
        if t.kind == lx.TRUE:
            self.advance()
            return True
        if t.kind == lx.FALSE:
            self.advance()
            return False
        if t.kind == lx.OP and t.text == "-":
            self.advance()
            nxt = self.tok
            if nxt.kind == lx.INTEGER:
                self.advance()
                return -int(nxt.text)
            if nxt.kind == lx.DOUBLE:
                self.advance()
                return -float(nxt.text)
            self.fail("expected a number after `-`")
        if t.kind == lx.PUNCT and t.text == "{":
            return self.parse_set_literal()
        if t.kind == lx.PUNCT and t.text == "[":
            return self.parse_list_literal()
        self.fail("expected a constant, found %r" % t.text)

    def parse_set_literal(self):
        start = self.expect(lx.PUNCT, "{")
        items = []
        if not self.at(lx.PUNCT, "}"):
            items.append(self.parse_constant())
            while self.accept(lx.PUNCT, ","):
                items.append(self.parse_constant())
        self.expect(lx.PUNCT, "}")
        return self.make_set(items, start)

    def make_set(self, items, start):
        kinds = {vtype(i) for i in items}
        if len({"int", "double"} & kinds) == 2:
            kinds = (kinds - {"int", "double"}) | {"num"}
        if len(kinds) > 1:
            self.fail("set literals must be homogeneous, found %s"
                      % ", ".join(sorted(kinds)), start)
        return frozenset(items)

    def parse_list_literal(self):
        self.expect(lx.PUNCT, "[")
        items = []
        if not self.at(lx.PUNCT, "]"):
            items.append(self.parse_constant())
            while self.accept(lx.PUNCT, ","):
                items.append(self.parse_constant())
        self.expect(lx.PUNCT, "]")
        return tuple(items)

    # -- expressions --------------------------------------------------------- #

    def parse_expression(self, level=0):
        if level >= len(_LEVELS):
            return self.parse_unary()
        ops = _LEVELS[level]
        node = self.parse_expression(level + 1)
        while self.at(lx.OP) and self.tok.text in ops:
            op = self.advance().text
            rhs = self.parse_expression(level + 1)
            node = EBinary(op, node, rhs)
        return node

    def parse_unary(self):
        if self.at(lx.OP, "!"):
            self.advance()
            return EUnary("!", self.parse_unary())
        if self.at(lx.OP, "-"):
            if self.peek(1).kind in (lx.INTEGER, lx.DOUBLE):
                self.advance()
                nxt = self.advance()
                value = -int(nxt.text) if nxt.kind == lx.INTEGER else -float(nxt.text)
                return EConst(value)
            self.advance()
            return EUnary("-", self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.tok

        if t.kind == lx.PUNCT and t.text == "(":
            self.advance()
            node = self.parse_expression()
            self.expect(lx.PUNCT, ")")
            return node

        if t.kind == lx.HASH:                                   # skolem function
            self.advance()
            name = self.expect(lx.ID)
            args = self.parse_call_args()
            return ESkolem(name.text, args)

        if t.kind == lx.VAR:
            self.advance()
            return EVar(t.text)

        if t.kind == lx.ID:
            self.advance()
            if not self.at(lx.PUNCT, "("):
                self.fail("bare identifier %r is not an expression; "
                          "did you mean %s()?" % (t.text, t.text), t)
            if ":" not in t.text and t.text in AGGREGATES:
                return self.parse_aggregate(t)
            args = self.parse_call_args()
            return ECall(t.text, args)

        if t.kind == lx.PUNCT and t.text == "[":
            items = self.parse_bracketed("[", "]")
            if all(isinstance(i, EConst) for i in items):
                return EConst(tuple(i.value for i in items))
            return ECall("__list__", items)

        if t.kind == lx.PUNCT and t.text == "{":
            # A set literal may hold expressions, not only constants, when it
            # appears inside an expression: `Q = {X} | Q1`.
            items = self.parse_bracketed("{", "}")
            if all(isinstance(i, EConst) for i in items):
                return EConst(self.make_set([i.value for i in items], t))
            return ECall("__set__", items)

        return EConst(self.parse_constant())

    def parse_bracketed(self, opener, closer):
        self.expect(lx.PUNCT, opener)
        items = []
        if not self.at(lx.PUNCT, closer):
            items.append(self.parse_expression())
            while self.accept(lx.PUNCT, ","):
                items.append(self.parse_expression())
        self.expect(lx.PUNCT, closer)
        return items

    def parse_call_args(self):
        self.expect(lx.PUNCT, "(")
        args = []
        if not self.at(lx.PUNCT, ")"):
            args.append(self.parse_expression())
            while self.accept(lx.PUNCT, ","):
                args.append(self.parse_expression())
        self.expect(lx.PUNCT, ")")
        return args

    def parse_aggregate(self, name_tok):
        op = name_tok.text
        self.expect(lx.PUNCT, "(")
        operand = None
        contributors = []
        if not self.at(lx.PUNCT, ")"):
            operand = self.parse_expression()
            while self.accept(lx.PUNCT, ","):
                if self.at(lx.OP, "<"):
                    contributors = self.parse_var_list()
                elif self.at(lx.PUNCT, "["):
                    contributors = self.parse_bracket_var_list()
                else:
                    self.fail("%s takes one expression optionally followed by a "
                              "list of contributor variables; for the numeric "
                              "min/max use the `math` library with an alias" % op,
                              name_tok)
        self.expect(lx.PUNCT, ")")
        if operand is None:
            operand = EConst(1)
        return EAgg(op, operand, contributors)

    def parse_var_list(self):
        self.expect(lx.OP, "<")
        names = [self.expect(lx.VAR).text]
        while self.accept(lx.PUNCT, ","):
            names.append(self.expect(lx.VAR).text)
        self.expect(lx.OP, ">")
        return names

    def parse_bracket_var_list(self):
        self.expect(lx.PUNCT, "[")
        names = []
        if not self.at(lx.PUNCT, "]"):
            names.append(self.expect(lx.VAR).text)
            while self.accept(lx.PUNCT, ","):
                names.append(self.expect(lx.VAR).text)
        self.expect(lx.PUNCT, "]")
        return names


def parse(text, source=None, program=None, params=None, report=None):
    """Parse program text; `params`/`report` fill placeholders (sec. 11.8)."""
    tokens = lx.tokenize(text, source, params=params, report=report)
    return Parser(tokens, source).parse_program(program)

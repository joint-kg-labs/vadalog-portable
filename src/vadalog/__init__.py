"""vadalog-portable: a small, dependency-free Datalog+/- (Vadalog) reasoner.

See SPECIFICATION.md for the language and engine specification.
"""

__version__ = "0.6.0"

from .chase import Options              # noqa: E402,F401
from .errors import VadalogError        # noqa: E402,F401
from .program import (Runner, load_program, load_text,  # noqa: E402,F401
                      run_file, run_text)

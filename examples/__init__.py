"""The toy examples, carried inside the package.

They travel with the engine — inside `vadalog.pyz` and inside an installed
wheel — so that someone who was handed the single file has something to run
before writing anything of their own:

    vadalog examples                       # what is in here
    vadalog examples --extract DIR         # write them out, then edit them

Extracting matters: inside the archive they are read-only resources, and the
web UI serves a directory on disk, so a copy on disk is what makes them
openable, editable and runnable from the page.  They are a set to try the
engine with; real work happens on your own files.

The module is deliberately tiny and standard-library only, like the rest.
"""

import os

# (file, one line about it).  A data file follows the program that reads it.
EXAMPLES = (
    ("reachability.vada", "transitive closure: the smallest recursive program"),
    ("existentials.vada", "existential quantification, marked nulls"),
    ("components.vada", "equality-generating dependencies over marked nulls"),
    ("aggregation.vada", "stratified aggregation: sum, max, avg, count"),
    ("company_control.vada", "recursion and monotonic aggregation together"),
    ("csv_pipeline.vada", "CSV in, CSV out, through @bind"),
    ("holdings.csv", "the input csv_pipeline.vada reads"),
)

HERE = os.path.dirname(os.path.abspath(__file__))


def names():
    """The example files, programs first, in the order they are worth reading."""
    return [name for name, _ in EXAMPLES]


def read(name):
    """The bytes of one example.

    Read as a package resource, so it works from a zipapp, where there is no
    file to open.  The three routes are the ones `vadalog.ui.server.read_index`
    documents: the module loader first (the only one correct everywhere, and
    the only one that gets the path spelling right inside an archive), then
    importlib.resources, then the plain file of a source checkout.
    """
    if name not in names():
        raise KeyError(name)

    # `globals()`, not `sys.modules[__name__]`: a source checkout loads this
    # file by path, under a name that is not in sys.modules.
    loader_data = getattr(globals().get("__loader__"), "get_data", None)
    if loader_data is not None:
        try:
            return loader_data(os.path.join(os.path.dirname(__file__), name))
        except Exception:
            pass

    if __package__:
        try:
            from importlib.resources import files
            return (files(__package__) / name).read_bytes()
        except Exception:
            pass

    with open(os.path.join(HERE, name), "rb") as fh:
        return fh.read()


def extract(dest, force=False):
    """Write every example into `dest`, which is created if it is not there.

    Returns (written, skipped).  An existing file is left alone unless `force`:
    the point of extracting is to edit the copies, and a second extraction must
    not silently discard those edits.
    """
    os.makedirs(dest, exist_ok=True)
    written, skipped = [], []
    for name in names():
        target = os.path.join(dest, name)
        if os.path.exists(target) and not force:
            skipped.append(target)
            continue
        with open(target, "wb") as fh:
            fh.write(read(name))
        written.append(target)
    return written, skipped

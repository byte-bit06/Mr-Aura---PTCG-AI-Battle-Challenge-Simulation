"""
build_alakazam_agent.py — unpack the Alakazam notebook into a runnable agent.

`codex_sol_eclipse_alakazam.py` is a Kaggle *builder* script, not an agent:
the real agent is a string literal (MAIN_SOURCE), the deck is another string
(DECK_SOURCE), and the bottom of the file writes a submission tarball. Import
it directly and it starts building tarballs and asserting on cg/libcg.so.

So we extract instead:

    <agent dir>/
      main.py     <- MAIN_SOURCE
      deck.csv    <- DECK_SOURCE
      group.txt   <- GROUP_SOURCE (if present)

Usage:
    python3 build_alakazam_agent.py [source.py] [output_dir]

Defaults to codex_sol_eclipse_alakazam.py in this folder, output to
./Alakazam_Courage/.
"""

import os
import re
import sys

DEFAULT_SRC = "codex_sol_eclipse_alakazam.py"
DEFAULT_OUT = "Alakazam_Courage"


def _extract(src_text, name):
    """Pull `NAME = r'''...'''` out of the builder script."""
    m = re.search(re.escape(name) + r"\s*=\s*r'''(.*?)'''", src_text, re.S)
    return m.group(1) if m else None


def build(src_path=None, out_dir=None):
    here = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.abspath(src_path or os.path.join(here, DEFAULT_SRC))
    out_dir = os.path.abspath(out_dir or os.path.join(here, DEFAULT_OUT))

    if not os.path.exists(src_path):
        print(f"! source not found: {src_path}")
        return 1

    text = open(src_path, encoding="utf-8", errors="replace").read()
    main_src = _extract(text, "MAIN_SOURCE")
    deck_src = _extract(text, "DECK_SOURCE")
    group_src = _extract(text, "GROUP_SOURCE")

    if main_src is None or deck_src is None:
        print("! could not find MAIN_SOURCE / DECK_SOURCE in the builder script.")
        print("  (has the notebook been re-exported in a different shape?)")
        return 1

    deck_ids = [int(x) for x in deck_src.split() if x.strip().isdigit()]
    if len(deck_ids) != 60:
        print(f"! deck has {len(deck_ids)} cards, expected 60 - refusing to write")
        return 1

    try:
        import ast
        ast.parse(main_src)
    except SyntaxError as e:
        print(f"! extracted main.py does not parse: {e}")
        return 1
    if "def agent(" not in main_src:
        print("! extracted main.py defines no agent() - refusing to write")
        return 1

    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "main.py"), "w", encoding="utf-8").write(main_src)
    open(os.path.join(out_dir, "deck.csv"), "w", encoding="utf-8").write(
        "\n".join(str(c) for c in deck_ids) + "\n")
    if group_src:
        open(os.path.join(out_dir, "group.txt"), "w", encoding="utf-8").write(
            group_src.strip() + "\n")

    print(f"wrote {out_dir}")
    print(f"  main.py   {len(main_src.splitlines())} lines")
    print(f"  deck.csv  {len(deck_ids)} cards, {len(set(deck_ids))} unique")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(build(args[0] if args else None,
                   args[1] if len(args) > 1 else None))

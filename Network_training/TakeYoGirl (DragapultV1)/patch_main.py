"""
patch_main.py — wires battle_log.py into main.py.

    python3 patch_main.py            # patch in place (writes main.py.bak first)
    python3 patch_main.py --dry-run  # show what it would change

Three edits, all additive; none change decision-making:

  1. import + construct BATTLE_LOG after the card index exists
  2. wrap sanitize_action so every returned selection is recorded
     (every return path in agent() funnels through it, including the
     exception fallback — nothing goes unrecorded)
  3. tag whether each decision came from the search or the policy

If an anchor isn't found the patcher tells you exactly what to paste and
where, rather than guessing.
"""

import os
import sys
import shutil


PRIORITY_HELPER_CODE = """
# --- transcript-driven priority fixes -------------------------------------
try:
    from dragapult_priorities import (
        build_attack_table, attack_score, retreat_veto, attach_veto,
        end_turn_score, discard_veto)
    try:
        from cg.api import all_attack as _all_attack
        build_attack_table(_all_attack)
        log_rule_execution("  [PRIORITIES] attack damage table loaded")
    except Exception as _e:
        log_rule_execution(f"  [PRIORITIES] attack table unavailable: {_e}")
    _PRIORITIES_OK = True
except Exception as _e:
    _PRIORITIES_OK = False
    log_rule_execution(f"  [PRIORITIES] disabled: {_e}")


def _priority_override(view, select_obj, options, o, otype):
    \"\"\"Veto or boost that outranks the tuned weight. None = no opinion.\"\"\"
    if not _PRIORITIES_OK:
        return None
    try:
        _ctx = _opt(select_obj, "context", None)
        _ctx = getattr(_ctx, "value", _ctx)
        if _ctx in (8, 10):          # DISCARD, TO_DECK_BOTTOM
            return discard_veto(view, _resolve_cid(view, select_obj, o, otype))
        if otype == OptionType.ATTACK:
            return attack_score(view, o, _opt)
        if otype == OptionType.RETREAT:
            return retreat_veto(view)
        if otype == OptionType.ATTACH:
            return attach_veto(view, o, _opt)
        if otype == OptionType.END:
            return end_turn_score(options, _opt, OptionType.END, OptionType.NO)
    except Exception:
        return None
    return None

"""

EDITS = [
    {
        "name": "logger construction",
        # Several candidates: the file has been refactored more than once.
        "anchors": ["HEURISTICS = Heuristics(CARD_INDEX)",
                    "HEURISTICS = Heuristics(",
                    "CARD_INDEX = _build_card_index()"],
        "after": True,
        "reindent": False,
        "guard": "BATTLE_LOG",
        "code": '''
# --- battle transcript logging (diagnostics only, no effect on play) -------
try:
    from battle_log import BattleLogger
    BATTLE_LOG = BattleLogger(
        card_index=getattr(HEURISTICS, "card_index", None) or CARD_INDEX)
    log_rule_execution(f"  [BATTLE LOG] writing to {BATTLE_LOG.path}")
except Exception as _e:
    class _NullLog:
        path = "(disabled)"
        def observe(self, *a, **k): pass
        def source(self, *a, **k): pass
        def record_result(self, *a, **k): pass
        def flush(self): pass
    BATTLE_LOG = _NullLog()
    log_rule_execution(f"  [BATTLE LOG] disabled: {_e}")
''',
    },
    {
        "name": "sanitize_action wrapper",
        "anchors": ["def agent(obs_dict: dict) -> list[int]:", "def agent(obs_dict"],
        "after": False,
        "reindent": False,
        "guard": "_sanitize_action_impl",
        "code": '''
# --- record every returned selection --------------------------------------
_sanitize_action_impl = sanitize_action


def sanitize_action(chosen_indices, select_data, obs_dict=None):
    result = _sanitize_action_impl(chosen_indices, select_data, obs_dict)
    try:
        BATTLE_LOG.observe(obs_dict, result)
    except Exception:
        pass
    return result

''',
    },
    {
        "name": "search source tag",
        "anchors": ["return sanitize_action(res.best_move",
                    "sanitize_action(res.best_move"],
        "after": False,
        "reindent": True,
        "guard": 'BATTLE_LOG.source("search"',
        "code": 'BATTLE_LOG.source("search", f"sep={separation:.3f}")\n',
    },
    {
        "name": "policy source tag",
        "anchors": ["chosen = _fill_multi(ranked",
                    "_fill_multi(ranked, select_data)",
                    'PLAN.stats["policy"] += 1'],
        "after": False,
        "reindent": True,
        "guard": 'BATTLE_LOG.source("policy")',
        "code": 'BATTLE_LOG.source("policy")\n',
    },
    {
        "name": "priority override helper",
        "anchors": ["def policy_rank(view, select_obj, options):"],
        "after": False,
        "reindent": False,
        "guard": "def _priority_override",
        "code": PRIORITY_HELPER_CODE,
    },
    {
        "name": "priority overrides (attack / retreat / attach / end)",
        "anchors": ["scored.append((s, i))"],
        "after": False,
        "reindent": True,
        "guard": "ov = _priority_override",
        "code": (
            "ov = _priority_override(view, select_obj, options, o, otype)\n"
            "if ov is not None:\n"
            "    s = ov\n"
        ),
    },
    {
        "name": "drop vetoed options from the ranking",
        "anchors": ["return [i for _, i in scored]"],
        "after": False,
        "reindent": True,
        "guard": "_legal_ranked",
        "code": (
            "_legal_ranked = [i for _s, i in scored if _s > -0.5]\n"
            "if _legal_ranked:\n"
            "    return _legal_ranked\n"
        ),
    },
    {
        "name": "search must clear its own noise floor",
        "anchors": ["trusted = usable and res.nodes > 0 and separation >= SEARCH_TIE_EPSILON"],
        "after": True,
        "reindent": True,
        "guard": "_noise_floor",
        "code": (
            "_noise_floor = max(m.spread for m in ranked_moves[:2]) if ranked_moves else 0.0\n"
            "trusted = trusted and separation >= _noise_floor\n"
            "if os.environ.get('DRAGAPULT_DISABLE_SEARCH'):\n"
            "    trusted = False\n"
        ),
    },
]


def _find_anchor(lines, patterns, skip_defs=True):
    """
    Locate an anchor by *content*, not exact whitespace — indentation and
    surrounding formatting drift between edits of the file. Returns
    (line_index, indent_string) or (None, None).
    """
    for pat in patterns:
        want = pat.strip()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if want not in stripped:
                continue
            # Don't anchor a call-site pattern onto the function's own def.
            if skip_defs and stripped.startswith("def ") and not want.startswith("def "):
                continue
            indent = line[:len(line) - len(line.lstrip())]
            return i, indent
    return None, None


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def patch(path=None, dry_run=False):
    # Default to the main.py sitting NEXT TO this script, not the one in the
    # current working directory. Invoking by absolute path from elsewhere
    # (e.g. `python "C:/.../agent/patch_main.py"` from the repo root) would
    # otherwise silently patch a completely different main.py.
    if path is None:
        path = os.path.join(_SCRIPT_DIR, "main.py")
    path = os.path.abspath(path)

    if not os.path.exists(path):
        print(f"! not found: {path}")
        print(f"  (place patch_main.py beside the main.py you want to patch,")
        print(f"   or pass the path explicitly: python patch_main.py <path>)")
        return 1

    print(f"patching: {path}")

    # Warn about the classic mistake: a different main.py in the cwd.
    cwd_main = os.path.abspath(os.path.join(os.getcwd(), "main.py"))
    if cwd_main != path and os.path.exists(cwd_main):
        print(f"note    : a different main.py also exists at {cwd_main}")
        print(f"          it is NOT being touched.")

    src = open(path, encoding="utf-8", errors="replace").read()
    newline = "\r\n" if "\r\n" in src else "\n"
    work = src.replace("\r\n", "\n")

    lines = work.split("\n")
    applied, skipped, missing = [], [], []
    for e in EDITS:
        if e["guard"] in work:
            skipped.append(e["name"])
            continue
        idx, indent = _find_anchor(lines, e["anchors"])
        if idx is None:
            missing.append(e)
            continue
        code = e["code"]
        if e["reindent"]:
            # Re-indent to the anchor while PRESERVING relative structure —
            # lstrip() on every line would flatten nested blocks.
            raw = [l for l in code.splitlines() if l.strip()]
            base = min(len(l) - len(l.lstrip()) for l in raw)
            code = "".join(indent + l[base:] + "\n" for l in raw)
        insert_at = idx + 1 if e["after"] else idx
        lines[insert_at:insert_at] = code.rstrip("\n").split("\n")
        applied.append(f"{e['name']} (line {insert_at + 1})")
        work = "\n".join(lines)

    print(f"applied : {', '.join(applied) or 'none'}")
    if skipped:
        print(f"skipped : {', '.join(skipped)} (already present)")
    if missing:
        print("\n! could not find anchors for:")
        for e in missing:
            print(f"\n  --- {e['name']} ---")
            print("  tried anchors: " + ", ".join(repr(a[:50]) for a in e["anchors"]))
            print(f"  paste this {'after' if e['after'] else 'before'} that line:")
            print("\n".join("      " + l for l in e["code"].splitlines()))
        print("\n(other edits were still applied)" if applied else "")

    if dry_run:
        print("\n[dry run] nothing written")
        return 0
    # Syntax-check BEFORE writing; never leave a broken agent on disk.
    try:
        import ast
        ast.parse(work)
    except SyntaxError as ex:
        print(f"\n! patched result does not parse: {ex}")
        print("  nothing was written — your main.py is untouched.")
        print("  (this usually means the source file already had a syntax error,")
        print("   or an anchor matched inside a string/comment)")
        return 1

    if applied:
        shutil.copy(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(work.replace("\n", newline))
        print(f"\nwrote {path} (backup at {path}.bak)")
    print("syntax check: ok")
    return 0


if __name__ == "__main__":
    explicit = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    sys.exit(patch(explicit, dry_run="--dry-run" in sys.argv))

r"""Normalise two pg_dump --schema-only files and diff them.

Strips pg_dump session artefacts (\restrict/\unrestrict nonces, comment banners)
and Alembic's own alembic_version bookkeeping table, which by design exists only
in a migrated database. Anything else that differs is a real schema divergence.
"""
import difflib
import re
import sys

DROP_LINE = re.compile(r"^(\\restrict|\\unrestrict|--|SET |SELECT pg_catalog)")


def normalise(path: str) -> list[str]:
    text = open(path).read()
    # Remove the alembic_version table and its primary key.
    text = re.sub(
        r"CREATE TABLE public\.alembic_version.*?\);\n", "", text, flags=re.S
    )
    text = re.sub(
        r"ALTER TABLE ONLY public\.alembic_version\s+ADD CONSTRAINT [^;]+;\n",
        "", text, flags=re.S,
    )
    out = []
    for line in text.splitlines():
        if DROP_LINE.match(line.strip()) or not line.strip():
            continue
        out.append(line.rstrip())
    return out


def main() -> int:
    a_path, b_path = sys.argv[1], sys.argv[2]
    a, b = normalise(a_path), normalise(b_path)
    delta = list(difflib.unified_diff(a, b, "create_all", "alembic", lineterm="", n=1))
    print(f"create_all : {len(a)} normalised DDL lines")
    print(f"alembic    : {len(b)} normalised DDL lines")
    if not delta:
        print("\nIDENTICAL - the migration reproduces create_all() exactly.")
        return 0
    print(f"\nDIVERGENCE ({len(delta)} diff lines):")
    print("\n".join(delta))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Smart folder rule engine — evaluate rule_json into a Media query.

This is the public entry point used by the smart-folder preview endpoint.
The per-dimension SQL generation lives in `app.rules.handlers`, dispatched
through the registry in `app.rules.base`.
"""
from sqlalchemy import select
from sqlalchemy.sql.expression import Select

from app.models.media import Media
from app.rules import handlers  # noqa: F401 — registers all RuleHandlers on import
from app.rules.base import apply_rule


def evaluate_rule(rule_json: dict) -> Select:
    """Build a SQLAlchemy select for Media rows matching the rule tree.

    Args:
        rule_json: A rule tree produced by the frontend editor, e.g.
            {"type": "group", "logic": "and", "children": [ ... ]}

    Returns:
        A SQLAlchemy ``select(Media)`` query with the appropriate WHERE
        clauses applied. An empty/invalid rule returns an unconstrained
        query (matches all media).
    """
    query: Select = select(Media)
    return apply_rule(query, rule_json)

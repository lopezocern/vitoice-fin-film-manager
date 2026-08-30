"""RuleHandler base class and registry.

Each RuleHandler handles one dimension of smart folder rules:
- tag: filter by tag membership
- duration: filter by media duration
- resolution: filter by video resolution
- rating: filter by user rating
- favorite: filter by favorite status
- library: filter by library
- media_type: filter by media type
- file_size: filter by file size

Handlers register themselves and generate SQL fragments for the rule engine.
This replaces the old system's if/elif chain that was impossible to extend.
"""
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import Select, and_, or_
from sqlalchemy.sql.elements import BinaryExpression

from app.models.media import Media
from app.models.tag import VideoTag


class RuleHandler(ABC):
    """Abstract base for rule dimension handlers."""

    dimension: str = ""

    @abstractmethod
    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        """Convert a rule condition to a SQLAlchemy expression.

        Args:
            operator: Comparison operator (eq, ne, gt, lt, gte, lte, in, contains, etc.)
            value: The comparison value

        Returns:
            SQLAlchemy expression to filter Media, or None if invalid.
        """
        pass

    @abstractmethod
    def validate(self, operator: str, value: Any) -> bool:
        """Validate that the operator and value are acceptable for this dimension."""
        pass

    def get_joins(self) -> list:
        """Return additional join conditions needed for this dimension.

        Override if the dimension requires joining other tables (e.g. VideoTag).
        Returns list of (model, condition) tuples for .join().
        """
        return []


class RuleRegistry:
    """Registry for rule handlers — replaces if/elif dispatch."""

    def __init__(self):
        self._handlers: dict[str, RuleHandler] = {}

    def register(self, handler: RuleHandler) -> None:
        """Register a handler."""
        if not handler.dimension:
            raise ValueError(f"Handler {handler.__class__.__name__} has no dimension")
        self._handlers[handler.dimension] = handler

    def get(self, dimension: str) -> RuleHandler | None:
        """Get a handler by dimension name."""
        return self._handlers.get(dimension)

    def dimensions(self) -> list[str]:
        """List all registered dimensions."""
        return list(self._handlers.keys())


# Global registry
registry = RuleRegistry()


def apply_rule(query: Select, rule_node: dict) -> Select:
    """Apply a rule tree to a SQLAlchemy query.

    Correctly handles arbitrarily nested groups. Each group's children are
    combined with AND/OR according to the group's ``logic`` key. Empty or
    invalid groups are treated as pass-through (no constraint added), which
    matches the frontend expectation that an empty rule matches all media.

    Rule node structure:
    {
        "type": "group",  # or "condition"
        "logic": "and",   # "and" | "or" (for groups)
        "children": [...] # for groups (may themselves be groups)
    }
    or:
    {
        "type": "condition",
        "dimension": "duration",
        "operator": "gt",
        "value": 3600
    }
    """
    if not rule_node:
        return query

    expr = _build_group_expr(rule_node)
    if expr is not None:
        query = query.where(expr)
    # S7 fix: smart folders should never surface soft-deleted (recycle-bin)
    # media, regardless of the rule. Matches the list-view semantics.
    query = query.where(Media.is_deleted == False)  # noqa: E712
    return query


def _build_group_expr(node: dict) -> BinaryExpression | None:
    """Recursively build a combined boolean expression for a rule group.

    Returns None for empty/invalid groups so they are treated as pass-through.
    """
    if not node:
        return None

    if node.get("type") == "group":
        children = node.get("children", []) or []
        sub_exprs = []
        for child in children:
            expr = _build_group_expr(child)
            if expr is not None:
                sub_exprs.append(expr)
        if not sub_exprs:
            return None
        logic = (node.get("logic") or "and").lower()
        if logic == "or":
            return or_(*sub_exprs)
        return and_(*sub_exprs)

    # Leaf condition node
    return _build_condition(node)


def _build_condition(rule: dict) -> BinaryExpression | None:
    """Build a single leaf condition from a condition node."""
    dimension = rule.get("dimension")
    operator = rule.get("operator")
    value = rule.get("value")

    if not dimension or not operator:
        return None

    handler = registry.get(dimension)
    if not handler:
        return None

    if not handler.validate(operator, value):
        return None

    return handler.to_sql(operator, value)

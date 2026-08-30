"""Rules package — registered RuleHandler architecture.

Replaces the old if/elif hardcoding in the smart folder rule engine.
Each dimension (tag, duration, resolution, etc.) is a registered handler
that generates SQL fragments.
"""

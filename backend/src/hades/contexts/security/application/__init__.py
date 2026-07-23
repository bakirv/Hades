"""Security Engine application layer — analyzers, scoring, explainability, engine.

Composition of many single-responsibility analyzers into one conservative
verdict. The engine orchestrates I/O (lists, persistence, events); the analyzers
are pure functions over a pre-assembled :class:`SecurityInputs` context.
"""

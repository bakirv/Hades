"""Feature Engine application layer.

Transforms the cleaned :class:`FeatureInputs` bundle into a versioned
:class:`FeatureSet` of (hundreds of) numeric features. Extractors are small and
single-purpose; the engine composes them, validates the output is finite, and
hands it to the feature store. It forms no opinion — a feature is a measurement,
never a decision.
"""

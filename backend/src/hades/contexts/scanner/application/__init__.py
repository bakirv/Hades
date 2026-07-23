"""Scanner application layer — discovery, metadata, validation, pipeline.

These services orchestrate the domain ports; they contain no I/O themselves
(that lives in ``infrastructure``) and take no trading decision. Their sole
output is clean, stored facts and the domain events announcing them.
"""

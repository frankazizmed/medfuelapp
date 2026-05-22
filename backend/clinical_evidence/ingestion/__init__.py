"""Ingestion layer — convert raw bytes into normalized text suitable for extraction.

Inputs: RawDocument records produced by the discovery layer.
Outputs: RawDocument records with normalized ``text`` and optional chunked
embeddings persisted to the ce_doc_chunks table.
"""

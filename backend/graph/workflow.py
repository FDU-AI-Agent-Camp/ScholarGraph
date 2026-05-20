"""LangGraph pipeline (BE-L wires ingest → classify → extract → store)."""

# TODO(BE-L): define StateGraph nodes calling:
#   backend.ingest.ingest_pdf
#   backend.agents.classifier.classify
#   backend.agents.extractor.extract
#   backend.graph.store.GraphStore.save

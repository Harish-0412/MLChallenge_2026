"""Member B: candidate retrieval channels (B3/B4), implemented as inverted-index joins in DuckDB.

Design rules (see reports/eda/validation_protocol.md):

* Retrieval never sees a label. The engine functions only touch the feature tables ``bq`` (benchmark queries) and ``tt`` (target corpus);
  the truth relation is attached later, by the evaluator only.
* Country is the first partition: every run handles one country, so no candidate can cross countries.
* Every channel emits (qid, tid, channel, rank, score) with rank <= MAX_K, and channels are never merged by comparing their scores, so an
  address-only or cross-script candidate is not dropped for having a low name score.
* Corpus statistics (document frequency / IDF) are computed on the retrieval corpus of the protocol, a documented unsupervised statistic.
"""
MAX_K = 100

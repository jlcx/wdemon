"""
Tests for indicators.labels_less_consistent.

Uses a fake db_pool (no real Postgres) to keep these runnable without the
algae DB. For real-DB exercises, see manual script usage documented elsewhere.

Expectation tiers mirror test_bad_description.py:
  'fire' | 'none' | 'observe'
"""
from contextlib import contextmanager

import pytest

from indicators import labels_less_consistent


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self._fetched = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self._fetched = self._rows

    def fetchall(self):
        return list(self._fetched or [])


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return _FakeCursor(self._rows)


class FakePool:
    """Minimal stand-in for psycopg_pool.ConnectionPool supporting one query."""
    def __init__(self, rows):
        self._rows = rows

    @contextmanager
    def connection(self):
        yield _FakeConn(self._rows)


def _event(qid, lang, new_label):
    return {'title': qid, 'comment': f'/* wbsetlabel-set:1|{lang} */ {new_label}'}


# 55 af+en+… synthetic "John Smith" langs; 3 langs already diverged.
CONSENSUS_ROWS = (
    [(f'lang{i}', 'John Smith') for i in range(55)]
    + [('ar', 'جون سميث'), ('bg', 'Джон Смит'), ('ja', 'ジョン・スミス')]
    + [('af', 'John Smith')]  # pre-edit value for the language we'll edit
)

CASES = [
    # (id, edit-lang, new-label, rows, expected)
    (
        'spam_diverges_from_consensus',
        'af', 'SpamBot 5000 (TM)', CONSENSUS_ROWS, 'fire',
    ),
    (
        'edit_matches_consensus',
        'af', 'John Smith', CONSENSUS_ROWS, 'none',
    ),
    (
        'transliteration_never_matched_consensus',
        'ar', 'جون سميث المحدث', CONSENSUS_ROWS, 'none',
    ),
    (
        'weak_consensus_below_threshold',
        'af', 'Anything',
        [('af', 'Old'), ('en', 'Old'), ('de', 'Other')],  # only 1 other matches
        'none',
    ),
    (
        'no_prior_row_for_lang',
        'xx', 'Something New', CONSENSUS_ROWS, 'none',
    ),
    (
        'case_only_change',
        'af', 'john smith', CONSENSUS_ROWS, 'none',
    ),
]


@pytest.mark.parametrize(
    'case_id,lang,new_label,rows,expected',
    CASES,
    ids=[c[0] for c in CASES],
)
def test_labels_less_consistent(case_id, lang, new_label, rows, expected):
    pool = FakePool(rows)
    result = labels_less_consistent(_event('Q1', lang, new_label), db_pool=pool)
    print(f'[{case_id}] result={result}')

    if expected == 'fire':
        assert result is not None, f'{case_id}: expected fire; got None'
    elif expected == 'none':
        assert result is None, f'{case_id}: expected no fire; got {result}'
    elif expected == 'observe':
        return
    else:
        raise ValueError(f'unknown expectation {expected!r} for {case_id}')


def test_non_label_action_is_skipped():
    pool = FakePool(CONSENSUS_ROWS)
    event = {'title': 'Q1', 'comment': '/* wbsetclaim-update:P31[[Q5]] */'}
    assert labels_less_consistent(event, db_pool=pool) is None


def test_missing_db_pool_short_circuits():
    assert labels_less_consistent(_event('Q1', 'af', 'Anything'), db_pool=None) is None

"""
Tests for indicators.time_travel_edge.

Uses a fake db_pool matching the pattern in test_labels_less_consistent.py.
"""
from contextlib import contextmanager

import pytest

from indicators import time_travel_edge


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
    def __init__(self, rows):
        self._rows = rows

    @contextmanager
    def connection(self):
        yield _FakeConn(self._rows)


def _claim_event(src_qid, pid, dst_qid, action='wbcreateclaim-create'):
    return {
        'title': src_qid,
        'comment': f'/* {action}:{pid}[[{dst_qid}]] */',
    }


# Shape: (qid, time_value, precision) — matches what wd_dates returns.
def _dob(qid, year, precision=11):
    return (qid, f'+{year:04d}-01-01T00:00:00Z', precision)


CASES = [
    # Einstein (b.1879) "influenced by" someone born 1980 → time-travel.
    (
        'influenced_by_younger_person',
        _claim_event('Q937', 'P737', 'Q999901'),
        [_dob('Q937', 1879), _dob('Q999901', 1980)],
        'fire',
    ),
    # Einstein "influenced by" Newton (b.1643) → legitimate, no fire.
    (
        'influenced_by_older_person',
        _claim_event('Q937', 'P737', 'Q935'),
        [_dob('Q937', 1879), _dob('Q935', 1643)],
        'none',
    ),
    # Work P170 creator where creator DOB post-dates work's inception.
    (
        'work_created_by_future_person',
        _claim_event('Q999800', 'P170', 'Q999801'),
        [
            ('Q999800', '+1850-01-01T00:00:00Z', 11),   # inception (any start prop)
            _dob('Q999801', 1900),
        ],
        'fire',
    ),
    # Forward-causal relation (P40 child) isn't in CAUSAL_BACKWARD → skipped.
    (
        'forward_relation_ignored',
        _claim_event('Q937', 'P40', 'Q999901'),
        [_dob('Q937', 1879), _dob('Q999901', 1980)],
        'none',
    ),
    # Same year — not strictly after, no fire.
    (
        'same_year_no_fire',
        _claim_event('Q937', 'P737', 'Q999902'),
        [_dob('Q937', 1879), _dob('Q999902', 1879)],
        'none',
    ),
    # Subject has no known date → can't evaluate, no fire.
    (
        'missing_src_date',
        _claim_event('Q937', 'P737', 'Q999901'),
        [_dob('Q999901', 1980)],
        'none',
    ),
    # Low-precision (decade) on one side → skipped to avoid false positives.
    (
        'coarse_precision_skipped',
        _claim_event('Q937', 'P737', 'Q999901'),
        [_dob('Q937', 1879, precision=8), _dob('Q999901', 1980)],
        'none',
    ),
    # BC dates: subject in -500, target in -300 (later) → fire.
    (
        'bc_time_travel',
        _claim_event('Q999700', 'P144', 'Q999701'),
        [
            ('Q999700', '-0500-01-01T00:00:00Z', 11),
            ('Q999701', '-0300-01-01T00:00:00Z', 11),
        ],
        'fire',
    ),
    # Author claim where creator is older than work — legit, no fire.
    (
        'author_older_than_work',
        _claim_event('Q999600', 'P50', 'Q999601'),
        [
            ('Q999600', '+1925-01-01T00:00:00Z', 11),
            _dob('Q999601', 1880),
        ],
        'none',
    ),
    # Person (b.1879, d.1955) "influenced by" thing that started in their
    # lifetime (1947) — legit, no fire (DOD widens the subject window).
    (
        'within_lifetime_no_fire',
        _claim_event('Q937', 'P737', 'Q999901'),
        [
            _dob('Q937', 1879),
            ('Q937', '+1955-04-18T00:00:00Z', 11),  # P570 DOD
            _dob('Q999901', 1947),
        ],
        'none',
    ),
    # Person "influenced by" thing that started AFTER their death → fire.
    (
        'posthumous_influence_fires',
        _claim_event('Q937', 'P737', 'Q999901'),
        [
            _dob('Q937', 1879),
            ('Q937', '+1955-04-18T00:00:00Z', 11),  # P570 DOD
            _dob('Q999901', 1980),
        ],
        'fire',
    ),
]


@pytest.mark.parametrize(
    'case_id,event,rows,expected',
    CASES,
    ids=[c[0] for c in CASES],
)
def test_time_travel_edge(case_id, event, rows, expected):
    pool = FakePool(rows)
    result = time_travel_edge(event, db_pool=pool)
    print(f'[{case_id}] result={result}')

    if expected == 'fire':
        assert result is not None, f'{case_id}: expected fire; got None'
    elif expected == 'none':
        assert result is None, f'{case_id}: expected no fire; got {result}'
    elif expected == 'observe':
        return
    else:
        raise ValueError(f'unknown expectation {expected!r} for {case_id}')


def test_non_claim_action_is_skipped():
    pool = FakePool([_dob('Q937', 1879), _dob('Q999901', 1980)])
    event = {'title': 'Q937', 'comment': '/* wbsetlabel-set:1|en */ Einstein'}
    assert time_travel_edge(event, db_pool=pool) is None


def test_missing_db_pool_short_circuits():
    event = _claim_event('Q937', 'P737', 'Q999901')
    assert time_travel_edge(event, db_pool=None) is None


def test_non_qid_title_skipped():
    pool = FakePool([])
    event = _claim_event('Property:P31', 'P737', 'Q999901')
    assert time_travel_edge(event, db_pool=pool) is None

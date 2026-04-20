"""
Tests for indicators.end_before_beginning.

FakePool pattern matches test_labels_less_consistent.py and
test_time_travel_edge.py.
"""
from contextlib import contextmanager

import pytest

from indicators import end_before_beginning


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


def _event(qid, comment):
    return {'title': qid, 'comment': comment}


def _row(prop, year, precision=11, sp='', st=''):
    return (prop, f'+{year:04d}-01-01T00:00:00Z', precision, sp, st)


CASES = [
    # Main dates: DOB 1950, DOD 1940 → end before start → fire.
    (
        'main_dob_after_dod',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: 1950'),
        [_row('P569', 1950), _row('P570', 1940)],
        'fire',
    ),
    # Main dates valid: DOB 1879, DOD 1955 → no fire.
    (
        'main_valid_order',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: 1879'),
        [_row('P569', 1879), _row('P570', 1955)],
        'none',
    ),
    # Qualifier group: P580 start 2020, P582 end 2010 on same P69 stmt → fire.
    (
        'qualifier_group_inverted',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P580]]: 2020'),
        [
            _row('P580', 2020, sp='P69', st='Q100'),
            _row('P582', 2010, sp='P69', st='Q100'),
        ],
        'fire',
    ),
    # Two DIFFERENT qualifier groups, neither individually inverted → no fire.
    # (tests that cross-group comparison is not done.)
    (
        'cross_group_not_compared',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P580]]: 2020'),
        [
            _row('P580', 2000, sp='P69', st='Q100'),
            _row('P582', 2010, sp='P69', st='Q100'),
            _row('P580', 2020, sp='P69', st='Q200'),  # later job's start
            _row('P582', 2025, sp='P69', st='Q200'),
        ],
        'none',
    ),
    # Edit touches a non-start/end prop → skipped.
    (
        'non_date_prop_skipped',
        _event('Q1', '/* wbsetclaim-update:P31[[Q5]] */'),
        [_row('P569', 1950), _row('P570', 1940)],  # would be inverted but we don't check
        'none',
    ),
    # Edit touches a start prop but item has no end dates → no fire.
    (
        'start_only_no_end',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: 1950'),
        [_row('P569', 1950)],
        'none',
    ),
    # Low precision (decade) on DB start row, and edit carries no parseable
    # stream-side date (QID-valued claim) → DB row skipped, no fire.
    (
        'coarse_precision_skipped',
        _event('Q1', '/* wbsetclaim-update:P569[[Q5]] */'),
        [_row('P569', 1950, precision=8), _row('P570', 1940)],
        'none',
    ),
    # Stream-side new P570 "November 1 CE" (year 1) lands before DB P569
    # (year 30); wd_dates has no P570 row yet — must still fire.
    (
        'stream_end_before_db_start',
        _event('Q1', '/* wbsetclaim-create:2||1 */ [[Property:P570]]: November 1 CE'),
        [('P569', '+0030-01-30T00:00:00Z', 11, '', '')],
        'fire',
    ),
    # Stream-side update that FIXES the inversion → no fire. DB has inverted
    # P569=1950, P570=1940; edit sets P570=1960 (now valid).
    (
        'stream_update_fixes_inversion',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P570]]: 1960'),
        [_row('P569', 1950), _row('P570', 1940)],
        'none',
    ),
    # Stream-side BCE date on end → parsed as negative year and fires.
    (
        'stream_bce_end_before_start',
        _event('Q1', '/* wbsetclaim-create:2||1 */ [[Property:P570]]: 30 BCE'),
        [('P569', '+0050-01-01T00:00:00Z', 11, '', '')],
        'fire',
    ),
    # Stream-side unparseable date ("unknown") → falls back to wd_dates only.
    (
        'stream_unparseable_falls_back',
        _event('Q1', '/* wbsetclaim-create:2||1 */ [[Property:P570]]: unknown value'),
        [_row('P569', 1950), _row('P570', 1940)],  # DB alone still inverted
        'fire',
    ),
    # BC dates: start -500, end -600 (earlier) → fire.
    (
        'bc_inversion',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: -500'),
        [
            ('P569', '-0500-01-01T00:00:00Z', 11, '', ''),
            ('P570', '-0600-01-01T00:00:00Z', 11, '', ''),
        ],
        'fire',
    ),
    # Direct claim-on-P569 comment form (with QID value): still detected.
    (
        'direct_property_id_form',
        _event('Q1', '/* wbcreateclaim-create:P569[[Q5]] */'),
        [_row('P569', 1950), _row('P570', 1940)],
        'fire',
    ),
    # Edit touches P571 inception; main group has P571 2020, P576 2000 → fire.
    (
        'inception_after_dissolution',
        _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P571]]: 2020'),
        [_row('P571', 2020), _row('P576', 2000)],
        'fire',
    ),
    # Qualifier inversion ignored when the edit touches unrelated prop.
    # (wrong: touched must be in START_END_PROPS, else we return None.)
    (
        'touched_not_start_end_despite_inversion',
        _event('Q1', '/* wbsetclaim-update:P31[[Q5]] */'),
        [
            _row('P580', 2020, sp='P69', st='Q100'),
            _row('P582', 2010, sp='P69', st='Q100'),
        ],
        'none',
    ),
]


@pytest.mark.parametrize(
    'case_id,event,rows,expected',
    CASES,
    ids=[c[0] for c in CASES],
)
def test_end_before_beginning(case_id, event, rows, expected):
    pool = FakePool(rows)
    result = end_before_beginning(event, db_pool=pool)
    print(f'[{case_id}] result={result}')

    if expected == 'fire':
        assert result is not None, f'{case_id}: expected fire; got None'
    elif expected == 'none':
        assert result is None, f'{case_id}: expected no fire; got {result}'
    elif expected == 'observe':
        return
    else:
        raise ValueError(f'unknown expectation {expected!r} for {case_id}')


def test_missing_db_pool_short_circuits():
    event = _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: 1950')
    assert end_before_beginning(event, db_pool=None) is None


def test_non_qid_title_skipped():
    pool = FakePool([_row('P569', 1950), _row('P570', 1940)])
    event = _event('Property:P31', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: 1950')
    assert end_before_beginning(event, db_pool=pool) is None


def test_fire_result_shape():
    pool = FakePool([_row('P569', 1950), _row('P570', 1940)])
    event = _event('Q1', '/* wbsetclaim-update:2||1 */ [[Property:P569]]: 1950')
    result = end_before_beginning(event, db_pool=pool)
    assert result is not None
    assert result['indicator'] == 'end_before_beginning'
    assert result['qid'] == 'Q1'
    assert 'P569' in result['touched']
    assert len(result['inversions']) == 1
    inv = result['inversions'][0]
    assert inv['scope'] == 'main'
    assert inv['start_year'] == 1950
    assert inv['end_year'] == 1940

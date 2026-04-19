"""
Tests for indicators.bad_description.

Three expectation tiers per case:
  'fire'    -> assert the indicator triggers
  'none'    -> assert it does not trigger
  'observe' -> no assertion; the score is printed for eyeballing

Run with `pytest -v -rP tests/` to see the score printout for every case
(including observe). Passing tests' stdout is captured by default;
`-rP` surfaces it, `-s` disables capture entirely.
"""
import pytest

from indicators import bad_description


def _event(desc):
    return {'title': 'Q1', 'comment': f'/* wbsetdescription-set:1|en */ {desc}'}


CASES = [
    ('proper_adj_no_fire',       'American singer',              'none'),
    ('balanced_paren_no_fire',   'the singer (from Detroit)',    'none'),
    ('article_plus_punct_fires', 'the singer.',                  'fire'),
    ('long_adspeak_fires',
        'The best American deals you will ever see. Discover the magic of our '
        'premium brand today! Book now for exclusive offers and rewards.',
        'fire'),
    ('lowercase_clean_no_fire',  'song by American Idol winner', 'none'),
    ('cosmetic_only_observe',    'American  singer,  composer',  'observe'),
    ('html_only_observe',        'actor &amp; director',         'observe'),
]


@pytest.mark.parametrize(
    'case_id,desc,expected',
    CASES,
    ids=[c[0] for c in CASES],
)
def test_bad_description(case_id, desc, expected):
    result = bad_description(_event(desc))
    score = result['score'] if result else 0.0
    issues = result['issues'] if result else []
    print(f'[{case_id}] score={score} issues={issues}')

    if expected == 'fire':
        assert result is not None, f'{case_id}: expected fire; got score={score}'
    elif expected == 'none':
        assert result is None, (
            f'{case_id}: expected no fire; got score={score} issues={issues}'
        )
    elif expected == 'observe':
        return
    else:
        raise ValueError(f'unknown expectation {expected!r} for {case_id}')

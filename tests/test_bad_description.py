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


def _event(desc, lang='en'):
    return {'title': 'Q1', 'comment': f'/* wbsetdescription-set:1|{lang} */ {desc}'}


# Rules keyed to English wording or English capitalization convention must not
# fire on other languages, and must match whole words only.
LANG_CASES = [
    ('substring_verb_no_fire',   'protected area in Ontario',         'en', 'none'),
    ('real_verb_observe',        'this is a singer',                  'en', 'observe'),
    ('proper_noun_no_fire',      'Premier League football club',      'en', 'none'),
    ('bad_bunny_no_fire',        'Bad Bunny song',                    'en', 'none'),
    ('office_no_fire',           '25th premier of Ontario',           'en', 'none'),
    ('acronym_start_no_fire',    'NASA astronaut and engineer',       'en', 'none'),
    ('wikimedia_start_no_fire',  'Wikimedia disambiguation page',     'en', 'none'),
    ('german_noun_no_fire',      'Gemeinde in Bayern, Deutschland',   'de', 'none'),
    ('french_premier_no_fire',   'Premier ministre de la France',     'fr', 'none'),
    ('adspeak_still_fires',      'the best dentist in Dallas, book now!', 'en', 'fire'),
]


@pytest.mark.parametrize(
    'case_id,desc,lang,expected',
    LANG_CASES,
    ids=[c[0] for c in LANG_CASES],
)
def test_language_and_word_boundaries(case_id, desc, lang, expected):
    result = bad_description(_event(desc, lang))
    score = result['score'] if result else 0.0
    issues = result['issues'] if result else []
    print(f'[{case_id}] score={score} issues={issues}')

    if expected == 'fire':
        assert result is not None, f'{case_id}: expected fire; got score={score}'
    elif expected == 'none':
        assert result is None, (
            f'{case_id}: expected no fire; got score={score} issues={issues}'
        )


# ad_language is checked rule-by-rule rather than through the 2.0 threshold,
# since a single rule can't reach it alone. A low threshold makes the rule's
# own verdict observable.
AD_LANGUAGE_CASES = [
    ('cta_at_start',        'Discover the magic of our brand today!', True),
    ('cta_after_sentence',  'Local firm. Book now for exclusive offers.', True),
    ('seo_acronym',         'SEO consultant in Dallas', True),
    ('jargon_term',         'digital marketing expert', True),
    ('sales_phrase',        'sales manager at a software company', True),
    ('noun_mid_string',     'National Nature Reserve in Wales', False),
    ('noun_at_start',       'Book by John Grisham', False),
    ('noun_plus_of',        'book of hours from 1450', False),
    ('brand_mid_string',    'Best Buy store in Texas', False),
    ('spanish_salts',       'sales de sodio', False),
    ('seo_not_in_surname',  'album by Seo Ji-hye', False),
]


@pytest.mark.parametrize(
    'case_id,desc,expected_ad',
    AD_LANGUAGE_CASES,
    ids=[c[0] for c in AD_LANGUAGE_CASES],
)
def test_ad_language(case_id, desc, expected_ad):
    result = bad_description(_event(desc), threshold=0.5)
    fired = bool(result) and any(i['name'] == 'ad_language' for i in result['issues'])
    assert fired == expected_ad, (
        f'{case_id}: ad_language fired={fired}, expected {expected_ad}; '
        f'issues={result["issues"] if result else []}'
    )


# Real comments where Wikibase appended the editor's own summary after the
# description value; only the value should be scored.
BOT_SUMMARY_CASES = [
    ('nabbot_tr',
     '/* wbsetdescription-add:1|tr */ böcek türü, '
     '[[Special:MyLanguage/Wikidata:Bots|Bot]], '
     '[[Wikidata:Requests for permissions/Bot/Nabbot 2|Task 2]]: '
     'Turkish description translated from English using dictionary.',
     'böcek türü'),
    ('cewbot_de',
     '/* wbsetdescription-set:1|de */ wissenschaftlicher Artikel, 15. August 1991, '
     '[[User:Cewbot/log/20210701/configuration|Modify PubMed ID]]: '
     '1855182 citation data from NCBI, Europe PMC and CrossRef',
     'wissenschaftlicher Artikel, 15. August 1991'),
]


@pytest.mark.parametrize(
    'case_id,comment,expected_value',
    BOT_SUMMARY_CASES,
    ids=[c[0] for c in BOT_SUMMARY_CASES],
)
def test_editor_summary_stripped(case_id, comment, expected_value):
    from utils import parse_edit_comment

    parsed = parse_edit_comment(comment)
    assert parsed['details']['value_part'] == expected_value
    result = bad_description({'title': 'Q1', 'comment': comment})
    assert result is None, f'{case_id}: expected no fire; got {result}'


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

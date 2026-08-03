#!/usr/bin/env python3
"""
Collection of functions (indicators) to detect potentially problematic changes
in Wikidata events. Each function should accept a processed event dictionary
and optionally other dependencies (like logger, db_pool).
They should return None if the indicator is not triggered, or a dictionary
describing the triggered flag if it is.
"""

import logging
import re
import string
from collections import Counter

FIRST_CENTURY_DATE = re.compile(r'\b(\d{1,2})\s+CE\b')

# --- Helper Functions ---

from utils import parse_edit_comment
from wd_constants import starts as WD_STARTS, ends as WD_ENDS

START_PROPS = frozenset(WD_STARTS.keys())
END_PROPS = frozenset(WD_ENDS.keys())
START_END_PROPS = START_PROPS | END_PROPS

PROPERTY_LINK_RE = re.compile(r'\[\[Property:(P\d+)\]\]', re.IGNORECASE)

# --- Indicator Functions ---

## Tier 1 indicators - only event data needed

# description indicators needed: see ideas in descgusting.py

# where to put indicators needing full item data, e.g. labels_less_consistent?

def large_removal(processed_event, logger=None, db_pool=None, removal_threshold_bytes=2500):
    """
    Checks if an edit resulted in a large removal of content (bytes).

    Args:
        processed_event (dict): The structured event data from the stream.
        logger (logging.Logger, optional): Logger instance for internal logging.
        db_pool (psycopg.pool.ConnectionPool, optional): DB pool if needed (not used here).
        removal_threshold_bytes (int): Minimum bytes removed to trigger. Defaults to 1000.

    Returns:
        dict or None: Dictionary with indicator details if triggered, else None.
    """
    length_data = processed_event.get('length')
    indicator_name = "large_removal"

    if not length_data:
        # Cannot determine length change
        return None

    old_len = length_data.get('old')
    new_len = length_data.get('new')

    # Check if lengths are valid integers
    if not isinstance(old_len, int) or not isinstance(new_len, int):
        if logger:
            # Log only if logger was passed
            logger.debug(f"{indicator_name}: Invalid or missing length data in event for {processed_event.get('title')}")
        return None

    bytes_removed = old_len - new_len

    if bytes_removed >= removal_threshold_bytes:
        if logger:
            logger.info(f"{indicator_name} triggered for {processed_event.get('title')} (RC_ID: {processed_event.get('rc_id')}): {bytes_removed} bytes removed.")

        # Return structured information about the flag
        return {
            "indicator": indicator_name,
            "threshold": removal_threshold_bytes,
            "bytes_removed": bytes_removed,
            "details": f"Removed {bytes_removed} bytes (threshold: {removal_threshold_bytes})"
        }
    else:
        # Removal was below threshold
        return None

def self_reference_added(processed_event, logger=None, db_pool=None):
    # TODO determine if this should be self_reference_added_t1 or something,
    # and then have a t3 version if the comment indicates that the item should be checked
    indicator_name = "self_reference_added"
    title = processed_event['title']
    parsed_comment = parse_edit_comment(processed_event['comment'])
    details = parsed_comment.get('details', {})
    pid = parsed_comment.get('property_id', {})
    if 'claim_value_qid' in details and details['claim_value_qid'] == title:
        return {
            "indicator": indicator_name,
            "details": f"Self-reference added: {title} {pid} {title}"
        }
    else:
        return None

# TODO what about a more general "date changed"?  what about a more specific "date changed to" (e.g. 2001-9-11)?  how should these be organized?

def life_dates_changed(processed_event, logger=None, db_pool=None):
    """
    Checks if an edit changed dates of birth (P569), death (P570), or other life dates
    """
    # TODO figure out how to approach other beginnings and endings; it's not all people, people!
    indicator_name = "life_dates_changed"
    date_props = ("P569", "P570")
    title = processed_event['title']
    parsed_comment = parse_edit_comment(processed_event['comment'])
    pid = parsed_comment.get('property_id', {})
    if pid in date_props:
        # logger.info("well, that's interesting")
        return {
            "indicator": indicator_name,
            "details": f"Property {pid} changed on {title}"
        }
    else:
        return None

BAD_DESC_ARTICLES = ('a ', 'an ', 'the ')
# Calls to action. These are adspeak only as commands, which in practice means
# opening a sentence — mid-description they are ordinary nouns ('National Nature
# Reserve in Wales', 'Book of Mormon character').
BAD_DESC_AD_IMPERATIVES = ('discover', 'enjoy', 'indulge', 'book', 'reserve',
                           'buy', 'get', 'hire')
# A preposition right after the word marks it as a noun ('book by X',
# 'reserve in Kenya') rather than a command ('Book now', 'Discover the magic').
AD_NOUN_FOLLOWERS = ('by', 'of', 'in', 'from', 'at', 'on', 'about')
# Promotional occupations/jargon, matched anywhere as whole words.
BAD_DESC_AD_TERMS = ('marketing', 'marketer', 'consultant', 'influencer',
                     'content creator')
# Bare 'sales' collides with ordinary vocabulary in other languages (Spanish
# 'sales' = salts, French = dirty), so require the promotional phrasing.
BAD_DESC_AD_PHRASES = ('sales manager', 'sales representative', 'sales rep',
                       'sales coach', 'sales expert', 'sales funnel',
                       'sales training', 'sales professional')
BAD_DESC_SUBJECTIVE = ('best', 'worst', 'good', 'bad', 'terrible', 'horrible', 'beautiful', 'ugly', 'greatest', 'leading', 'premier', 'premium', 'finest')
BAD_DESC_VERBS = ('is', 'are', 'was', 'were')
# First-word proper adjectives that legitimately start English descriptions.
# Extend as needed; keep alphabetized for easy editing.
PROPER_ADJECTIVES = frozenset({
    'American', 'Argentine', 'Argentinian', 'Australian', 'Brazilian',
    'British', 'Canadian', 'Chinese', 'Dutch', 'Egyptian', 'English',
    'French', 'German', 'Greek', 'Indian', 'Irish', 'Italian',
    'Japanese', 'Korean', 'Mexican', 'Nigerian', 'Norwegian', 'Polish',
    'Russian', 'Scottish', 'Spanish', 'Swedish', 'Turkish', 'Welsh',
})
# Proper nouns that routinely open an otherwise well-formed description.
PROPER_NOUN_STARTERS = frozenset({
    'Commons', 'Wikibooks', 'Wikidata', 'Wikimedia', 'Wikinews', 'Wikipedia',
    'Wikiquote', 'Wikisource', 'Wikivoyage', 'Wiktionary',
})
# Languages that capitalize every noun, so a capitalized first word carries no
# signal. Mostly German and its relatives.
NOUN_CAPITALIZING_LANGS = frozenset({
    'als', 'bar', 'de', 'de-at', 'de-ch', 'gsw', 'ksh', 'lb', 'nds', 'nds-nl',
    'pdc', 'pfl', 'stq', 'vmf',
})


def _word_pattern(words):
    """Whole-word alternation, so 'are' no longer matches inside 'area'."""
    return re.compile(r'\b(?:%s)\b' % '|'.join(re.escape(w) for w in words),
                      re.IGNORECASE)


BAD_DESC_VERB_RE = _word_pattern(BAD_DESC_VERBS)
BAD_DESC_SUBJECTIVE_RE = _word_pattern(BAD_DESC_SUBJECTIVE)
BAD_DESC_AD_TERM_RE = _word_pattern(BAD_DESC_AD_TERMS + BAD_DESC_AD_PHRASES)
# Acronyms stay case-sensitive so 'Seoul' and the surname 'Seo' don't match.
BAD_DESC_AD_ACRONYM_RE = re.compile(r'\b(?:SEO|AEO)\b')
# An imperative at the start of the description or of a later sentence, not
# followed by a preposition.
BAD_DESC_AD_IMPERATIVE_RE = re.compile(
    r'(?:^|[.!?]\s+)(?:%s)\s+(?!(?:%s)\b)' % (
        '|'.join(BAD_DESC_AD_IMPERATIVES),
        '|'.join(AD_NOUN_FOLLOWERS),
    ),
    re.IGNORECASE,
)
# 'premier' names offices and competitions far more often than it advertises.
PREMIER_LEGIT_RE = re.compile(r'\bpremier\s+(?:league|of|minister)\b', re.IGNORECASE)


def _first_word(desc):
    word = desc.split(' ', 1)[0] if desc else ''
    return word.strip(string.punctuation)


def _proper_start(desc):
    """True when the first word is capitalized for a reason other than style:
    a proper adjective, a known proper noun, or an acronym like 'NASA'."""
    word = _first_word(desc)
    return (word in PROPER_ADJECTIVES
            or word in PROPER_NOUN_STARTERS
            or (len(word) > 1 and word.isupper()))


def _ad_language_score(desc):
    """Marketing language: a call to action opening a sentence, promotional
    jargon, or an SEO-style acronym."""
    if (BAD_DESC_AD_IMPERATIVE_RE.search(desc)
            or BAD_DESC_AD_TERM_RE.search(desc)
            or BAD_DESC_AD_ACRONYM_RE.search(desc)):
        return 1.0
    return 0.0


def _subjective_score(desc):
    """Subjective wording, ignoring capitalized hits — 'Bad Bunny', 'Premier
    League' and 'Greatest Hits' are names, while genuine puffery ('the best
    dentist') is written lowercase mid-description."""
    hits = {m.group(0) for m in BAD_DESC_SUBJECTIVE_RE.finditer(desc)
            if m.group(0)[0].islower()}
    if 'premier' in hits and PREMIER_LEGIT_RE.search(desc):
        hits.discard('premier')
    return 1.0 if hits else 0.0

def _balanced_trailing_paren(desc):
    return desc.endswith(')') and desc.count('(') == desc.count(')')

def _len_score(desc):
    return max(0.0, (len(desc) - 42) * 0.02)

# Each rule: score(desc) -> float (0 = no fire), optional suppress_if(desc) -> bool.
# Weights are independent; total >= threshold triggers the indicator.
# Optional "langs" limits a rule to those language codes; "skip_langs" excludes
# them. Both exist because some rules encode English-specific conventions and
# would otherwise fire on ordinary words in other languages.
BAD_DESC_RULES = [
    {"name": "too_long",              "score": _len_score},
    {"name": "starts_capitalized",    "score": lambda d: 1.0 if d and d[0].isupper() else 0.0,
                                      "suppress_if": _proper_start,
                                      "skip_langs": NOUN_CAPITALIZING_LANGS},
    {"name": "ends_with_punctuation", "score": lambda d: 1.0 if d and d[-1] in string.punctuation else 0.0,
                                      "suppress_if": _balanced_trailing_paren},
    {"name": "starts_with_article",   "score": lambda d: 1.0 if d.lower().startswith(BAD_DESC_ARTICLES) else 0.0,
                                      "langs": frozenset({'en'})},
    {"name": "ad_language",           "score": _ad_language_score},
    {"name": "subjective",            "score": _subjective_score,
                                      "langs": frozenset({'en'})},
    {"name": "verb",                  "score": lambda d: 1.0 if BAD_DESC_VERB_RE.search(d) else 0.0,
                                      "langs": frozenset({'en'})},
    {"name": "contains_trademark",    "score": lambda d: 1.0 if ('\u00ae' in d or '\u2122' in d) else 0.0},
    {"name": "double_space",          "score": lambda d: 0.5 if '  ' in d else 0.0},
    {"name": "space_before_comma",    "score": lambda d: 0.5 if ' ,' in d else 0.0},
    {"name": "html_escape",           "score": lambda d: 1.0 if ('&amp;' in d or '&lt;' in d or '&gt;' in d or '&quot;' in d) else 0.0},
]
BAD_DESC_THRESHOLD = 2.0

def bad_description(processed_event, logger=None, db_pool=None, threshold=BAD_DESC_THRESHOLD):
    """
    Flags description edits whose weighted score across BAD_DESC_RULES reaches
    `threshold`. Each rule contributes a float; some have suppress_if exceptions
    and some apply only to certain languages.
    """
    indicator_name = "bad_description"
    parsed_comment = parse_edit_comment(processed_event.get('comment', ''))
    if not parsed_comment.get('action', '').startswith('wbsetdescription'):
        return None
    details = parsed_comment.get('details') or {}
    # value_part excludes any bot/editor summary Wikibase appended after the
    # description; fall back for comments where no split was attempted.
    desc = details.get('value_part') or details.get('manual_comment_part', '')
    if not desc:
        return None

    lang = parsed_comment.get('language')
    issues = []
    total = 0.0
    for rule in BAD_DESC_RULES:
        only_langs = rule.get('langs')
        if only_langs and lang not in only_langs:
            continue
        if lang in rule.get('skip_langs', ()):
            continue
        suppress = rule.get('suppress_if')
        if suppress and suppress(desc):
            continue
        s = rule['score'](desc)
        if s > 0:
            issues.append({"name": rule['name'], "score": round(s, 2)})
            total += s

    if total < threshold:
        return None

    title = processed_event.get('title', '?')
    breakdown = ', '.join(f"{i['name']}={i['score']}" for i in issues)
    return {
        "indicator": indicator_name,
        "lang": parsed_comment.get('language'),
        "score": round(total, 2),
        "threshold": threshold,
        "issues": issues,
        "details": f"{title}: score={round(total, 2)} ({breakdown})",
    }

def constraint_check_candidate(processed_event, logger=None, db_pool=None):
    """
    Measurement-only Tier 1 indicator: returns a result on every edit where
    a Wikidata wbcheckconstraints API call would be worth making — i.e., a
    claim create/update on a Q-item. Used to size API call volume before
    committing to a Tier 3 constraint-violation indicator.

    Excludes claim removals (rare violation introducers) and non-Q pages
    (Property:/Lexeme: have separate constraint surfaces). References
    CLAIM_CREATE_OR_UPDATE defined in the Tier 2 section below — resolved
    at call time, so forward order is fine.
    """
    indicator_name = "constraint_check_candidate"
    qid = processed_event.get('title')
    if not qid or not qid.startswith('Q'):
        return None
    parsed = parse_edit_comment(processed_event.get('comment', ''))
    action = parsed.get('action')
    if action not in CLAIM_CREATE_OR_UPDATE:
        return None
    pid = parsed.get('property_id')
    has_qid_value = bool((parsed.get('details') or {}).get('claim_value_qid'))
    return {
        "indicator": indicator_name,
        "qid": qid,
        "property_id": pid,
        "action": action,
        "has_qid_value": has_qid_value,
        "details": f"{qid} {action} {pid or '?'}",
    }


def dob_first_century(processed_event, logger=None, db_pool=None):
    """
    Flags edits that set date of birth (P569) to a first-century value (years 1-99 CE).
    These are almost always mistakes — someone entering a day or month number as the year.
    """
    indicator_name = "dob_first_century"
    parsed_comment = parse_edit_comment(processed_event.get('comment', ''))
    trailing = parsed_comment.get('details', {}).get('manual_comment_part', '')
    # property_id may be None when the value isn't a QID link (e.g. dates),
    # so also check for P569 directly in the trailing text
    pid = parsed_comment.get('property_id')
    if pid != 'P569' and '[[Property:P569]]' not in trailing:
        return None
    m = FIRST_CENTURY_DATE.search(trailing)
    if m:
        year = int(m.group(1))
        title = processed_event.get('title', '?')
        return {
            "indicator": indicator_name,
            "details": f"P569 on {title} set to year {year} CE"
        }
    return None

## Tier 2 indicators - tier 1 results and/or local DB queries needed

# Properties where X --[P]--> Y implies Y should predate X.
# A violation — target post-dates subject — is the "time travel" signal.
CAUSAL_BACKWARD = frozenset({
    'P737',   # influenced by
    'P941',   # inspired by
    'P144',   # based on
    'P5191',  # derived from
    'P5059',  # modified version of
    'P629',   # edition or translation of
    'P9810',  # remix of
    'P1877',  # after a work by
    'P155',   # follows
    'P1365',  # replaces
    'P22',    # father
    'P25',    # mother
    'P184',   # doctoral advisor
    'P1066',  # student of
    'P170',   # creator
    'P50',    # author
    'P86',    # composer
    'P87',    # librettist
    'P84',    # architect
    'P110',   # illustrator
    'P178',   # developer
    'P943',   # programmer
    'P287',   # designed by
    'P176',   # manufacturer
    'P57',    # director
    'P58',    # screenwriter
    'P162',   # producer
    'P272',   # production company
    'P61',    # discoverer or inventor
    'P112',   # founded by
    'P138',   # named after
    'P828',   # has cause
    'P1478',  # has immediate cause
    'P1479',  # has contributing factor
})

# Earliest relevant dates for an entity: DOB, inception, publication, etc.
# Used as the target's "first existed" bound.
TIME_TRAVEL_START_PROPS = frozenset({
    'P569',   # date of birth
    'P571',   # inception
    'P575',   # time of discovery or invention
    'P577',   # publication date
    'P580',   # start time
    'P585',   # point in time
    'P606',   # first flight
    'P729',   # service entry
    'P1191',  # first performance
    'P1249',  # time of earliest written record
    'P1317',  # floruit
    'P1319',  # earliest date
    'P1619',  # date of official opening
    'P2031',  # work period (start)
    'P523',   # temporal range start
})

# End/latest dates: DOD, dissolution, discontinuation, etc. Combined with the
# start props, this gives the subject's "last possible moment of influence".
TIME_TRAVEL_END_PROPS = frozenset({
    'P570',   # date of death
    'P576',   # dissolved, abolished or demolished
    'P582',   # end time
    'P730',   # service retirement
    'P1326',  # latest date
    'P2032',  # work period (end)
    'P2669',  # discontinued date
    'P3999',  # date of official closure
    'P524',   # temporal range end
})

TIME_TRAVEL_ALL_PROPS = TIME_TRAVEL_START_PROPS | TIME_TRAVEL_END_PROPS

CLAIM_CREATE_OR_UPDATE = frozenset({
    'wbcreateclaim-create', 'wbsetclaim-create', 'wbsetclaim-update',
})

# Wikidata time_value format: '+1952-03-11T00:00:00Z' or '-0044-03-15T00:00:00Z'
WD_YEAR_RE = re.compile(r'^([+-])(\d+)-')


def _parse_wd_year(time_value):
    if not time_value:
        return None
    m = WD_YEAR_RE.match(time_value)
    if not m:
        return None
    sign = -1 if m.group(1) == '-' else 1
    return sign * int(m.group(2))


def _years(rows, min_precision=9):
    """rows: iterable of (time_value, precision). Skips precision < min
    (decade/century) since those are too fuzzy for a year comparison."""
    return [
        y for tv, prec in rows
        if prec is not None and prec >= min_precision
        and (y := _parse_wd_year(tv)) is not None
    ]


def time_travel_edge(processed_event, logger=None, db_pool=None):
    """
    Flags a claim create/update where a 'backward-causal' edge (P737 influenced
    by, P170 creator, P144 based on, ...) points to a target whose earliest
    known start date is AFTER the subject's — i.e. the subject is claimed to
    be influenced/created/etc. by something that didn't yet exist.
    """
    indicator_name = "time_travel_edge"
    if not db_pool:
        if logger:
            logger.debug(f"{indicator_name}: db_pool not provided")
        return None

    src_qid = processed_event.get('title')
    if not src_qid or not src_qid.startswith('Q'):
        return None

    parsed = parse_edit_comment(processed_event.get('comment', ''))
    if parsed.get('action') not in CLAIM_CREATE_OR_UPDATE:
        return None
    pid = parsed.get('property_id')
    if pid not in CAUSAL_BACKWARD:
        return None
    dst_qid = (parsed.get('details') or {}).get('claim_value_qid')
    if not dst_qid:
        return None

    try:
        with db_pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT qid, time_value, precision
                  FROM wd_dates
                 WHERE qid = ANY(%s)
                   AND property = ANY(%s)
                   AND source_property = ''
                """,
                ([src_qid, dst_qid], list(TIME_TRAVEL_ALL_PROPS)),
            )
            rows = cur.fetchall()
    except Exception as e:
        if logger:
            logger.error(
                f"{indicator_name} DB error for {src_qid}->{dst_qid}: {e}",
                exc_info=True,
            )
        return None

    # Subject upper bound: latest known date (DOD / end / etc., falling back
    # to start dates when no end is recorded). Target lower bound: earliest
    # known date. Using min over both start and end props on the target is
    # safe — including end dates only widens its window backwards, never
    # forwards, so it can only reduce false positives.
    src_years = _years((tv, prec) for q, tv, prec in rows if q == src_qid)
    dst_years = _years((tv, prec) for q, tv, prec in rows if q == dst_qid)

    if not src_years or not dst_years:
        return None
    src_upper = max(src_years)
    dst_lower = min(dst_years)
    if dst_lower <= src_upper:
        return None

    if logger:
        logger.info(
            f"{indicator_name}: {src_qid} {pid} {dst_qid} "
            f"(src_upper={src_upper}, dst_lower={dst_lower})"
        )
    return {
        "indicator": indicator_name,
        "src": src_qid,
        "dst": dst_qid,
        "property_id": pid,
        "src_upper_year": src_upper,
        "dst_lower_year": dst_lower,
        "details": (
            f"{src_qid} {pid} {dst_qid}: target first-seen year {dst_lower} "
            f"is after subject last-seen year {src_upper}"
        ),
    }


def _touched_properties(parsed_comment):
    """Props mentioned by the edit: main claim prop + any [[Property:Pxx]]
    links in the trailing manual comment (which is where qualifier-prop edits
    and date-value claims surface Pxx)."""
    touched = set()
    pid = parsed_comment.get('property_id')
    if pid:
        touched.add(pid)
    trailing = (parsed_comment.get('details') or {}).get('manual_comment_part', '')
    for m in PROPERTY_LINK_RE.finditer(trailing):
        touched.add(m.group(1).upper())
    return touched


# Matches [[Property:Pxx]]: <value-text> — lazy to next [[Property: or end.
PROP_VALUE_RE = re.compile(
    r'\[\[Property:(P\d+)\]\]:\s*(.*?)(?=\[\[Property:|\Z)',
    re.IGNORECASE | re.DOTALL,
)
BCE_RE = re.compile(r'\b(?:BCE|BC|B\.C\.E?\.?)\b', re.IGNORECASE)
# Standalone 1-4 digit integer (not part of a longer number).
YEAR_TOKEN_RE = re.compile(r'(?<!\d)(\d{1,4})(?!\d)')


def _parse_year_from_text(text):
    """Best-effort year from a Wikidata-rendered date string like
    'November 1 CE', '14 March 1879', '30 BCE'. Uses the largest 1-4 digit
    integer in the text, negated if BCE/BC is mentioned."""
    if not text:
        return None
    text = text.strip()
    if not text or text.startswith('[['):  # QID value, not a date
        return None
    numbers = [int(n) for n in YEAR_TOKEN_RE.findall(text)]
    if not numbers:
        return None
    year = max(numbers)
    return -year if BCE_RE.search(text) else year


def _stream_start_end_years(parsed_comment):
    """{prop_id: year} for each [[Property:Pxx]]: <date-text> in trailing,
    keeping only start/end props with parseable years."""
    trailing = (parsed_comment.get('details') or {}).get('manual_comment_part', '')
    if not trailing:
        return {}
    out = {}
    for m in PROP_VALUE_RE.finditer(trailing):
        pid = m.group(1).upper()
        if pid not in START_END_PROPS:
            continue
        year = _parse_year_from_text(m.group(2))
        if year is not None:
            out[pid] = year
    return out


def end_before_beginning(processed_event, logger=None, db_pool=None):
    """
    Flags claim edits on start/end date properties where the item's current
    wd_dates state contains an end that precedes a start within the same
    statement-group (main dates share one group; qualifier dates group by
    (source_property, source_target)).

    Compares at year precision. Ignores rows with precision < 9 (decade or
    coarser) to avoid spurious inversions from fuzzy dates.

    To bridge the wd_dates snapshot lag, any [[Property:Pxx]]: <date-text>
    in the trailing comment is parsed and treated as authoritative for that
    prop in the main group — so an edit that introduces an inversion against
    an existing stored date will fire on the same event, not next sync.
    """
    indicator_name = "end_before_beginning"
    if not db_pool:
        if logger:
            logger.debug(f"{indicator_name}: db_pool not provided")
        return None

    qid = processed_event.get('title')
    if not qid or not qid.startswith('Q'):
        return None

    parsed = parse_edit_comment(processed_event.get('comment', ''))
    if parsed.get('action') not in CLAIM_CREATE_OR_UPDATE:
        return None

    touched = _touched_properties(parsed)
    touched_start_end = touched & START_END_PROPS
    if not touched_start_end:
        return None

    stream_years = _stream_start_end_years(parsed)

    try:
        with db_pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT property, time_value, precision,
                       source_property, source_target
                  FROM wd_dates
                 WHERE qid = %s
                   AND property = ANY(%s)
                """,
                (qid, list(START_END_PROPS)),
            )
            rows = cur.fetchall()
    except Exception as e:
        if logger:
            logger.error(f"{indicator_name} DB error for {qid}: {e}", exc_info=True)
        return None
    if not rows and not stream_years:
        return None

    # Group by (source_property, source_target); each entry: (prop, year).
    groups = {}
    for prop, tv, prec, sp, st in rows:
        if prec is None or prec < 9:
            continue
        year = _parse_wd_year(tv)
        if year is None:
            continue
        groups.setdefault((sp, st), []).append((prop, year))

    # Stream values supersede wd_dates for matching props in the main group.
    if stream_years:
        main = [(p, y) for (p, y) in groups.get(('', ''), []) if p not in stream_years]
        main.extend(stream_years.items())
        groups[('', '')] = main

    inversions = []
    for (sp, st), entries in groups.items():
        start_years = [y for p, y in entries if p in START_PROPS]
        end_years = [y for p, y in entries if p in END_PROPS]
        if not start_years or not end_years:
            continue
        max_start = max(start_years)
        min_end = min(end_years)
        if min_end < max_start:
            inversions.append({
                'scope': 'main' if sp == '' else f'{sp}->{st}',
                'start_year': max_start,
                'end_year': min_end,
            })

    if not inversions:
        return None

    if logger:
        logger.info(
            f"{indicator_name}: {qid} touched {sorted(touched_start_end)}, "
            f"{len(inversions)} inverted pair(s)"
        )
    return {
        "indicator": indicator_name,
        "qid": qid,
        "touched": sorted(touched_start_end),
        "inversions": inversions,
        "details": (
            f"{qid}: " + "; ".join(
                f"{inv['scope']} end {inv['end_year']} < start {inv['start_year']}"
                for inv in inversions
            )
        ),
    }


PROP_QID_TRAILING = re.compile(r'\[\[Property:(P\d+)\]\]:\s*\[\[(Q\d+)\]\]', re.IGNORECASE)

def high_wp_count_removed(processed_event, logger=None, db_pool=None, threshold=2):
    """
    Flags claim removals where the removed src→dst edge has a high Wikipedia
    co-occurrence count in wp_links. Default threshold=2 (present in ≥2 wikis).
    """
    indicator_name = "high_wp_count_removed"
    if not db_pool:
        if logger:
            logger.debug(f"{indicator_name}: db_pool not provided")
        return None

    src_qid = processed_event.get('title')
    if not src_qid or not src_qid.startswith('Q'):
        return None

    comment = processed_event.get('comment', '')
    parsed = parse_edit_comment(comment)
    if not parsed.get('action', '').startswith('wbremoveclaims'):
        return None

    dst_qid = parsed.get('details', {}).get('claim_value_qid')
    pid = parsed.get('property_id')
    if not dst_qid:
        # remove-claim comments carry the target as trailing "[[Property:Pxx]]: [[Qyy]]";
        # parse_edit_comment's remove branch doesn't capture it, so do it here.
        m = PROP_QID_TRAILING.search(comment)
        if m:
            pid = pid or m.group(1).upper()
            dst_qid = m.group(2).upper()
    if not dst_qid:
        return None

    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT wp_count FROM wp_links WHERE src = %s AND dst = %s",
                    (src_qid, dst_qid),
                )
                row = cur.fetchone()
    except Exception as e:
        if logger:
            logger.error(
                f"{indicator_name} DB error for {src_qid}->{dst_qid}: {e}",
                exc_info=True,
            )
        return None

    if not row or row[0] is None or row[0] < threshold:
        return None

    wp_count = row[0]
    if logger:
        logger.info(
            f"{indicator_name}: {src_qid} {pid} {dst_qid} (wp_count={wp_count})"
        )
    return {
        "indicator": indicator_name,
        "src": src_qid,
        "dst": dst_qid,
        "property_id": pid,
        "wp_count": wp_count,
        "threshold": threshold,
        "details": f"Removed {src_qid} {pid} {dst_qid} with wp_count={wp_count}",
    }

def labels_less_consistent(processed_event, logger=None, db_pool=None, consensus_threshold=3):
    """
    Flags label edits where the language's pre-edit label matched a cross-language
    consensus but the new label diverges from it.

    Triggers iff:
      - ≥ consensus_threshold OTHER languages share the same normalized label
        (stripped, casefolded);
      - the DB's current (pre-edit) row for this (qid, lang) matches that consensus;
      - the new label in the edit does not.

    The pre-edit match requirement keeps legitimate transliteration edits (which
    never matched the consensus to begin with) from triggering.
    """
    indicator_name = "labels_less_consistent"
    if not db_pool:
        if logger:
            logger.debug(f"{indicator_name}: db_pool not provided")
        return None

    qid = processed_event.get('title')
    if not qid or not qid.startswith('Q'):
        return None

    parsed = parse_edit_comment(processed_event.get('comment', ''))
    if parsed.get('action') != 'wbsetlabel-set':
        return None

    lang = parsed.get('language')
    label_details = parsed.get('details') or {}
    new_label = label_details.get('value_part') or label_details.get('manual_comment_part', '')
    if not lang or not new_label:
        return None
    new_norm = new_label.strip().casefold()

    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT lang, label FROM wd_labels WHERE qid = %s",
                    (qid,),
                )
                rows = cur.fetchall()
    except Exception as e:
        if logger:
            logger.error(f"{indicator_name} DB error for {qid}: {e}", exc_info=True)
        return None
    if not rows:
        return None

    counts = Counter()
    originals = {}
    old_label = None
    for row_lang, row_label in rows:
        if not row_label:
            continue
        if row_lang == lang:
            old_label = row_label
            continue
        norm = row_label.strip().casefold()
        counts[norm] += 1
        originals.setdefault(norm, row_label.strip())
    if not counts:
        return None

    consensus_norm, consensus_n = counts.most_common(1)[0]
    if consensus_n < consensus_threshold:
        return None
    if old_label is None or old_label.strip().casefold() != consensus_norm:
        return None
    if new_norm == consensus_norm:
        return None

    consensus_display = originals.get(consensus_norm, consensus_norm)
    if logger:
        logger.info(
            f"{indicator_name}: {qid}[{lang}] {old_label!r} -> {new_label!r}; "
            f"consensus {consensus_display!r} in {consensus_n} other langs"
        )
    return {
        "indicator": indicator_name,
        "qid": qid,
        "lang": lang,
        "old_label": old_label,
        "new_label": new_label,
        "consensus_label": consensus_display,
        "consensus_count": consensus_n,
        "details": (
            f"{qid}[{lang}]: {old_label!r} -> {new_label!r}; "
            f"{consensus_n} other langs agree on {consensus_display!r}"
        ),
    }

## Tier 3 indicators - web API calls needed

# What goes here again?  Can I classify some of my live_monitor.py indicators here?


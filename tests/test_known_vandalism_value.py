"""
Tests for the known_vandalism_value indicator: claim create/update whose value
is one of the QIDs vandals reuse (VANDALISM_MAGNET_QIDS).
"""
from indicators import known_vandalism_value


def _event(comment, title='Q42'):
    return {'title': title, 'comment': comment}


def test_inline_claim_value_fires():
    result = known_vandalism_value(_event('/* wbcreateclaim-create:P22[[Q615]] */'))
    assert result is not None
    assert result['property_id'] == 'P22'
    assert result['value_qid'] == 'Q615'
    assert result['value_label'] == 'Lionel Messi'


def test_trailing_property_value_form_fires():
    # /* wbsetclaim-create:2||1 */ [[Property:P106]]: [[Q488111]]
    result = known_vandalism_value(
        _event('/* wbsetclaim-create:2||1 */ [[Property:P106]]: [[Q488111]]'))
    assert result is not None
    assert result['property_id'] == 'P106'
    assert result['value_qid'] == 'Q488111'


def test_update_to_magnet_value_fires():
    result = known_vandalism_value(_event('/* wbsetclaim-update:P26[[Q11571]] */'))
    assert result is not None
    assert result['value_qid'] == 'Q11571'


def test_lowercase_qid_fires():
    # parse_edit_comment normalises the QID case.
    result = known_vandalism_value(_event('/* wbcreateclaim-create:P31[[q134227481]] */'))
    assert result is not None
    assert result['value_qid'] == 'Q134227481'


def test_ordinary_value_does_not_fire():
    assert known_vandalism_value(_event('/* wbcreateclaim-create:P31[[Q5]] */')) is None


def test_claim_removal_does_not_fire():
    # Removing the value is the fix, not the problem — and the comment carries
    # no value anyway.
    assert known_vandalism_value(_event('/* wbremoveclaims-remove:1|P22 */')) is None


def test_label_edit_does_not_fire():
    assert known_vandalism_value(_event('/* wbsetlabel-set:1|en */ Q615')) is None


def test_edit_on_the_magnet_item_itself_still_checks_the_value():
    # Editing Q615 to point at Q11571 is as suspect as the reverse.
    result = known_vandalism_value(
        _event('/* wbcreateclaim-create:P22[[Q11571]] */', title='Q615'))
    assert result is not None
    assert result['value_qid'] == 'Q11571'

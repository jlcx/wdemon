"""
Tests for recheck's self_reference_added claim check and the indicator's
structured property_id field.
"""
from indicators import self_reference_added
from recheck import _self_ref_gone, _self_ref_property


def _row(details, qid='Q130601266'):
    return {'id': 1, 'item_qid': qid, 'indicator_name': 'self_reference_added',
            'indicator_details': details}


def _entity_with_claim(pid, target_qid):
    return {'claims': {pid: [
        {'mainsnak': {'snaktype': 'value',
                      'datavalue': {'type': 'wikibase-entityid',
                                    'value': {'entity-type': 'item',
                                              'id': target_qid}}}},
    ]}}


def test_indicator_stores_property_id():
    event = {'title': 'Q42',
             'comment': '/* wbsetclaim-update:P361[[Q42]] */'}
    result = self_reference_added(event)
    assert result is not None
    assert result['property_id'] == 'P361'


def test_property_from_structured_field():
    row = _row({'property_id': 'P734', 'details': 'whatever'})
    assert _self_ref_property(row) == 'P734'


def test_property_parsed_from_old_details_string():
    # Pre-existing rows only embed the property in the details string.
    row = _row({'details': 'Self-reference added: Q130601266 P734 Q130601266'})
    assert _self_ref_property(row) == 'P734'


def test_self_ref_still_present():
    row = _row({'property_id': 'P734', 'details': ''})
    entity = _entity_with_claim('P734', 'Q130601266')
    assert _self_ref_gone(row, entity) is False


def test_self_ref_value_changed():
    row = _row({'property_id': 'P734', 'details': ''})
    entity = _entity_with_claim('P734', 'Q845104')
    assert _self_ref_gone(row, entity) is True


def test_self_ref_claim_removed():
    row = _row({'property_id': 'P734', 'details': ''})
    assert _self_ref_gone(row, {'claims': {}}) is True


def test_self_ref_multiple_statements_one_still_bad():
    # A second statement on the property still self-references: not corrected.
    row = _row({'property_id': 'P734', 'details': ''})
    entity = _entity_with_claim('P734', 'Q845104')
    entity['claims']['P734'].append(
        _entity_with_claim('P734', 'Q130601266')['claims']['P734'][0])
    assert _self_ref_gone(row, entity) is False


def test_no_property_means_no_correction():
    row = _row({'details': 'malformed'})
    assert _self_ref_gone(row, {'claims': {}}) is False


def test_novalue_snak_has_no_datavalue():
    # somevalue/novalue snaks lack datavalue entirely; must not crash and the
    # self-reference counts as gone.
    row = _row({'property_id': 'P734', 'details': ''})
    entity = {'claims': {'P734': [{'mainsnak': {'snaktype': 'novalue'}}]}}
    assert _self_ref_gone(row, entity) is True

"""
Tests for recheck's claim check on known_vandalism_value flags, and for the
shared dispatch that resolves both claim indicators in one API pass.
"""
from recheck import _check_claims, _magnet_value_gone


def _row(details, qid='Q42', indicator='known_vandalism_value', id_=1):
    return {'id': id_, 'item_qid': qid, 'indicator_name': indicator,
            'indicator_details': details}


def _item_claim(target_qid):
    return {'mainsnak': {'snaktype': 'value',
                         'datavalue': {'type': 'wikibase-entityid',
                                       'value': {'entity-type': 'item',
                                                 'id': target_qid}}}}


def _entity(claims):
    return {'claims': claims}


def test_value_still_present_is_not_corrected():
    row = _row({'property_id': 'P22', 'value_qid': 'Q615'})
    entity = _entity({'P22': [_item_claim('Q615')]})
    assert _magnet_value_gone(row, entity) is False


def test_value_replaced_is_corrected():
    row = _row({'property_id': 'P22', 'value_qid': 'Q615'})
    entity = _entity({'P22': [_item_claim('Q1234')]})
    assert _magnet_value_gone(row, entity) is True


def test_property_removed_entirely_is_corrected():
    row = _row({'property_id': 'P22', 'value_qid': 'Q615'})
    assert _magnet_value_gone(row, _entity({})) is True


def test_other_statement_on_same_property_keeps_flag_active():
    row = _row({'property_id': 'P22', 'value_qid': 'Q615'})
    entity = _entity({'P22': [_item_claim('Q1234'), _item_claim('Q615')]})
    assert _magnet_value_gone(row, entity) is False


def test_non_item_value_does_not_crash():
    row = _row({'property_id': 'P22', 'value_qid': 'Q615'})
    entity = _entity({'P22': [{'mainsnak': {'snaktype': 'somevalue'}}]})
    assert _magnet_value_gone(row, entity) is True


def test_missing_value_qid_leaves_row_active():
    # Nothing to check against, so never claim a correction.
    row = _row({'property_id': 'P22'})
    assert _magnet_value_gone(row, _entity({'P22': []})) is False


def test_without_property_the_whole_item_is_searched():
    row = _row({'value_qid': 'Q615'})
    # Value moved to some other property — still on the item, still active.
    assert _magnet_value_gone(row, _entity({'P26': [_item_claim('Q615')]})) is False
    assert _magnet_value_gone(row, _entity({'P26': [_item_claim('Q7')]})) is True


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return _FakeResponse(self._payload)


def test_both_claim_indicators_share_one_request():
    rows = [
        _row({'property_id': 'P361', 'details': ''}, indicator='self_reference_added', id_=1),
        _row({'property_id': 'P22', 'value_qid': 'Q615'}, id_=2),
        # Not a claim indicator — must not pull an extra QID into the batch.
        _row({'lang': 'en'}, qid='Q99', indicator='bad_description', id_=3),
    ]
    session = _FakeSession({'entities': {'Q42': _entity({
        'P361': [_item_claim('Q42')],   # self-reference still there
        'P22': [_item_claim('Q1234')],  # magnet value replaced
    })}})

    corrected, errors = _check_claims(session, rows)

    assert errors == 0
    assert corrected == {2}
    assert len(session.calls) == 1
    assert session.calls[0]['ids'] == 'Q42'


def test_api_failure_counts_as_error_and_corrects_nothing():
    class _BoomSession:
        def get(self, *a, **k):
            raise RuntimeError('boom')

    rows = [_row({'property_id': 'P22', 'value_qid': 'Q615'}, id_=2)]
    corrected, errors = _check_claims(_BoomSession(), rows)
    assert corrected == set()
    assert errors == 1

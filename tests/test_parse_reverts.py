"""
Tests for parse_edit_comment's revert/undo/restore handling.

These comment shapes are produced verbatim by MediaWiki/Wikibase on
wikidatawiki (sampled 2026-08 via the recentchanges API with rctag filters):
  mw-undo:     /* undo:0||<revid>|<user> */ optional free text
  restore UI:  /* restore:0||<revid>|<user> */ optional free text
  mw-rollback: Reverted edits by [[Special:Contributions/<user>|<user>]] ...
"""
from utils import parse_edit_comment


def test_standard_undo_summary():
    p = parse_edit_comment(
        "/* undo:0||2530834010|Prof.MarianoDaRosa */ rev. Prof. selfie")
    assert p['action'] == 'undo'
    assert p['details']['undone_rev_id'] == 2530834010


def test_standard_restore_summary():
    p = parse_edit_comment("/* restore:0||2528972004|Yirba */ rvv")
    assert p['action'] == 'restore'
    assert p['details']['restored_rev_id'] == 2528972004


def test_rollback_linked_username_with_spaces():
    p = parse_edit_comment(
        "Reverted edits by [[Special:Contributions/Nourhan El-Kady|Nourhan El-Kady]] "
        "([[User talk:Nourhan El-Kady|talk]]) to last revision by Foo")
    assert p['action'] == 'revert'
    assert p['details']['reverted_user'] == 'Nourhan El-Kady'


def test_rollback_linked_temp_account():
    p = parse_edit_comment(
        "Reverted edits by [[Special:Contributions/~2026-44710-20|~2026-44710-20]] "
        "([[User talk:~2026-44710-20|talk]])")
    assert p['action'] == 'revert'
    assert p['details']['reverted_user'] == '~2026-44710-20'


def test_english_prose_undo_still_parses():
    p = parse_edit_comment("Undo revision 123456 by SomeUser")
    assert p['action'] == 'undo'
    assert p['details']['undone_rev_id'] == 123456


def test_plain_revert_fallback():
    p = parse_edit_comment("Reverted edits by BadActor (talk | contribs)")
    assert p['action'] == 'revert'
    assert p['details']['reverted_user'] == 'BadActor'


def test_non_revert_comments_unaffected():
    p = parse_edit_comment("/* wbsetlabel-set:1|en */ some label")
    assert p['action'] == 'wbsetlabel-set'
    assert p['language'] == 'en'
    assert 'undone_rev_id' not in p['details']
    assert 'restored_rev_id' not in p['details']

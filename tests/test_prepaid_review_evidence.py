"""Prepaid review holds cannot be settled as ordinary provider successes."""
import pytest

from gridraft.store import Store
from test_gridraft import MODEL, WALLET


def test_review_hold_requires_audited_operator_settlement(tmp_path):
    store = Store(str(tmp_path/'prepaid.db'), 'p'*40)
    store.credit(WALLET, 10000, 'fixture')
    key = store.issue_key(WALLET, 'fixture', 10000)
    request_id = store.reserve(key['id'], WALLET, 1000, 'request', MODEL, 30)
    other = Store(str(tmp_path/'prepaid.db'), 'p'*40)
    other.review(request_id, 'provider-reference')
    other.close()

    with pytest.raises(ValueError):
        store.settle(request_id, 0)
    with pytest.raises(ValueError):
        store.settle(request_id, 0, evidence='provider statement')
    assert store.pending()[0]['state'] == 'needs_review'
    assert store.account(WALLET)['balance_nusd'] == 9000
    assert store.keys(WALLET)[0]['spent_nusd'] == 1000
    assert store.needs_review() is True

    assert store.settle(request_id, 250, state='operator_settled', evidence='provider statement')
    assert store.account(WALLET)['balance_nusd'] == 9750
    assert store.keys(WALLET)[0]['spent_nusd'] == 250
    assert store.needs_review() is False
    assert store.db.execute('SELECT evidence FROM reconciliations WHERE request_id=?',
                            (request_id,)).fetchone()[0] == 'provider statement'
    store.close()


@pytest.mark.parametrize('evidence', [None, '', '   ', '\n', 123, 'x'*201])
def test_invalid_operator_evidence_does_not_release_prepaid_hold(tmp_path, evidence):
    store = Store(str(tmp_path/'prepaid.db'), 'p'*40)
    store.credit(WALLET, 10000, 'fixture')
    key = store.issue_key(WALLET, 'fixture', 10000)
    request_id = store.reserve(key['id'], WALLET, 1000, 'request', MODEL, 30)
    store.review(request_id)
    with pytest.raises(ValueError):
        store.settle(request_id, 0, state='operator_settled', evidence=evidence)
    assert store.needs_review() is True
    assert store.account(WALLET)['balance_nusd'] == 9000
    store.close()

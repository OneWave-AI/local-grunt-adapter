from telemetry import Ledger
import pytest


def test_lifetime_review_and_negative_roi(tmp_path):
    ledger = Ledger(tmp_path/'usage.sqlite3')
    ledger.record('a', 'extract', {'input_characters':16000,'local_input_tokens':4000,'local_output_tokens':10}, 'ok', 'files')
    pending = ledger.roi()['estimated_net_cloud_tokens_saved']
    assert pending < 0
    ledger.outcome('a','accepted')
    assert ledger.roi()['estimated_net_cloud_tokens_saved'] == pending+4000
    ledger.outcome('a','redone')
    assert ledger.roi()['estimated_net_cloud_tokens_saved'] == pending
    with ledger.connect() as c: c.execute('UPDATE calls SET created=0')
    assert ledger.summary()['calls'] == 0
    assert ledger.summary()['roi']['calls'] == 1


def test_text_no_credit_and_paired_replacement(tmp_path):
    ledger = Ledger(tmp_path/'usage.sqlite3')
    ledger.record('a','extract',{'input_characters':16000},'ok','text')
    ledger.outcome('a','accepted')
    assert ledger.roi()['estimated_avoided_cloud_input_tokens'] == 0
    ledger.record_cloud_pair('a',100,120)
    ledger.record_cloud_pair('a',100,130)
    assert ledger.roi()['measured_net_cloud_tokens_saved'] == -30
    assert ledger.roi()['paired_measurements'] == 1
    with pytest.raises(ValueError): ledger.record_cloud_pair('a',-1,2)
    with pytest.raises(ValueError): ledger.record_cloud_pair('missing',1,2)


def test_configured_cost_and_invalid_rate(tmp_path):
    ledger=Ledger(tmp_path/'usage.sqlite3')
    config=tmp_path/'roi-config.json'
    config.write_text('{"blended_cloud_usd_per_million_tokens":10,"local_cost_usd":2}')
    assert ledger.roi()['estimated_net_usd'] == -2
    assert ledger.roi()['estimated_roi_percent'] == -100
    config.write_text('{"characters_per_token":0}')
    with pytest.raises(ValueError): ledger.roi()

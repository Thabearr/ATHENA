from __future__ import annotations
import hashlib
import json

import pytest

from domain.goal_score_dynamics import FeatureStatus,GOAL_SCORE_FEATURE_REGISTRY,GoalScoreError
import domain.goal_score_training_view as v


def test_training_view_contract_pin_validates():
    _,_,e,t=v.validate_training_view_contract()
    assert t==v.calculate_training_view_contract_sha256(e)


def test_canonical_payload_rejects_rehashless_mutation():
    raw='{"a":1}';sha=hashlib.sha256(raw.encode()).hexdigest()
    assert v._parse_canonical_payload(raw,sha,'x')['a']==1
    with pytest.raises(GoalScoreError):v._parse_canonical_payload('{"a":2}',sha,'x')


def test_target_requires_available_canonical_ft_labels():
    ok={'labels':{'HOME_GOALS':{'status':'AVAILABLE','value':2},'AWAY_GOALS':{'status':'AVAILABLE','value':1}}}
    assert v._extract_target(ok)==(2,1)
    bad={'labels':{'HOME_GOALS':{'status':'MISSING','value':None},'AWAY_GOALS':{'status':'AVAILABLE','value':1}}}
    with pytest.raises(GoalScoreError):v._extract_target(bad)


def test_postmatch_coverage_fields_are_not_model_features():
    joined=' '.join(x.feature_id.lower() for x in GOAL_SCORE_FEATURE_REGISTRY)
    assert all(word not in joined for word in ('data_quality','lineup','coach','referee','path_label','label_availability','capability'))


def _asof_payload():
    values=[];seen=set()
    for d in GOAL_SCORE_FEATURE_REGISTRY:
      if d.upstream_corpus!='HISTORICAL_ASOF':continue
      key=(d.upstream_feature_id,d.scope,d.window)
      if key in seen:continue
      seen.add(key);values.append({'feature_id':d.upstream_feature_id,'scope':d.scope,'window':d.window,'status':'AVAILABLE','value':1.25})
    return {'home_resolutions':values,'away_resolutions':values}


def _tactical_payload():
    def dims(scope):
      values=[];seen=set()
      for d in GOAL_SCORE_FEATURE_REGISTRY:
        if d.upstream_corpus=='TACTICAL_IDENTITY' and d.scope==scope and d.upstream_feature_id not in seen:
          seen.add(d.upstream_feature_id);values.append({'dimension_id':d.upstream_feature_id,'status':'AVAILABLE','continuous_score':.2})
      return values
    return {'home_profile':{'overall_dimensions':dims('OVERALL'),'venue_dimensions':dims('HOME_ONLY')},'away_profile':{'overall_dimensions':dims('OVERALL'),'venue_dimensions':dims('AWAY_ONLY')}}


def test_feature_extraction_covers_registry_and_preserves_status():
    out=v._extract_features(_asof_payload(),_tactical_payload())
    assert set(out)=={d.feature_id for d in GOAL_SCORE_FEATURE_REGISTRY}
    assert all(status is FeatureStatus.AVAILABLE for status,_ in out.values())


def test_missing_upstream_feature_stays_missing_not_zero():
    a=_asof_payload();a['home_resolutions']=[]
    out=v._extract_features(a,_tactical_payload())
    key=next(d.feature_id for d in GOAL_SCORE_FEATURE_REGISTRY if d.upstream_corpus=='HISTORICAL_ASOF' and d.side=='HOME')
    assert out[key]==(FeatureStatus.MISSING,None)


def test_target_identity_requires_exact_cross_corpus_fields():
    a={'target':{'match_key':'m','match_date':'2020-01-01','scope':'club','competition_key':'x'}}
    c={'match_key':'m','match_date':'2020-01-01','scope':'club','competition_key':'x'}
    assert v._target_identity(a,'ASOF')==v._target_identity(c,'COVERAGE')

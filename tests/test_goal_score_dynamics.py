from __future__ import annotations
from datetime import date,timedelta
import math
from types import MappingProxyType

import numpy as np
import pytest

from domain.goal_score_dynamics import (
    AUTHORITY_FLAGS, FeatureStatus, FoldPreprocessor, GOAL_SCORE_FEATURE_REGISTRY,
    GOAL_SCORE_MODEL_REGISTRY, GoalScoreError, TrainingRow,
    build_goal_score_distribution, calculate_evaluation_contract_sha256,
    calculate_feature_registry_sha256, calculate_model_registry_sha256,
    challenger_disagreement, chronological_split, dixon_coles_tau,
    evaluate_challengers, evaluate_predictions, fit_challenger,
    fit_competition_prior, fit_dixon_coles_rho, paired_date_bucket_bootstrap,
    rolling_origin_folds, validate_evaluation_contract, validate_feature_registry,
    validate_model_registry,
)

F=GOAL_SCORE_FEATURE_REGISTRY[0].feature_id
T=next(x.feature_id for x in GOAL_SCORE_FEATURE_REGISTRY if x.feature_id.startswith('TACTICAL.'))

def row(i:int, *, low=False, team_feature=None, competition='L1'):
    d=(date(2020,1,1)+timedelta(days=i)).isoformat()
    signal=-2.0 if low else 2.0
    hg=0 if low else 3
    ag=0 if low else 2
    features={F:(FeatureStatus.AVAILABLE,signal),T:(FeatureStatus.AVAILABLE,signal)}
    if team_feature is not None: features[F]=(FeatureStatus.AVAILABLE,team_feature)
    return TrainingRow(f'm{i:03d}',d,'club',competition,'2020',hg,ag,MappingProxyType(features))

def corpus(n=40): return [row(i,low=(i%2==0),competition='L1' if i%3 else 'L2') for i in range(n)]

def test_registry_pins_are_literal_and_valid():
    f,m,e=validate_evaluation_contract()
    assert f==calculate_feature_registry_sha256()
    assert m==calculate_model_registry_sha256()
    assert e==calculate_evaluation_contract_sha256(feature_sha=f,model_sha=m)
    assert len(GOAL_SCORE_FEATURE_REGISTRY)==120
    assert len(GOAL_SCORE_MODEL_REGISTRY)==3

def test_same_version_registry_drift_fails():
    with pytest.raises(GoalScoreError): validate_feature_registry(GOAL_SCORE_FEATURE_REGISTRY[:-1])
    with pytest.raises(GoalScoreError): validate_model_registry(GOAL_SCORE_MODEL_REGISTRY[:-1])

def test_training_row_rejects_unknown_feature_and_invalid_target():
    with pytest.raises(GoalScoreError): TrainingRow('x','2020-01-01','club','L','S',-1,0,{})
    with pytest.raises(GoalScoreError): TrainingRow('x','2020-01-01','club','L','S',1,0,{'odds':(FeatureStatus.AVAILABLE,2.0)})

def test_missing_and_blocked_remain_distinct_design_columns():
    a=row(1);b=row(2)
    a=TrainingRow(a.match_key,a.match_date,a.scope,a.competition_key,a.season,a.home_goals,a.away_goals,{F:(FeatureStatus.MISSING,None)})
    b=TrainingRow(b.match_key,b.match_date,b.scope,b.competition_key,b.season,b.home_goals,b.away_goals,{F:(FeatureStatus.BLOCKED,None)})
    pp=FoldPreprocessor([F]).fit([row(0)])
    x=pp.transform([a,b])
    assert x[0].tolist()==[2.0,1.0,0.0]
    assert x[1].tolist()==[2.0,0.0,1.0]

def test_validation_values_cannot_change_train_median():
    pp=FoldPreprocessor([F]).fit([row(1,team_feature=1),row(2,team_feature=3)])
    before=dict(pp.medians);pp.transform([row(3,team_feature=999999)])
    assert pp.medians==before=={F:2.0}

def test_competition_prior_is_train_only_and_shrunk():
    prior=fit_competition_prior([row(i,low=False,competition='A') for i in range(4)]+[row(i+10,low=True,competition='B') for i in range(4)])
    a=prior.rates('A');b=prior.rates('B');unknown=prior.rates('NEW')
    assert 0<a[3]<1 and 0<b[3]<1 and a[0]>b[0]
    assert unknown[:2]==(prior.global_home_rate,prior.global_away_rate)

def test_chronological_split_uses_complete_unique_date_buckets():
    rows=corpus(20)+[TrainingRow('dup',corpus(20)[-1].match_date,'club','L1','2020',1,1,{F:(FeatureStatus.AVAILABLE,0.0)})]
    split=chronological_split(rows)
    assert set(r.match_date for r in split.development_rows).isdisjoint(r.match_date for r in split.holdout_rows)
    assert split.holdout_dates==tuple(sorted(set(r.match_date for r in rows))[-4:])

def test_rolling_origin_has_five_strict_folds():
    split=chronological_split(corpus(30));folds=rolling_origin_folds(split.development_rows)
    assert len(folds)==5
    for train,val in folds: assert max(r.match_date for r in train)<min(r.match_date for r in val)

def test_independent_score_surface_normalizes_and_has_adaptive_tail():
    d=build_goal_score_distribution('P',1.7,1.2)
    assert math.isclose(sum(d.probabilities.values()),1.0,abs_tol=1e-12)
    assert d.omitted_tail_mass<=1e-10
    assert d.home_win+d.draw+d.away_win==pytest.approx(1.0)
    assert sum(d.total_goals_distribution().values())==pytest.approx(1.0)
    assert sum(d.goal_margin_distribution().values())==pytest.approx(1.0)

def test_dixon_coles_tau_only_changes_four_low_score_cells():
    rho=.05;lam=1.4;mu=1.1
    for h in range(4):
      for a in range(4):
        if (h,a) not in {(0,0),(0,1),(1,0),(1,1)}: assert dixon_coles_tau(h,a,lam,mu,rho)==1.0

def test_dixon_coles_rho_is_safe_and_surface_normalizes():
    rows=corpus(20);rho=fit_dixon_coles_rho(rows,[1.4]*20,[1.1]*20)
    assert all(dixon_coles_tau(h,a,1.4,1.1,rho)>0 for h,a in ((0,0),(0,1),(1,0),(1,1)))
    assert sum(build_goal_score_distribution('DC',1.4,1.1,rho).probabilities.values())==pytest.approx(1.0)

def test_all_challengers_produce_positive_finite_intensities():
    rows=corpus(30)
    for model_id in ('POISSON_GLM_SCORE_V1','DIXON_COLES_SCORE_V1','HIST_GRADIENT_BOOSTING_POISSON_V1'):
        model=fit_challenger(model_id,rows);h,a=model.predict_intensities(rows[:3])
        assert np.all(np.isfinite(h)) and np.all(h>0) and np.all(a>0)

def test_hgb_challenger_is_deterministic_with_same_seed_and_data():
    rows=corpus(30);a=fit_challenger('HIST_GRADIENT_BOOSTING_POISSON_V1',rows);b=fit_challenger('HIST_GRADIENT_BOOSTING_POISSON_V1',rows)
    ah,aa=a.predict_intensities(rows[:5]);bh,ba=b.predict_intensities(rows[:5])
    assert np.allclose(ah,bh) and np.allclose(aa,ba)

def test_exact_score_nll_uses_positive_infinite_support_probability():
    r=TrainingRow('hi','2021-01-01','club','L','S',12,0,{F:(FeatureStatus.AVAILABLE,0.0)})
    m=evaluate_predictions([r],[build_goal_score_distribution('P',1.4,1.0)])
    assert math.isfinite(m['exact_score_nll'])

def test_challenger_disagreement_and_paired_bootstrap():
    a=build_goal_score_distribution('A',1.0,1.0);b=build_goal_score_distribution('B',2.0,.8)
    out=challenger_disagreement({'a':a,'b':b});assert out['home_intensity_range']==1.0 and out['mean_pairwise_total_variation']>0
    rows=corpus(20);paired=paired_date_bucket_bootstrap(rows,[1.0]*20,[.9]*20,replicates=30)
    assert paired['mean_difference']==pytest.approx(.1)

def test_no_team_manager_or_bookmaker_identity_features():
    text=' '.join(f.feature_id.lower()+f.upstream_feature_id.lower() for f in GOAL_SCORE_FEATURE_REGISTRY)
    assert all(word not in text for word in ('team_name','manager_name','odds','price','sportybet','kelly','implied'))

def test_synthetic_tactical_signal_is_learned_without_identity():
    rows=[]
    for i in range(50):
        low=i%2==0;base=row(i,low=low)
        rows.append(TrainingRow(base.match_key,base.match_date,base.scope,base.competition_key,base.season,base.home_goals,base.away_goals,{T:(FeatureStatus.AVAILABLE,-3.0 if low else 3.0)}))
    model=fit_challenger('POISSON_GLM_SCORE_V1',rows,feature_ids=[T])
    assert model.predict_intensities([rows[1]])[0][0]>model.predict_intensities([rows[0]])[0][0]

def test_authority_is_research_only():
    assert AUTHORITY_FLAGS['research_goal_score_model'] is True
    assert not any(v for k,v in AUTHORITY_FLAGS.items() if k!='research_goal_score_model')

def test_full_protocol_runs_without_production_promotion():
    result=evaluate_challengers(corpus(36))
    assert len(result['development_ranking'])==3
    assert result['production_promotion_eligible'] is False
    assert result['holdout_exposure'] is True
    assert result['live_champion_replay_status']=='BLOCKED_NOT_CANONICALLY_REPLAYABLE'

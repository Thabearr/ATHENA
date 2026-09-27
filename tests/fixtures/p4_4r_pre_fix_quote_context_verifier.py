def verify_current_shadow_price_context(value: Any) -> CurrentShadowPriceContext:
    if type(value) is not CurrentShadowPriceContext:
        raise ShadowPriceError("value must be exact CurrentShadowPriceContext")
    if value.source_context_mode == LEGACY_PR253_FIXTURE_BRIDGE:
        if value._bridge_bundle is None:
            raise ShadowPriceError("legacy context omitted retained fixture bridge")
        rebuilt = build_current_shadow_price_context(
            complete_current_history=value._complete_current_history,
            fixture_identity=value.fixture_identity,
            provider_event_evidence=value._event_evidence,
            fixture_quote_bridge=value._bridge_bundle,
        )
    elif value.source_context_mode == CURRENT_RECONCILIATION_DIRECT:
        if value._current_reconciliation_bundle is None:
            raise ShadowPriceError("direct current context omitted retained reconciliation")
        rebuilt = build_current_shadow_price_context_from_reconciliation(
            complete_current_history=value._complete_current_history,
            fixture_identity=value.fixture_identity,
            provider_event_id=value.provider_event_id,
            current_reconciliation_bundle=value._current_reconciliation_bundle,
        )
    else:
        raise ShadowPriceError("unknown current Shadow source-context mode")
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise ShadowPriceError("current Shadow price context differs on source replay")
    return rebuilt

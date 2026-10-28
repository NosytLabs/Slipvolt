"""Bounded, read-only OpenBroker usage-list reconciliation.

The list is provider-reported and paginated, not an atomic account statement.
It never allocates funds, changes a ledger, or runs inference.
"""
from datetime import date, datetime, timezone
from .broker import quantity

CATEGORIES = ('provider_settled_requests', 'estimated_requests',
              'epoch_adjustments', 'fallback_unbilled', 'other')


def _category(source):
    if not isinstance(source, str) or not 1 <= len(source) <= 100 or not source.isprintable():
        raise ValueError('Invalid provider cost source')
    if source.startswith('devshard_'):
        return 'provider_settled_requests'
    if source.startswith('estimated_'):
        return 'estimated_requests'
    if source == 'escrow_epoch':
        return 'epoch_adjustments'
    if source == 'fallback_unbilled':
        return 'fallback_unbilled'
    return 'other'


def _row(row, start, end):
    if not isinstance(row, dict):
        raise ValueError('Invalid provider usage row')
    identifier = row.get('id')
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or not identifier.isprintable():
        raise ValueError('Invalid provider usage identifier')
    timestamp = row.get('created_at')
    if not isinstance(timestamp, str) or len(timestamp) > 64:
        raise ValueError('Invalid provider usage timestamp')
    try:
        observed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError('Missing timezone')
        day = observed.astimezone(timezone.utc).date()
    except (ValueError, OverflowError) as exc:
        raise ValueError('Invalid provider usage timestamp') from exc
    if not start <= day <= end:
        raise ValueError('Provider usage row is outside the requested window')
    category = _category(row.get('cost_source'))
    cost = quantity(row.get('cost_ngonka'))
    if category == 'fallback_unbilled' and cost != 0:
        raise ValueError('Inconsistent unbilled provider row')
    return identifier, category, cost


async def reconcile_usage(broker, start, end, *, max_pages=5, page_size=200):
    if type(start) is not date or type(end) is not date or not 0 <= (end-start).days < 90:
        raise ValueError('Choose a UTC date window of at most 90 days')
    if type(max_pages) is not int or not 1 <= max_pages <= 25:
        raise ValueError('Invalid provider page limit')
    if type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError('Invalid provider page size')
    categories = {name: {'rows': 0, 'cost_ngonka': 0} for name in CATEGORIES}
    identifiers = set()
    expected = None
    for page in range(1, max_pages + 1):
        query = f'/v1/usage?page={page}&page_size={page_size}&from={start.isoformat()}&to={end.isoformat()}'
        payload = await broker.read(query, True, max_bytes=4_000_000)
        rows, pagination = payload.get('data'), payload.get('pagination')
        if not isinstance(rows, list) or not isinstance(pagination, dict):
            raise ValueError('Invalid provider pagination')
        current, size = pagination.get('page'), pagination.get('page_size')
        total, pages = pagination.get('total_items'), pagination.get('total_pages')
        if any(type(value) is not int for value in (current, size, total, pages)):
            raise ValueError('Invalid provider pagination')
        if current != page or size != page_size or total < 0:
            raise ValueError('Invalid provider pagination')
        calculated_pages = (total + page_size - 1) // page_size
        if pages not in ((0, 1) if total == 0 else (calculated_pages,)):
            raise ValueError('Inconsistent provider pagination')
        if expected is not None and (total, pages) != expected:
            raise ValueError('Provider pagination changed during the scan')
        expected = total, pages
        if len(rows) != min(page_size, max(0, total - (page-1)*page_size)):
            raise ValueError('Incomplete provider page')
        for row in rows:
            identifier, category, cost = _row(row, start, end)
            if identifier in identifiers:
                raise ValueError('Duplicate provider usage identifier')
            identifiers.add(identifier)
            categories[category]['rows'] += 1
            categories[category]['cost_ngonka'] += cost
        if page >= pages:
            for group in categories.values():
                group['cost_ngonka'] = str(group['cost_ngonka'])
            return {'from': start.isoformat(), 'to': end.isoformat(),
                'pages': page, 'rows': len(identifiers), 'categories': categories,
                'account_debits_verified': False,
                'notice': 'Provider-reported list; pages are not an atomic statement. Reconcile against account movements before financial decisions.'}
    raise ValueError('Provider usage exceeds the configured page limit')

from datetime import datetime, date


def format_date(d):
    """Format a date string to readable format."""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, '%Y-%m-%d')
        except ValueError:
            try:
                d = datetime.strptime(d, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return d
    if isinstance(d, (datetime, date)):
        return d.strftime('%b %d, %Y')
    return str(d)


def format_datetime(dt):
    """Format a datetime string to readable format."""
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return dt
    if isinstance(dt, datetime):
        return dt.strftime('%b %d, %Y %I:%M %p')
    return str(dt)


def format_currency(amount):
    """Format amount as currency."""
    if amount is None:
        return '₹0.00'
    return f'₹{amount:,.2f}'


def time_ago(dt_str):
    """Return a human-readable 'time ago' string."""
    if isinstance(dt_str, str):
        try:
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return dt_str
    elif isinstance(dt_str, datetime):
        dt = dt_str
    else:
        return str(dt_str)

    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return 'just now'
    elif seconds < 3600:
        mins = int(seconds // 60)
        return f'{mins}m ago'
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours}h ago'
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f'{days}d ago'
    else:
        return format_date(dt)


def paginate(items, page, per_page=20):
    """Simple pagination helper."""
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        'items': items[start:end],
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': max(1, (total + per_page - 1) // per_page),
        'has_prev': page > 1,
        'has_next': end < total,
    }

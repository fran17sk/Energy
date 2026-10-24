from django import template

register = template.Library()


@register.filter
def duracion(value):
    if value is None:
        return '—'
    seconds = max(0, float(value))
    if seconds < 60:
        return '< 1 min'
    if seconds < 3600:
        return f'{seconds / 60:.0f} min'
    if seconds < 86400:
        return f'{seconds / 3600:.1f}'.replace('.', ',') + ' h'
    return f'{seconds / 86400:.1f}'.replace('.', ',') + ' días'

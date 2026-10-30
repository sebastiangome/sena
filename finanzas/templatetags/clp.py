from django import template

register = template.Library()


@register.filter
def clp(valor):
    """Formatea un entero como pesos chilenos: 1234567 -> $1.234.567"""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return valor
    signo = "-" if n < 0 else ""
    return f"{signo}${abs(n):,}".replace(",", ".")

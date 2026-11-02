def tema(request):
    if request.user.is_authenticated:
        try:
            return {"tema_actual": request.user.perfil.tema}
        except Exception:
            from .models import Perfil
            perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
            return {"tema_actual": perfil.tema}
    return {"tema_actual": "auto"}


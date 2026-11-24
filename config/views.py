from django.http import HttpResponse


def home(request):
    return HttpResponse("CafeCorner order management")

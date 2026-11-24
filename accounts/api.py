from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated

from accounts.models import Profile
from accounts.serializers import ProfileSerializer


class CurrentProfileView(RetrieveAPIView):
    serializer_class = ProfileSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        # Legacy or manually-created users may predate the profile signal.
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

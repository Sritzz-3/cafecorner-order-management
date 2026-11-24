from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

from accounts.models import Profile


class Command(BaseCommand):
    help = "Create the dedicated printer user and display its DRF token once."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="cafecorner-printer")

    def handle(self, *args, **options):
        username = options["username"]
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User {username!r} already exists; refusing to display or rotate its token.")

        with transaction.atomic():
            user = User(username=username, is_staff=False, is_superuser=False)
            user.set_unusable_password()
            user.save()
            profile = user.profile
            profile.role = Profile.Role.PRINTER
            profile.save()
            token = Token.objects.create(user=user)
        self.stdout.write(self.style.SUCCESS(f"Printer user created: {username}"))
        self.stdout.write(f"PRINTER_TOKEN={token.key}")
        self.stdout.write("Store this token securely on the printer device. It will not be shown again.")

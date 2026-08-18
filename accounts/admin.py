from django.contrib import admin

from .models import User, UserSettings

admin.site.register(User)
admin.site.register(UserSettings)

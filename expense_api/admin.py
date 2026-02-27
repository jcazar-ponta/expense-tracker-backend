from django.contrib import admin

from .models import Allocation, AppSettings, ItemExpense, LedgerEvent, Payment, Person

admin.site.register(Person)
admin.site.register(ItemExpense)
admin.site.register(Allocation)
admin.site.register(Payment)
admin.site.register(LedgerEvent)
admin.site.register(AppSettings)

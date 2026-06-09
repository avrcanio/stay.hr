from __future__ import annotations

from django import forms

from apps.properties.guest_info import merge_wifi_into_guest_info, wifi_facts_from_guest_info
from apps.properties.models import Property


class PropertyAdminForm(forms.ModelForm):
    wifi_ssid = forms.CharField(
        label="WiFi mreža (SSID)",
        required=False,
        max_length=128,
        help_text="Prikazuje se gostu u porukama nakon check-in-a.",
    )
    wifi_password = forms.CharField(
        label="WiFi lozinka",
        required=False,
        max_length=128,
        help_text="Prikazuje se gostu u porukama nakon check-in-a.",
    )

    class Meta:
        model = Property
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            ssid, password = wifi_facts_from_guest_info(self.instance.guest_info)
            self.fields["wifi_ssid"].initial = ssid
            self.fields["wifi_password"].initial = password

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.guest_info = merge_wifi_into_guest_info(
            instance.guest_info,
            ssid=self.cleaned_data.get("wifi_ssid") or "",
            password=self.cleaned_data.get("wifi_password") or "",
        )
        if commit:
            instance.save()
            self.save_m2m()
        return instance

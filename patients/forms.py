from django import forms
from .models import PatientsModel




class PatientsModelForm(forms.ModelForm):
    dob = forms.DateField(
        widget=forms.DateInput(format='%d-%m-%Y'),
        input_formats=['%d-%m-%Y']
    )

    class Meta:
        model = PatientsModel
        fields = '__all__'
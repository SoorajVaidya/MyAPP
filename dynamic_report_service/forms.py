from django import forms
from django_select2.forms import Select2MultipleWidget
from .models import (
    AcupressureProtocolBank,
    AcupressureReportSystem,
    AuricularProtocolBank,
    AuricularReportSystem,
    MudraReportSystem,
    MudraProtocolBank,
    PranayamaProtocolBank,
    PranayamaReportSystem,
    SeedtherapyProtocolBank,
    SeedtherapyReportSystem,
    SingleSeedProtocolBank,
    SingleSeedReportSystem,
    YogaReportSystem,
    YogaProtocolBank,
    ColourProtocolBank,
    ColourReportSystem,
)
from django_select2.forms import Select2Widget
from django import forms
from django.utils.safestring import mark_safe
import re


class ProtocolWidget(forms.MultiWidget):
    def __init__(self, *args, **kwargs):
        hand_choices = [
            ("Left", "Left"),
            ("Right", "Right"),
        ]
        area_choices = [
            ("Thumb", "Thumb"),
            ("Index", "Index"),
            ("Middle", "Middle"),
            ("Fourth", "Fourth"),
            ("Little", "Little"),
            ("Center", "Center"),
        ]
        position_choices = [("Ring", "Ring"), ("Yin", "Yin"), ("Yang", "Yang")]
        number_choices = [
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
            ("6", "6"),
            ("7", "7"),
            ("8", "8"),
            ("9", "9"),
            ("10", "10"),
            ("11", "11"),
            ("12", "12"),
            ("13", "13"),
            ("14", "14"),
            ("15", "15"),
            ("16", "16"),
            ("31", "31"),
            ("32", "32"),
            ("33", "33"),
        ]
        colour_choices = [
            ("Red", "Red"),
            ("Black", "Black"),
            ("Blue", "Blue"),
            ("Green", "Green"),
            ("Sky Blue", "Sky Blue"),
            ("Orange", "Orange"),
            ("Yellow", "Yellow"),
            ("Pink", "Pink"),
        ]
        widgets = [
            forms.Select(
                choices=hand_choices,
                attrs={"style": "width: 20%; display: inline-block;"},
            ),
            forms.Select(
                choices=area_choices,
                attrs={"style": "width: 20%; display: inline-block;"},
            ),
            forms.Select(
                choices=position_choices,
                attrs={"style": "width: 20%; display: inline-block;"},
            ),
            forms.Select(
                choices=number_choices,
                attrs={"style": "width: 20%; display: inline-block;"},
            ),
            forms.Select(
                choices=colour_choices,
                attrs={"style": "width: 20%; display: inline-block;"},
            ),
        ]
        super().__init__(widgets, *args, **kwargs)

    def decompress(self, value):
        if value:
            return value.split(",")
        return [None, None, None]  # Defaults if no value is present

    def format_output(self, rendered_widgets):
        return mark_safe(" ".join(rendered_widgets))


class PlusProtocolWidget(ProtocolWidget):
    def render(self, name, value, attrs=None, renderer=None):
        # Render the initial protocol group (group index 0)
        original_html = super().render(name, value, attrs, renderer)
        # Wrap the original widget in a full-width container
        container_html = (
            f'<div id="{name}-container" style="width:100%;">{original_html}</div>'
        )

        # Create a hidden template for cloning new protocol groups.
        # Replace the input name portion (e.g. "protocol_") with a placeholder "{{group}}"
        template_group_html = original_html.replace(
            f"{name}_", f"{name}_{{{{group}}}}_"
        )
        template_html = (
            f'<div id="{name}-template" style="display:none;">'
            f"{template_group_html}"
            "</div>"
        )

        # Create the plus button with green styling (btn-success) and some top margin
        plus_button_html = (
            f'<button type="button" id="{name}-plus" class="btn btn-success add-{name}" '
            f'style="margin-top: 10px;">+</button>'
        )

        # Inline JavaScript that:
        # 1. Always appends the plus button at the end of the container.
        # 2. On click, removes the plus button, clones a new protocol group (with updated names),
        #    appends the new group (making it full width) and then re-appends the plus button.
        script = f"""
        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            var container = document.getElementById("{name}-container");
            var template = document.getElementById("{name}-template").innerHTML;
            var plusBtn = document.getElementById("{name}-plus");
            var groupIndex = 1;  // group 0 is already rendered

            // Initially, ensure the plus button is appended after the first group
            container.appendChild(plusBtn);

            plusBtn.addEventListener("click", function() {{
                // Remove the plus button from its current position
                if (plusBtn.parentNode) {{
                    plusBtn.parentNode.removeChild(plusBtn);
                }}
                // Replace the placeholder with the current group index to create new HTML
                var newHtml = template.replace(/{{{{group}}}}/g, groupIndex);
                // Wrap the new group in a div and force it to full width
                var newGroupDiv = document.createElement("div");
                newGroupDiv.innerHTML = newHtml.replace(/id="[^"]*"/g, '');
                newGroupDiv.style.width = "100%";
                container.appendChild(newGroupDiv);
                groupIndex++;
                // Append the plus button at the end of the container so it's always after the latest group
                container.appendChild(plusBtn);
            }});
        }});
        </script>
        """

        combined_html = container_html + template_html + plus_button_html + script
        return mark_safe(combined_html)


class ProtocolField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        # Define individual fields for the MultiValueField
        fields = [
            forms.ChoiceField(
                choices=[("Left", "Left"), ("Right", "Right")], required=True
            ),
            forms.ChoiceField(
                choices=[
                    ("Thumb", "Thumb"),
                    ("Index", "Index"),
                    ("Middle", "Middle"),
                    ("Fourth", "Fourth"),
                    ("Little", "Little"),
                    ("Center", "Center"),
                ],
                required=True,
            ),
            forms.ChoiceField(
                choices=[("Ring", "Ring"), ("Yin", "Yin"), ("Yang", "Yang")],
                required=True,
            ),
            forms.ChoiceField(
                choices=[
                    ("1", "1"),
                    ("2", "2"),
                    ("3", "3"),
                    ("4", "4"),
                    ("5", "5"),
                    ("6", "6"),
                    ("7", "7"),
                    ("8", "8"),
                    ("9", "9"),
                    ("10", "10"),
                    ("11", "11"),
                    ("12", "12"),
                    ("13", "13"),
                    ("14", "14"),
                    ("15", "15"),
                    ("16", "16"),
                    ("31", "31"),
                    ("32", "32"),
                    ("33", "33"),
                ],
                required=True,
            ),
            forms.ChoiceField(
                choices=[
                    ("Red", "Red"),
                    ("Black", "Black"),
                    ("Blue", "Blue"),
                    ("Green", "Green"),
                    ("Sky Blue", "Sky Blue"),
                    ("Orange", "Orange"),
                    ("Yellow", "Yellow"),
                    ("Pink", "Pink"),
                ],
                required=True,
            ),
        ]

        # Call the parent constructor without the widget
        super().__init__(fields, *args, **kwargs)

        # Assign the custom widget
        self.widget = ProtocolWidget()

    def compress(self, values):
        if values:
            return "-".join(values)  # Combine the dropdown values into a single string
        return ""


class AuricularProtocolBankForm(forms.ModelForm):
    protocol = forms.MultipleChoiceField(
        choices=AuricularProtocolBank.PROTOCOL_CHOICES,
        widget=Select2MultipleWidget,
        required=False,
        label="Auricular Protocols",
    )

    class Meta:
        model = AuricularProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocol:
            # Pre-fill the initial data by splitting the saved comma-separated values
            self.initial["protocol"] = self.instance.protocol.split(",")

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Join the selected protocols as a comma-separated string
        instance.protocol = ",".join(self.cleaned_data["protocol"])
        if commit:
            instance.save()
        return instance


class AuricularReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=AuricularProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Auricular Protocols",
    )

    class Meta:
        model = AuricularReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = AuricularProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Auricular Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class MudraProtocolBankForm(forms.ModelForm):
    protocol = forms.ChoiceField(
        choices=MudraProtocolBank.PROTOCOL_CHOICES,
        widget=Select2Widget,  # Single-selection widget
        required=False,
        label="Mudra Protocol",
    )

    class Meta:
        model = MudraProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocol:
            # Pre-fill the initial data for the dropdown
            self.initial["protocol"] = self.instance.protocol

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Save the selected protocol as it is (no need to join since it's a single value)
        instance.protocol = self.cleaned_data["protocol"]
        if commit:
            instance.save()
        return instance


class MudraReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=MudraProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Mudra Protocols",
    )

    class Meta:
        model = MudraReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = MudraProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Mudra Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class YogaProtocolBankForm(forms.ModelForm):
    protocol = forms.ChoiceField(
        choices=YogaProtocolBank.PROTOCOL_CHOICES,
        widget=Select2Widget,  # Single-selection widget
        required=False,
        label="Yoga Protocol",
    )

    class Meta:
        model = YogaProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocol:
            # Pre-fill the initial data for the dropdown
            self.initial["protocol"] = self.instance.protocol

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Save the selected protocol as it is (no need to join since it's a single value)
        instance.protocol = self.cleaned_data["protocol"]
        if commit:
            instance.save()
        return instance


class YogaReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=YogaProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Yoga Protocols",
    )

    class Meta:
        model = YogaReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = YogaProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Yoga Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class ColourProtocolBankForm(forms.ModelForm):
    protocol = ProtocolField(label="Colour Protocol")

    class Meta:
        model = ColourProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set a known base name and use our custom widget
        self.fields["protocol"].widget.attrs["name"] = "protocol"
        self.fields["protocol"].widget = PlusProtocolWidget()

    def clean_protocol(self):
        protocol_groups = []
        base_name = "protocol"  # our known base name
        group_index = 0

        while True:
            group_values = []
            # For group 0, the expected keys: protocol_0, protocol_1, ..., protocol_4
            # For group n (n > 0): protocol_{n}_{0}, protocol_{n}_{1}, ..., protocol_{n}_{4}
            for i in range(5):
                if group_index == 0:
                    key = f"{base_name}_{i}"
                else:
                    key = f"{base_name}_{group_index}_{i}"
                # Use an empty string as default (strip extra whitespace)
                value = self.data.get(key, "").strip()
                group_values.append(value)
            # If all fields in this group are empty, assume no more groups
            if not any(group_values):
                break
            # Only add if all five values are present (you may decide to validate partial groups differently)
            if all(group_values):
                # Combine the five values with dashes, e.g. "Left-Thumb-Ring-1-Red"
                protocol_groups.append("-".join(group_values))
            else:
                # You might want to raise a ValidationError if a group is partially filled
                raise forms.ValidationError(
                    "All dropdowns for each protocol group must be filled."
                )
            group_index += 1

        # Store as a comma-separated string
        return ",".join(protocol_groups)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # The protocol field now contains all protocol groups as a comma-separated string.
        if commit:
            instance.save()
        return instance


class ColourReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=ColourProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Colour Protocols",
    )

    class Meta:
        model = ColourReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = ColourProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Colour Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class SingleSeedProtocolBankForm(forms.ModelForm):
    protocol = forms.CharField(
        required=False, label="Single Seed Protocols", widget=forms.TextInput()
    )

    class Meta:
        model = SingleSeedProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocol:
            # Pre-fill the initial data with the saved string
            self.initial["protocol"] = self.instance.protocol

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Save the text entered directly without splitting or joining
        instance.protocol = self.cleaned_data["protocol"]
        if commit:
            instance.save()
        return instance


class SingleSeedReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=SingleSeedProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Single Seed Protocols",
    )

    class Meta:
        model = SingleSeedReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = SingleSeedProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Single Seed Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class SeedtherapyProtocolBankForm(forms.ModelForm):
    protocol = ProtocolField(label="Seed therapy Protocol")

    class Meta:
        model = SeedtherapyProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set a known base name and use our custom widget
        self.fields["protocol"].widget.attrs["name"] = "protocol"
        self.fields["protocol"].widget = PlusProtocolWidget()

    def clean_protocol(self):
        protocol_groups = []
        base_name = "protocol"  # our known base name
        group_index = 0

        while True:
            group_values = []
            # For group 0, the expected keys: protocol_0, protocol_1, ..., protocol_4
            # For group n (n > 0): protocol_{n}_{0}, protocol_{n}_{1}, ..., protocol_{n}_{4}
            for i in range(5):
                if group_index == 0:
                    key = f"{base_name}_{i}"
                else:
                    key = f"{base_name}_{group_index}_{i}"
                # Use an empty string as default (strip extra whitespace)
                value = self.data.get(key, "").strip()
                group_values.append(value)
            # If all fields in this group are empty, assume no more groups
            if not any(group_values):
                break
            # Only add if all five values are present (you may decide to validate partial groups differently)
            if all(group_values):
                # Combine the five values with dashes, e.g. "Left-Thumb-Ring-1-Red"
                protocol_groups.append("-".join(group_values))
            else:
                # You might want to raise a ValidationError if a group is partially filled
                raise forms.ValidationError(
                    "All dropdowns for each protocol group must be filled."
                )
            group_index += 1

        # Store as a comma-separated string
        return ",".join(protocol_groups)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # The protocol field now contains all protocol groups as a comma-separated string.
        if commit:
            instance.save()
        return instance


class SeedtherapyReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=SeedtherapyProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Seed therapy Protocols",
    )

    class Meta:
        model = SeedtherapyReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = SeedtherapyProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Seed therapy Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class AcupressureProtocolBankForm(forms.ModelForm):
    protocol = ProtocolField(label="Acupressure Protocol")

    class Meta:
        model = AcupressureProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set a known base name and use our custom widget
        self.fields["protocol"].widget.attrs["name"] = "protocol"
        self.fields["protocol"].widget = PlusProtocolWidget()

    def clean_protocol(self):
        protocol_groups = []
        base_name = "protocol"  # our known base name
        group_index = 0

        while True:
            group_values = []
            # For group 0, the expected keys: protocol_0, protocol_1, ..., protocol_4
            # For group n (n > 0): protocol_{n}_{0}, protocol_{n}_{1}, ..., protocol_{n}_{4}
            for i in range(5):
                if group_index == 0:
                    key = f"{base_name}_{i}"
                else:
                    key = f"{base_name}_{group_index}_{i}"
                # Use an empty string as default (strip extra whitespace)
                value = self.data.get(key, "").strip()
                group_values.append(value)
            # If all fields in this group are empty, assume no more groups
            if not any(group_values):
                break
            # Only add if all five values are present (you may decide to validate partial groups differently)
            if all(group_values):
                # Combine the five values with dashes, e.g. "Left-Thumb-Ring-1-Red"
                protocol_groups.append("-".join(group_values))
            else:
                # You might want to raise a ValidationError if a group is partially filled
                raise forms.ValidationError(
                    "All dropdowns for each protocol group must be filled."
                )
            group_index += 1

        # Store as a comma-separated string
        return ",".join(protocol_groups)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # The protocol field now contains all protocol groups as a comma-separated string.
        if commit:
            instance.save()
        return instance


class AcupressureReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=AcupressureProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Acupressure Protocols",
    )

    class Meta:
        model = AcupressureReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = AcupressureProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Acupressure Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance


class PranayamaProtocolBankForm(forms.ModelForm):
    protocol = forms.ChoiceField(
        choices=PranayamaProtocolBank.PROTOCOL_CHOICES,
        widget=Select2Widget,  # Single-selection widget
        required=False,
        label="Pranayama Protocol",
    )

    class Meta:
        model = PranayamaProtocolBank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocol:
            # Pre-fill the initial data for the dropdown
            self.initial["protocol"] = self.instance.protocol

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Save the selected protocol as it is (no need to join since it's a single value)
        instance.protocol = self.cleaned_data["protocol"]
        if commit:
            instance.save()
        return instance


class PranayamaReportSystemForm(forms.ModelForm):
    protocols = forms.ModelMultipleChoiceField(
        queryset=PranayamaProtocolBank.objects.all(),
        widget=Select2MultipleWidget,
        required=False,
        label="Pranayama Protocols",
    )

    class Meta:
        model = PranayamaReportSystem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.protocols:
            protocol_ids = [
                int(id_) for id_ in self.instance.protocols.split(",") if id_.isdigit()
            ]
            self.initial["protocols"] = PranayamaProtocolBank.objects.filter(
                id__in=protocol_ids
            )
        self.fields["protocols"].label_from_instance = (
            lambda obj: f"Pranayama Protocol {obj.protocol_number}"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.protocols = ",".join(
            [
                str(protocol.protocol_number)
                for protocol in self.cleaned_data["protocols"]
            ]
        )
        if commit:
            instance.save()
        return instance

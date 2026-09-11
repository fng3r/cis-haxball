from django.contrib import admin
from django.contrib.postgres.fields import ArrayField

from django_celery_beat.admin import ClockedScheduleAdmin as BaseClockedScheduleAdmin
from django_celery_beat.admin import CrontabScheduleAdmin as BaseCrontabScheduleAdmin
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from django_celery_beat.admin import PeriodicTaskForm, TaskSelectWidget
from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    SolarSchedule,
)
from django_celery_results.admin import GroupResultAdmin as BaseGroupResultAdmin
from django_celery_results.admin import TaskResultAdmin as BaseTaskResultAdmin
from django_celery_results.models import GroupResult, TaskResult
from smart_selects.db_fields import ChainedForeignKey
from smart_selects.widgets import ChainedSelect
from unfold import admin as unfold_admin
from unfold.contrib.forms.widgets import ArrayWidget
from unfold.mixins.nested_inlines_model_admin import NestedInlinesModelAdminMixin
from unfold.widgets import SELECT_CLASSES, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget


class UnfoldChainedSelect(ChainedSelect):
    template_name = 'unfold/widgets/select.html'

    def __init__(self, *args, **kwargs):
        if 'attrs' not in kwargs:
            kwargs['attrs'] = {}

        attrs = kwargs['attrs']
        attrs['class'] = ' '.join([*SELECT_CLASSES, attrs.get('class', '') if attrs else ''])

        super().__init__(*args, **kwargs)


class ChainedForeignKeySupportMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if isinstance(db_field, ChainedForeignKey):
            widget = UnfoldChainedSelect(
                to_app_name=db_field.to_app_name,
                to_model_name=db_field.to_model_name,
                chained_field=db_field.chained_field,
                chained_model_field=db_field.chained_model_field,
                foreign_key_app_name=db_field.model._meta.app_label,
                foreign_key_model_name=db_field.model._meta.object_name,
                foreign_key_field_name=db_field.name,
                show_all=db_field.show_all,
                auto_choose=db_field.auto_choose,
                sort=db_field.sort,
                view_name=db_field.view_name,
            )
            kwargs['widget'] = widget

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class UnfoldModelAdmin(ChainedForeignKeySupportMixin, unfold_admin.ModelAdmin):
    compressed_fields = False
    formfield_overrides = {
        ArrayField: {
            'widget': ArrayWidget,
        }
    }


class UnfoldStackedInline(ChainedForeignKeySupportMixin, unfold_admin.StackedInline):
    collapsible = True


class UnfoldTabularInline(ChainedForeignKeySupportMixin, unfold_admin.TabularInline):
    pass


admin.site.unregister(PeriodicTask)
admin.site.unregister(IntervalSchedule)
admin.site.unregister(CrontabSchedule)
admin.site.unregister(SolarSchedule)
admin.site.unregister(ClockedSchedule)


class UnfoldTaskSelectWidget(UnfoldAdminSelectWidget, TaskSelectWidget):
    pass


class UnfoldPeriodicTaskForm(PeriodicTaskForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['task'].widget = UnfoldAdminTextInputWidget()
        self.fields['regtask'].widget = UnfoldTaskSelectWidget()


@admin.register(PeriodicTask)
class PeriodicTaskAdmin(BasePeriodicTaskAdmin, UnfoldModelAdmin):
    form = UnfoldPeriodicTaskForm


@admin.register(IntervalSchedule)
class IntervalScheduleAdmin(UnfoldModelAdmin):
    pass


@admin.register(CrontabSchedule)
class CrontabScheduleAdmin(BaseCrontabScheduleAdmin, UnfoldModelAdmin):
    pass


@admin.register(SolarSchedule)
class SolarScheduleAdmin(UnfoldModelAdmin):
    pass


@admin.register(ClockedSchedule)
class ClockedScheduleAdmin(BaseClockedScheduleAdmin, UnfoldModelAdmin):
    pass


admin.site.unregister(TaskResult)
admin.site.unregister(GroupResult)


@admin.register(TaskResult)
class TaskResultAdmin(BaseTaskResultAdmin, UnfoldModelAdmin):
    pass


@admin.register(GroupResult)
class GroupResultAdmin(BaseGroupResultAdmin, UnfoldModelAdmin):
    pass


# Monkey-patch build_nested_formsets to make it work with polymorphic inlines
def _patched_build_nested_formsets(self, request, obj, formsets, inline_instances, change):
    from unfold.admin import TabularInline

    for formset, inline in zip(formsets, inline_instances):
        for form in formset.forms:
            nested_formsets = []

            if not hasattr(inline, 'inlines'):
                continue

            for inline_class in inline.inlines:
                inline_formset = self._get_nested_formset(request, obj, form, inline, inline_class, change)

                if not inline_formset:
                    continue

                inline_formset.inline_type = 'stacked'
                if issubclass(inline_class, TabularInline):
                    inline_formset.inline_type = 'tabular'

                nested_formsets.append(inline_formset)
                self.nested_formset_media += inline_formset.media

            form.nested_formsets = nested_formsets

        has_empty_forms = hasattr(formset, 'empty_forms') and formset.empty_forms
        has_empty_form = not has_empty_forms and hasattr(formset, 'empty_form')
        if (
            (has_empty_forms or has_empty_form)
            and hasattr(inline, 'inlines')
            and inline.has_add_permission(request, obj)
        ):
            formset.form.nested_formsets = []

            template_form = formset.empty_forms[0] if has_empty_forms else formset.empty_form

            for inline_class in inline.inlines:
                inline_formset = self._get_nested_formset(request, obj, template_form, inline, inline_class, change)

                if not inline_formset:
                    continue

                inline_formset.inline_type = 'stacked'
                if issubclass(inline_class, TabularInline):
                    inline_formset.inline_type = 'tabular'

                formset.form.nested_formsets.append(inline_formset)
                self.nested_formset_media += inline_formset.media


NestedInlinesModelAdminMixin._build_nested_formsets = _patched_build_nested_formsets

from django import forms
from django.core.exceptions import ValidationError

from ckeditor_uploader.widgets import CKEditorUploadingWidget

from tournament.models import Achievements

from .models import NewComment, Post, Profile


class NewCommentForm(forms.ModelForm):
    body = forms.CharField(label='Комментарий', widget=CKEditorUploadingWidget(config_name='comment'), required=True)

    class Meta:
        model = NewComment
        fields = ('body',)


class EditCommentForm(forms.ModelForm):
    edit_body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='comment'), required=True)

    class Meta:
        model = NewComment
        fields = ('edit_body',)


class EditProfileForm(forms.ModelForm):
    remove_bg = forms.BooleanField(label='Удалить фон', required=False)

    class Meta:
        model = Profile
        fields = (
            'about',
            'born_date',
            'avatar',
            'avatar_frame',
            'city',
            'vk',
            'discord',
            'telegram',
            'commentable',
            'remove_bg',
            'favourite_teams',
            'favourite_players',
            'tag',
            'favorite_achievements',
        )
        widgets = {
            'favorite_achievements': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, can_use_premium_features: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_use_premium_features:
            avatar_frame_field = self.fields['avatar_frame']
            tag_field = self.fields['tag']
            avatar_frame_field.disabled = True
            tag_field.disabled = True

        # Filter achievements to only show those the user has earned
        if self.instance and self.instance.name:
            user_achievements = Achievements.objects.filter(player__name=self.instance.name).select_related('category')
            self.fields['favorite_achievements'].queryset = user_achievements
            self.fields['favorite_achievements'].help_text = 'Выберите до 5 достижений для отображения в комментариях'
        else:
            self.fields['favorite_achievements'].queryset = Achievements.objects.none()

    def clean_favorite_achievements(self):
        achievements = self.cleaned_data.get('favorite_achievements')
        if achievements and len(achievements) > 5:
            raise ValidationError('Можно выбрать не более 5 достижений.')
        return achievements


class PostForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='default'))
    description = forms.CharField(
        label='Краткое описание',
        widget=forms.Textarea(attrs={'rows': 3, 'maxlength': 150}),
        required=False,
        help_text='Краткое описание содержимого поста для превью (максимум 150 символов)',
    )

    class Meta:
        model = Post
        fields = ('title', 'body', 'description', 'preview_cover')

from django import forms
from django.core.exceptions import ValidationError

from ckeditor_uploader.widgets import CKEditorUploadingWidget

from tournament.models import Medal

from .models import FavoriteMedal, NewComment, Post, Profile


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
    favorite_medals = forms.ModelMultipleChoiceField(
        label='Избранные достижения',
        queryset=Medal.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text='Выберите до 5 достижений для отображения в комментариях',
    )

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
            'favorite_medals',
        )

    def __init__(self, *args, can_use_premium_features: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_use_premium_features:
            avatar_frame_field = self.fields['avatar_frame']
            tag_field = self.fields['tag']
            avatar_frame_field.disabled = True
            tag_field.disabled = True

        if self.instance and self.instance.name:
            player = getattr(self.instance.name, 'user_player', None)
            if player:
                self.fields['favorite_medals'].queryset = Medal.objects.filter(
                    player_medals__player=player
                ).select_related('medal_type')
                if not self.is_bound:
                    self.initial['favorite_medals'] = self.instance.favorite_medals.values_list('medal_id', flat=True)

    def clean_favorite_medals(self):
        medals = self.cleaned_data.get('favorite_medals')
        if medals and len(medals) > 5:
            raise ValidationError('Можно выбрать не более 5 достижений.')
        return medals

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            selected_medals = self.cleaned_data['favorite_medals']
            profile.favorite_medals.exclude(medal__in=selected_medals).delete()
            FavoriteMedal.objects.bulk_create(
                [
                    FavoriteMedal(profile=profile, medal=medal)
                    for medal in selected_medals
                    if not profile.favorite_medals.filter(medal=medal).exists()
                ]
            )
        return profile


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

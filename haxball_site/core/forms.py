from django import forms

from ckeditor_uploader.widgets import CKEditorUploadingWidget

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
        )

    def __init__(self, *args, can_use_premium_features: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_use_premium_features:
            avatar_frame_field = self.fields['avatar_frame']
            tag_field = self.fields['tag']
            avatar_frame_field.disabled = True
            tag_field.disabled = True


class PostForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='default'))

    class Meta:
        model = Post
        fields = ('title', 'body')

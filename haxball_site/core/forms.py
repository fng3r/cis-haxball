from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms

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
        fields = ('about', 'born_date', 'avatar', 'city', 'vk', 'discord', 'telegram', 'commentable', 'remove_bg')


class PostForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='default'))

    class Meta:
        model = Post
        fields = ('title', 'body')

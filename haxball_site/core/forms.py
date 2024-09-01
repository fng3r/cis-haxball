from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms

from .models import NewComment, Post, Profile


class NewCommentForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='comment'))

    class Meta:
        model = NewComment
        fields = ('body',)


class EditProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('about', 'born_date', 'avatar', 'city', 'vk', 'discord', 'telegram', 'commentable')


class PostForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='default'))

    class Meta:
        model = Post
        fields = ('title', 'body')

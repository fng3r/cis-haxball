import json
from datetime import datetime

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.generic import ListView, DetailView
from django.views.generic.base import View
from pytils.translit import slugify

from .forms import EditProfileForm, PostForm, NewCommentForm
from .models import Post, Profile, LikeDislike, Category, Themes, NewComment, UserNicknameHistoryItem
from .templatetags.user_tags import can_edit, exceeds_edit_limit
from .utils import get_comments_for_object, get_paginated_comments
from tournament.models import Team, Achievements



# Вьюха для списка постов
class PostListView(ListView):
    queryset = Post.objects \
        .select_related('category', 'author__user_profile') \
        .prefetch_related('comments', 'votes') \
        .filter(category__is_official=True) \
        .order_by('-important', '-publish',)
    context_object_name = 'posts'
    paginate_by = 7
    template_name = 'core/post/list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        count_imp = Post.objects.filter(category__is_official=True, important=True).count()
        context['count_imp'] = count_imp

        return context


# Смотреть все новости
class AllPostView(ListView):
    queryset = Post.objects.filter(category__is_official=True).order_by('-created')
    context_object_name = 'posts'
    paginate_by = 7
    template_name = 'core/post/all_posts_list.html'


# Вьюха для трансляций
class LivesView(ListView):
    try:
        category = Category.objects.get(slug='live')
    except:
        category = None
    queryset = Post.objects.filter(category=category)
    context_object_name = 'posts'
    paginate_by = 6
    template_name = 'core/lives/lives_list.html'


def anime_view(request):
    return render(request, 'core/anime/marat_anime.html')


# Главная форума тута
class ForumView(ListView):
    queryset = Themes.objects.all()
    context_object_name = 'themes'
    template_name = 'core/forum/forum_main.html'


# Вьюха для списка постов в категории форума
class CategoryListView(DetailView):
    model = Category
    template_name = 'core/forum/post_list_in_category.html'
    context_name = 'category'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post_list = self.object.posts_in_category.annotate(
            last_activity=Coalesce(Max('comments__created'), 'created')).order_by('-last_activity')

        paginat = Paginator(post_list, 6)
        page = self.request.GET.get('page')

        try:
            posts = paginat.page(page)
        except PageNotAnInteger:
            # If page is not an integer deliver the first page
            posts = paginat.page(1)
        except EmptyPage:
            # If page is out of range deliver last page of results
            posts = paginat.page(paginat.num_pages)

        context['posts'] = posts
        context['page'] = page

        return context


# post-create view
def post_new(request, slug):
    category = Category.objects.get(slug=slug)
    if request.method == 'POST':
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.category = category
            post.slug = slugify(post.title)
            post.created = datetime.now()
            post.save()
            return redirect(category.get_absolute_url())
    else:
        form = PostForm()
    return render(request, 'core/forum/add_post.html', {'form': form, 'category': category})


# post-edit view
def post_edit(request, slug, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == 'POST':
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.save()
            return redirect(post.get_absolute_url())
    else:
        if request.user == post.author or request.user.is_superuser:
            form = PostForm(instance=post)
        else:
            return HttpResponse('Ошибка доступа')
    return render(request, 'core/forum/add_post.html', {'form': form})


# edit comment
def comment_edit(request, pk):
    comment = get_object_or_404(NewComment, pk=pk)
    obj = comment.content_type.get_object_for_this_type(pk=comment.object_id)
    if not request.user.is_superuser:
        if request.user != comment.author:
            return HttpResponse('Ошибка доступа')

        if not can_edit(comment):
            return HttpResponse('Время на редактирование комментария истекло')

        if exceeds_edit_limit(comment):
            return HttpResponse('Достигнут лимит на количество изменений комментария')

    if request.method == 'POST':
        form = NewCommentForm(request.POST, instance=comment)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.save()
            return redirect(obj.get_absolute_url())
        else:
            comment.delete()
            return redirect(obj.get_absolute_url())
    else:
        form = NewCommentForm(instance=comment)

    return render(request, 'core/post/edit_comment.html', {'comment_form': form})


# Удаление комментария
def delete_comment(request, pk):
    comment = get_object_or_404(NewComment, pk=pk)
    obj = comment.content_object
    if request.method == 'POST' and \
            ((request.user == comment.author and timezone.now() - comment.created < timezone.timedelta(
                minutes=10)) or request.user.is_superuser or request.user == obj.name):
        comment.delete()
        return redirect(obj.get_absolute_url())
    else:
        return HttpResponse('Ошибка доступа или время истекло')


# Вьюха для фасткапов
class FastcupView(ListView):
    try:
        category = Category.objects.get(slug='fastcups')
    except:
        category = None
    queryset = Post.objects.filter(category=category).order_by('-created')
    context_object_name = 'posts'
    paginate_by = 6
    template_name = 'core/fastcups/fastcups_list.html'


# Список админов
class AdminListView(ListView):
    us = User.objects.filter(is_staff=True).order_by('id')
    a = []
    for i in us:
        s = 0

        for icon in i.user_profile.user_icon.all():
            s += icon.priority
        if s > 0:
            a.append([i, s, i.id])

    c = sorted(a, key=lambda x: x[1], reverse=True)
    
    queryset = [i[0] for i in c]
    context_object_name = 'users'
    template_name = 'core/admins/admin_list.html'


# Вьюха для турниров
class TournamentsView(ListView):
    try:
        category = Category.objects.get(slug='tournaments')
    except:
        category = None
    queryset = Post.objects.filter(category=category)
    context_object_name = 'posts'
    paginate_by = 6
    template_name = 'core/tournaments/tournaments_list.html'


class PostDetailView(DetailView):
    model = Post
    context_object_name = 'post'
    template_name = 'core/post/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = context['post']
        post.views = post.views + 1
        post.save()

        page = self.request.GET.get('page')
        comments_obj = get_comments_for_object(Post, post.id)
        comments = get_paginated_comments(comments_obj, page)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form
        return context


# Вьюха для профиля пользователя MultipleObjectMixin
class ProfileDetail(DetailView):
    model = Profile
    context_object_name = 'profile'
    template_name = 'core/profile/profile_detail.html'

    def get_queryset(self):
        return super().get_queryset().select_related('name__user_player__team')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = context['profile']
        profile.views = profile.views + 1
        profile.save()

        page = self.request.GET.get('page')
        comments_obj = get_comments_for_object(Profile, profile.id)
        comments = get_paginated_comments(comments_obj, page)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form

        all_achievements = Achievements.objects.select_related('category').filter(player__name=profile.name)
        achievements_by_category = {}
        for achievement in all_achievements:
            category = 'Без категории'
            if achievement.category:
                category = achievement.category.title
            if category not in achievements_by_category:
                achievements_by_category[category] = list()
            achievements_by_category[category].append(achievement)
        context['achievements_by_category'] = achievements_by_category.items()
        context['previous_nicknames'] = UserNicknameHistoryItem.objects.filter(user=profile.name).order_by('-edited')

        return context


class AddCommentView(View):
    model = None

    def post(self, request, pk):
        obj = self.model.objects.get(id=pk)
        if request.method == 'POST':
            comment_form = NewCommentForm(data=request.POST)
            new_com = comment_form.save(commit=False)
            if request.POST.get("parent", None):
                new_com.parent_id = int(request.POST.get('parent'))
            new_com.object_id = obj.id
            new_com.author = request.user
            new_com.content_type = ContentType.objects.get_for_model(obj)
            new_com.save()
            return redirect(obj.get_absolute_url())


class EditMyProfile(DetailView, View):
    model = Profile
    context_object_name = 'profile'
    template_name = 'core/profile/profile_edit.html'

    def post(self, request, pk, slug):
        profile = Profile.objects.get(slug=slug, id=pk)
        profile_form = EditProfileForm(request.POST, instance=profile)
        if profile_form.is_valid():
            if 'avatar' in request.FILES:
                profile.avatar = request.FILES['avatar']
            if 'background' in request.FILES:
                profile.background = request.FILES['background']
            if request.POST.get('bg-removed') == 'on':
                profile.background = None
            profile_form.save()
        return redirect(profile.get_absolute_url())


class VotesView(View):
    model = None  # Модель данных - Статьи или Комментарии
    vote_type = None  # Тип комментария Like/Dislike

    def post(self, request, id):
        obj = self.model.objects.get(id=id)
        author_profile = obj.author.user_profile
        # GenericForeignKey не поддерживает метод get_or_create
        try:
            likedislike = LikeDislike.objects.get(content_type=ContentType.objects.get_for_model(obj), object_id=obj.id,
                                                  user=request.user)

            if likedislike.vote is not self.vote_type:

                if obj.author != request.user:
                    author_profile.karma -= likedislike.vote
                    author_profile.karma += self.vote_type
                    author_profile.save(update_fields=['karma'])

                likedislike.vote = self.vote_type
                likedislike.save(update_fields=['vote'])
                result = True
            else:
                # if obj.author != request.user:
                #    author_profile.karma -= likedislike.vote
                #    author_profile.save(update_fields=['karma'])
                likedislike.delete()
                result = False

        except LikeDislike.DoesNotExist:
            obj.votes.create(user=request.user, vote=self.vote_type)
            if obj.author != request.user:
                obj.author.user_profile.karma += self.vote_type
                obj.author.user_profile.save(update_fields=['karma'])
            result = True

        return HttpResponse(
            json.dumps({
                "result": result,
                "like_count": obj.votes.likes().count(),
                "dislike_count": obj.votes.dislikes().count(),
                "sum_rating": obj.votes.sum_rating()
            }),
            content_type="application/json"
        )


def search_result(request):
    a = request.GET.get('q')
    profile_list = Profile.objects.filter(name__username__icontains=a)
    team_list = Team.objects.filter(title__icontains=a)
    post_list = Post.objects.filter(title__icontains=a)
    return render(request, 'core/search_result/search_result.html',
                  {'profiles': profile_list, 'teams': team_list, 'posts': post_list})

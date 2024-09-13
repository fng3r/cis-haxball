from django.contrib.auth.decorators import login_required
from django.urls import path
from tournament.models import League, Match

from . import views
from .models import LikeDislike, NewComment, Post, Profile

app_name = 'core'

urlpatterns = [
    path('', views.PostListView.as_view(), name='home'),
    path('post/<int:pk>/<slug:slug>', views.PostDetailView.as_view(), name='post_detail'),
    path('profile/<int:pk>/<slug:slug>/', views.ProfileDetail.as_view(), name='profile_detail'),
    path('profile/<slug:slug>/<int:pk>/edit', views.EditProfile.as_view(), name='edit_profile'),
    path('anime/', views.anime_view, name='anime'),
    #  Путь к фасткапам
    path('fastcups/', views.FastcupView.as_view(), name='fastcups'),
    path('filter/', views.search_result, name='filter'),
    #  Путь к турнирам
    path('tournaments/', views.TournamentsView.as_view(), name='tournaments'),
    #  Путь к админам
    path('admin_list/', views.AdminListView.as_view(), name='admins'),
    #  Все посты
    path('news_all/', views.AllPostView.as_view(), name='all_posts'),
    #  Путь к трансляциям
    path('lives/', views.LivesView.as_view(), name='lives'),
    #  Путь на форум
    path('forum/', views.ForumView.as_view(), name='forum'),
    path('forum/<slug:slug>', views.CategoryListView.as_view(), name='forum_category'),
    # Ссылка на создание нового поста на форуме
    path('forum/<slug:slug>/add_post', views.post_new, name='new_post'),
    path('comments/<int:ct>/<int:pk>', views.CommentsListView.as_view(), name='comments'),
    path('comment/<int:pk>', views.get_comment, name='comment'),
    # Создание нового комментария
    path('add_comment/<int:ct>/<int:pk>', views.AddCommentView.as_view(), name='add_comment'),
    # Редактирование комментария
    path('post/edit_comment/<int:pk>', views.EditCommentView.as_view(), name='edit_comment'),
    # Удаление комментария
    path('delete_comment/<int:pk>', views.delete_comment, name='delete_comment'),
    # Редактирование поста, если создан пользователем
    path('post/<slug:slug>/<int:pk>/edit', views.post_edit, name='post_edit'),
    # Путь на самописный апи для обработку лайка/дизлайка ПОСТА через Ажакс-запрос
    path(
        'api/post/<int:id>/like/',
        login_required(views.VotesView.as_view(model=Post, vote_type=LikeDislike.LIKE)),
        name='post_like',
    ),
    path(
        'api/post/<int:id>/dislike/',
        login_required(views.VotesView.as_view(model=Post, vote_type=LikeDislike.DISLIKE)),
        name='post_dislike',
    ),
    path(
        'api/comment/<int:id>/like/',
        login_required(views.VotesView.as_view(model=NewComment, vote_type=LikeDislike.LIKE)),
        name='comment_like',
    ),
    path(
        'api/comment/<int:id>/dislike/',
        login_required(views.VotesView.as_view(model=NewComment, vote_type=LikeDislike.DISLIKE)),
        name='comment_dislike',
    ),
]

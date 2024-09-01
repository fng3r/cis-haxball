import collections

from autoslug import AutoSlugField
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Max, Sum
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from model_utils import FieldTracker


class MyQuerySet(models.query.QuerySet):
    def delete(self):
        for obj in self:
            obj.delete()


# Менеджер модели лайк-дизлайк
class LikeDislikeManager(models.Manager):
    use_for_related_fields = True

    def likes(self):
        # Забираем queryset с записями больше 0
        return self.get_queryset().filter(vote__gt=0)

    def dislikes(self):
        # Забираем queryset с записями меньше 0
        return self.get_queryset().filter(vote__lt=0)

    def sum_rating(self):
        # Забираем суммарный рейтинг
        return self.get_queryset().aggregate(Sum('vote')).get('vote__sum') or 0

    def posts(self):
        return self.get_queryset().filter(content_type__model='post').order_by('-posts__pub_date')

    def comments(self):
        return self.get_queryset().filter(content_type__model='comment').order_by('-comments__pub_date')

    def get_queryset(self):
        return MyQuerySet(self.model, using=self._db)


# Модель для лайк-дизлайк системы
class LikeDislike(models.Model):
    LIKE = 1
    DISLIKE = -1

    VOTES = ((DISLIKE, 'Не нравится'), (LIKE, 'Нравится'))

    vote = models.SmallIntegerField(verbose_name='Голос', choices=VOTES)
    user = models.ForeignKey(User, verbose_name='Пользователь', on_delete=models.CASCADE)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    objects = LikeDislikeManager()

    def delete(self, *args, **kwargs):
        if self.user != self.content_object.author:
            self.content_object.author.user_profile.karma -= self.vote
            self.content_object.author.user_profile.save(update_fields=['karma'])
        super(LikeDislike, self).delete(*args, **kwargs)

    def get_query_set(self):
        return MyQuerySet(self.model)

    class Meta:
        verbose_name = 'Лайк/дизлайк голос'
        verbose_name_plural = 'Лайк/дизлайк голоса'


# Огромный раздел форума в котором категории создаются админами
class Themes(models.Model):
    title = models.CharField('Тема', max_length=256)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Раздел форума'
        verbose_name_plural = 'Разделы форума'


# Модель для категории поста(Новость, Фасткап, Регламент, Турнир, Трансляция, Архив, общение...)
# Это также секции форума, в которых можно публиковать посты, поэтому доступно описание, если тема
# неофицальная, ставим ис-оффишл НОУ и пишем описание, привязываем к теме форума
class Category(models.Model):
    title = models.CharField('Категория', max_length=256)
    slug = models.SlugField(max_length=250, unique=True)
    description = models.TextField('Описание категории', blank=True)
    is_official = models.BooleanField(default=True, verbose_name='Официальная')
    theme = models.ForeignKey(
        Themes,
        verbose_name='Тема на форуме',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='category_in_theme',
    )

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('core:forum_category', args=[self.slug])

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'


# Модель для "правильных" комментариев
class NewComment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()
    author = models.ForeignKey(User, verbose_name='Автор', related_name='n_comments_by_user', on_delete=models.CASCADE)
    body = models.TextField('Текст комментария')
    created = models.DateTimeField('Создан', default=timezone.now)
    edited = models.DateTimeField('Изменен', blank=True, null=True)
    parent = models.ForeignKey(
        'self', verbose_name='Родитель', on_delete=models.SET_NULL, blank=True, null=True, related_name='childs'
    )
    votes = GenericRelation(LikeDislike, related_query_name='n_comments')
    version = models.PositiveSmallIntegerField('Версия', default=1)

    tracker = FieldTracker()

    class Meta:
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'
        ordering = ('-created',)

    def save(self, *args, **kwargs):
        if self.pk and self.tracker.has_changed('body'):
            self.edited = timezone.now()
            self.version = self.tracker.previous('version') + 1
        super(NewComment, self).save(*args, **kwargs)

    def __str__(self):
        return 'Комментарий от {} к {}'.format(self.author, self.content_object)

    def get_absolute_url(self):
        if self.parent:
            return self.get_root().get_absolute_url()

        commented_object = self.content_object
        top_level_comments = list(self.content_object.comments.filter(parent=None))
        index = top_level_comments.index(self)
        page = (index // 25) + 1
        return '{}?page={}#r{}'.format(commented_object.get_absolute_url(), page, self.id)

    def get_root(self):
        obj = self
        while obj.parent is not None:
            obj = obj.parent
        return obj

    def is_parent(self):
        return self.parent is None

    def has_childs(self):
        return self.childs.count() > 0

    def all_childs(self):
        return sorted(list(bfs(self)), key=lambda x: x.created)

    def childs_count(self):
        return len(list(bfs(self)))


class CommentHistoryItem(models.Model):
    body = models.TextField('Текст комментария')
    created = models.DateTimeField('Дата')
    comment = models.ForeignKey(
        NewComment, verbose_name='Базовый комментарий', on_delete=models.CASCADE, related_name='comment_history'
    )
    version = models.PositiveSmallIntegerField('Версия', default=1)

    class Meta:
        verbose_name = ''
        verbose_name_plural = 'История комментариев'
        ordering = (
            '-comment__id',
            '-created',
        )

    @receiver(post_save, sender=NewComment)
    def create_comment_history_item(sender, instance, created, **kwargs):
        if not created and instance.tracker.has_changed('body'):
            previous_created = instance.tracker.previous('edited') or instance.created
            previous_comment = instance.tracker.previous('body')
            previous_version = instance.tracker.previous('version')
            CommentHistoryItem(
                body=previous_comment, created=previous_created, comment=instance, version=previous_version
            ).save()

    def __str__(self):
        return 'Версия комментария #{}'.format(self.version)


# Модель для поста
class Post(models.Model):
    title = models.CharField('Заголовок', max_length=256)
    category = models.ForeignKey(
        Category,
        verbose_name='Категория поста',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='posts_in_category',
    )
    author = models.ForeignKey(User, verbose_name='Автор', on_delete=models.CASCADE, related_name='blog_posts')
    slug = models.SlugField(max_length=250)
    body = models.TextField('Текст поста')
    publish = models.DateTimeField('Время публикации', default=timezone.now)
    created = models.DateTimeField('Создано', auto_now_add=True)
    updated = models.DateTimeField('Изменено', auto_now=True)
    important = models.BooleanField('Закрепленный пост', default=False)
    votes = GenericRelation(LikeDislike, related_query_name='posts')
    views = models.PositiveIntegerField(default=0)
    commentable = models.BooleanField('Комментируемая запись', default=True)
    comments = GenericRelation(NewComment, related_query_name='post_comments')

    def get_absolute_url(self):
        return reverse('core:post_detail', args=[self.id, self.slug])

    def last_comment(self):
        return self.comments.annotate(Max('created'))

    def __str__(self):
        return '{}: {}'.format(self.category, self.title)

    class Meta:
        verbose_name = 'Пост'
        verbose_name_plural = 'Посты'
        ordering = ('-created',)


# Модель для комментария
class Comment(models.Model):
    post = models.ForeignKey(Post, verbose_name='Место', on_delete=models.CASCADE, related_name='post_old_comments')
    author = models.ForeignKey(User, verbose_name='Автор', related_name='comments_by_user', on_delete=models.CASCADE)
    body = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        'self', verbose_name='Родитель', on_delete=models.SET_NULL, blank=True, null=True, related_name='childs'
    )
    votes = GenericRelation(LikeDislike, related_query_name='comments')

    class Meta:
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'
        ordering = ('-created',)

    def __str__(self):
        return 'Комментарий от {} к {}'.format(self.author, self.post.title)

    def is_parent(self):
        return self.parent is None

    def has_childs(self):
        return self.childs.count() > 0

    def all_childs(self):
        return sorted(list(bfs(self)), key=lambda x: x.created)

    def childs_count(self):
        return len(list(bfs(self)))


# Обход графа в ширину хе-хе, хоть где-то пригодилось)
def bfs(root):
    visited = set()
    queue = collections.deque([root])
    while queue:
        vertex = queue.popleft()
        for neighbour in vertex.childs.all():
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return visited


# Модель ip-адресов пользователя
class IPAdress(models.Model):
    name = models.ForeignKey(
        User, verbose_name='Пользователь', related_name='user_ips', on_delete=models.SET_NULL, null=True
    )
    ip = models.GenericIPAddressField()
    created = models.DateTimeField('Первый заход', auto_now_add=True)
    update = models.DateTimeField('Последний заход', default=timezone.now)
    suspicious = models.BooleanField('Подозрительный', default=False)

    def __str__(self):
        return '({}, {})'.format(self.name, self.ip)

    class Meta:
        verbose_name = 'IP-Адрес'
        verbose_name_plural = 'IP-Адреса'


class UserActivity(models.Model):
    user = models.ForeignKey(User, verbose_name='Пользователь', on_delete=models.CASCADE)
    ip = models.GenericIPAddressField('IP-адрес')
    user_agent = models.CharField(max_length=200, verbose_name='User-Agent')
    id_token = models.CharField(max_length=32, verbose_name='IdToken')
    first_seen = models.DateTimeField('Первый заход', auto_now_add=True)
    last_seen = models.DateTimeField('Последний заход', auto_now_add=True)
    has_duplicates = models.BooleanField('Есть дубликаты', default=False)

    class Meta:
        verbose_name = 'Пользовательская активность'
        verbose_name_plural = 'Пользовательская активность'


# Модель для профиля пользователя
class Profile(models.Model):
    name = models.OneToOneField(
        User, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='user_profile'
    )
    slug = AutoSlugField(always_update=True, populate_from='name')
    avatar = models.ImageField('Аватар', upload_to='users_avatars/', default='users_avatars/default/default.png')
    background = models.ImageField('Фон профиля', upload_to='users_background/', blank=True, null=True)
    born_date = models.DateField('Дата рождения', blank=True, null=True)
    about = models.TextField(max_length=1000, blank=True)
    city = models.CharField(max_length=100, blank=True)
    vk = models.CharField(max_length=100, blank=True)
    telegram = models.CharField(max_length=100, blank=True)
    discord = models.CharField(max_length=100, blank=True)
    views = models.PositiveIntegerField(default=0)
    karma = models.SmallIntegerField(default=0)
    comments = GenericRelation(NewComment, related_query_name='profile_comments')
    commentable = models.BooleanField('Комментируемый профиль', default=True)
    can_vote = models.BooleanField('Может голосовать', default=True)
    can_comment = models.BooleanField('Может комментировать', default=True)

    @receiver(post_save, sender=User)
    def create_user_profile(sender, instance, created, **kwargs):
        if created:
            Profile.objects.create(name=instance)

    @receiver(post_save, sender=User)
    def save_user_profile(sender, instance, **kwargs):
        instance.user_profile.save()

    def get_absolute_url(self):
        return reverse('core:profile_detail', args=[self.id, self.slug])

    def __str__(self):
        return 'Профиль {}'.format(self.name.username)

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'


class UserIcon(models.Model):
    title = models.CharField('Название', max_length=256)
    priority = models.SmallIntegerField(
        default=1,
    )
    description = models.CharField('Описание(при наведении)', max_length=100, blank=True)
    image = models.ImageField('Иконка', upload_to='user_icon/', blank=True, null=True)
    user = models.ManyToManyField(Profile, related_name='user_icon', blank=True, null=True)

    class Meta:
        verbose_name = 'Иконка'
        verbose_name_plural = 'Иконки'


class UserNicknameHistoryItem(models.Model):
    user = models.ForeignKey(User, verbose_name='Пользователь', on_delete=models.CASCADE)
    nickname = models.CharField(verbose_name='Никнейм', max_length=50)
    edited = models.DateTimeField('Дата смены', default=timezone.now)

    class Meta:
        verbose_name = 'История никнеймов'
        verbose_name_plural = 'История никнеймов'

    @receiver(pre_save, sender=User)
    def create_history_item(sender, instance, **kwargs):
        previous_instance = User.objects.filter(pk=instance.pk).first()
        if previous_instance is None:
            return

        if previous_instance.username != instance.username:
            UserNicknameHistoryItem.objects.create(user=instance, nickname=previous_instance.username)


class SubscriptionQuerySet(models.QuerySet):
    def by_user(self, user):
        return self.filter(user=user)

    def active(self):
        now = timezone.now()
        return self.filter(disabled=False, starts_at__lte=now, expires_at__gte=now)


class Subscription(models.Model):
    TIER_1 = 1
    TIER_2 = 2

    TIERS = ((TIER_1, 'Tier 1'), (TIER_2, 'Tier 2'))

    user = models.ForeignKey(
        User, verbose_name='Пользователь', related_name='subscriptions', on_delete=models.SET_NULL, null=True
    )
    starts_at = models.DateTimeField('Дата начала', default=timezone.now)
    expires_at = models.DateTimeField('Дата окончания')
    tier = models.PositiveSmallIntegerField('Тир подписки', choices=TIERS, default=TIER_1)
    disabled = models.BooleanField('Отключена', default=False)

    objects = SubscriptionQuerySet.as_manager()

    def is_active(self):
        now = timezone.now()
        return not self.disabled and self.starts_at <= now <= self.expires_at

    class Meta:
        ordering = ['-starts_at']
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'

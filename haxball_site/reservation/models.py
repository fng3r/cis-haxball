from django.contrib.auth.models import User
from django.db import models
from tournament.models import Match


# Create your models here.
class ReservationHost(models.Model):
    name = models.CharField('Название хоста', max_length=256)
    link = models.URLField('Адрес')
    is_active = models.BooleanField('Активный')

    def __str__(self):
        return f'{self.name}'

    class Meta:
        verbose_name = 'Хост'
        verbose_name_plural = 'Хосты'
        ordering = ['id']


class ReservationEntry(models.Model):
    author = models.ForeignKey(
        User, verbose_name='Автор заявки', on_delete=models.CASCADE, related_name='user_reservation_authors'
    )
    match = models.OneToOneField(
        Match, verbose_name='Матч', on_delete=models.CASCADE, related_name='match_reservation'
    )
    time_date = models.DateTimeField('Дата и время')

    host = models.ForeignKey(ReservationHost, verbose_name='Хост', on_delete=models.SET_NULL, null=True)
    created = models.DateTimeField('Когда создана', auto_now_add=True)
    
    cancelled_at = models.DateTimeField('Когда отменена', null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        verbose_name='Кем отменена', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cancelled_reservations'
    )

    def __str__(self):
        return f'Бронь матча {self.match} на {self.time_date.astimezone()}'

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None

    class Meta:
        verbose_name = 'Бронь хоста'
        verbose_name_plural = 'Брони хоста'
        ordering = ['-time_date']


class Replay(models.Model):
    name = models.CharField(verbose_name='Название реплея', max_length=256)
    description = models.TextField(verbose_name='Описание', blank=True, null=True)
    file = models.FileField(
        upload_to='hbr',
    )
    author = models.ForeignKey(
        User, verbose_name='Выложил', on_delete=models.SET_NULL, null=True, related_name='uploaded_replays'
    )
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Реплей {self.name} от {self.author}'

    class Meta:
        verbose_name = 'Реплей'
        verbose_name_plural = 'Реплеи'
        ordering = ['-created']

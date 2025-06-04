from django.contrib.auth.models import User
from django.db import models

from tournament.models import Match


# Create your models here.
class ReservationHost(models.Model):
    name = models.CharField('Название хоста', max_length=256)
    codename = models.CharField('Кодовое название', max_length=16)
    link = models.URLField('Адрес')
    is_active = models.BooleanField('Активный')

    def __str__(self):
        return f'{self.name}'

    class Meta:
        verbose_name = 'Хост'
        verbose_name_plural = 'Хосты'
        ordering = ['id']


class ReservationEntry(models.Model):
    match = models.ForeignKey(Match, verbose_name='Матч', on_delete=models.CASCADE, related_name='match_reservations')
    author = models.ForeignKey(
        User, verbose_name='Автор заявки', on_delete=models.CASCADE, related_name='user_reservation_authors'
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
        related_name='cancelled_reservations',
    )
    is_cancelled = models.GeneratedField(
        verbose_name='Отменена',
        expression=models.Case(
            models.When(cancelled_at__isnull=False, then=True),
            default=False,
            output_field=models.BooleanField(),
        ),
        db_persist=True,
        output_field=models.BooleanField(),
    )

    def __str__(self):
        return (
            f'Бронь для матча {self.match.team_home.short_title} - {self.match.team_guest.short_title}'
            + f'на {self.time_date.strftime('%d.%m.%y %H:%M')}'
        )

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

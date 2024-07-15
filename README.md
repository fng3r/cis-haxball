# haxball
Blog-site with social component and tables for creating haxball championships 
[cis-haxball](https://cis-haxball.ru/)

## Запуск проекта

### Prerequisites
- [Python 3.12+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/) (в большинстве случаев устанавливается вместе с python; если этого не произошло, установить [вручную](https://pip.pypa.io/en/latest/installation/))
- [sqlite3](https://www3.sqlite.org/index.html)
- [postgres](https://www.postgresql.org/download/)
- Python IDE (например, [PyCharm Community Edition](https://www.jetbrains.com/pycharm/download/))

### Подготовка
- Настраиваем интерпретатор для проекта и создаем [venv](https://www.jetbrains.com/help/pycharm/creating-virtual-environment.html) 
  (в результате должна появиться директория venv в корне)
- Устанавливаем зависимости `pip install -r requirements/dev.txt'`
- `cd haxball_site`
- Заполняем настройками файл с конфигурацией - .env (шаблон можно взять из .env.example)
- Подготавливаем БД
  - `python manage.py makemigrations`
  - `python manage.py migrate`
- Создаем суперюзера `python manage.py createsuperuser`

### Запуск
Поднимаем development server
`python manage.py runserver`

### Troubleshooting
- Если при подготовке БД возникает ошибка `django.db.utils.OperationalError: no such table: auth_user`, попробуйте
  закомментировать строчку `path('', include('core.urls', namespace='core'))` в `haxball_site\urls.py`, затем прогнать миграции, а после включить ее обратно
- Если при регистрации на сайте вы видите ошибку `TypeError: SMTP.starttls() got an unexpected keyword argument 'keyfile'`,
  ее можно устранить [следующим образом](https://github.com/packtpublishing/django-4-by-example/issues/41)

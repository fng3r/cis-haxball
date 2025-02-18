# haxball
Blog-site with social component and tables for creating haxball championships 
[cis-haxball](https://cis-haxball.ru/)

## Разработка проекта

### Prerequisites
- [WSL](https://learn.microsoft.com/ru-ru/windows/wsl/install) (если разработка ведет под Windows)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Python 3.12+](https://www.python.org/downloads/) (можно установить через [uv](https://docs.astral.sh/uv/guides/install-python/))
- [PostgreSQL 14](https://www.postgresql.org/download/)
- Python IDE (например, [PyCharm Community Edition](https://www.jetbrains.com/pycharm/download/) или [VSCode](https://code.visualstudio.com/download))

### Подготовка
- Устанавливаем зависимости `uv sync`
- Заполняем настройками файл с конфигурацией - .env (шаблон можно взять из .env.example)
- `cd haxball_site`
- Подготавливаем БД
  - `python manage.py makemigrations`
  - `python manage.py migrate`
- Создаем суперюзера `python manage.py createsuperuser`

### Запуск
Поднимаем development server
`python manage.py runserver`

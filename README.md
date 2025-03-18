# [CIS-HAXBALL](https://cis-haxball.ru/)
Платформа для проведения турниров по игре [HaxBall](https://www.haxball.com/)

## Powered by 

![Python](https://img.shields.io/badge/Python-FFF?style=for-the-badge&logo=python&logoColor=FFF&color=3a76a7)
![Django](https://img.shields.io/badge/Django-000?style=for-the-badge&logo=django&color=0c4b33)
![PostgreSQL](https://img.shields.io/badge/Postgresql-2e6792?style=for-the-badge&logo=postgresql&logoColor=FFF)
![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-00BDFF?style=for-the-badge&logo=tailwindcss&logoColor=FFF)

## Разработка проекта

### Prerequisites
- [WSL](https://learn.microsoft.com/ru-ru/windows/wsl/install) (если разработка ведется под Windows)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Python 3.12+](https://www.python.org/downloads/) (можно установить через [uv](https://docs.astral.sh/uv/guides/install-python/))
- [PostgreSQL 14](https://www.postgresql.org/download/)
- [Node.js](https://nodejs.org/en/download/current)

### Подготовка
- Устанавливаем зависимости
  - `uv sync`
  - `cd tailwind && npm i`
- Заполняем настройками файл с конфигурацией - .env (шаблон можно взять из .env.example)
- `cd haxball_site`
- Подготавливаем БД
  - `python manage.py makemigrations`
  - `python manage.py migrate`
- Создаем суперюзера `python manage.py createsuperuser`

### Запуск
- Поднимаем development server - `python manage.py runserver`
- Параллельно запускаем [vite](https://vite.dev/) dev server для сборки Tailwind'а и автоматического обновления при изменении шаблонов - `cd tailwind && npn run dev`

import re
from dataclasses import dataclass, replace
from datetime import date

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import FavoriteMedal
from tournament.models import (
    AchievementCategory,
    Achievements,
    AwardNomination,
    League,
    LegacyMedalMapping,
    Medal,
    MedalCategory,
    MedalType,
    PlayerMedal,
    PlayerTransfer,
    Season,
    TeamAchievement,
    TeamMedal,
)

NOMINATIONS = {
    'игрок сезона': ('BEST_PLAYER', 'Игрок сезона'),
    'игрок cезона': ('BEST_PLAYER', 'Игрок сезона'),
    'нападающий сезона': ('BEST_STRIKER', 'Нападающий сезона'),
    'нападающий cезона': ('BEST_STRIKER', 'Нападающий сезона'),
    'опорник сезона': ('BEST_DEFENDER', 'Опорник сезона'),
    'опорник cезона': ('BEST_DEFENDER', 'Опорник сезона'),
    'вратарь сезона': ('BEST_GOALKEEPER', 'Вратарь сезона'),
    'капитан сезона': ('BEST_CAPTAIN', 'Капитан сезона'),
    'прорыв сезона': ('BREAKTHROUGH', 'Прорыв сезона'),
    'прогресс сезона': ('PROGRESS', 'Прогресс сезона'),
    'открытие сезона': ('DISCOVERY', 'Открытие сезона'),
    'новичок сезона': ('BEST_NEWCOMER', 'Новичок сезона'),
    'лидер сезона': ('BEST_LEADER', 'Лидер сезона'),
}

HONORARY = {
    'инспектор сезона': ('inspector', 'Инспектор'),
    'инспектор,': ('inspector', 'Инспектор'),
    'медиа-сотрудник': ('media_contributor', 'Медиа-сотрудник'),
    'дизайнер': ('designer', 'Дизайнер'),
    'петух года': ('rooster_of_year', 'Петух года'),
    'танос сезона': ('thanos_of_season', 'Танос сезона'),
    'рофлянка': ('roflyanka', 'Рофлянка'),
}

AUXILIARY_COMPETITIONS = {
    'турнир прогнозистов': ('predictions', 'Турнир прогнозистов'),
    'турнира прогнозистов': ('predictions', 'Турнир прогнозистов'),
    'fantasy league': ('fantasy_league', 'Fantasy League'),
    'arena reborn': ('arena_reborn', 'Arena Reborn'),
    'survival instinct': ('survival_instinct', 'Survival Instinct'),
    'кубка субботы': ('saturday_cup_rating', 'Рейтинг Кубка Субботы'),
    'slotcybercup': ('slotcybercup', 'SlotCyberCup'),
    'hax-premier trophy': ('hax_premier_trophy', 'Hax-Premier Trophy'),
    'copa del cis': ('copa_del_cis', 'Copa del CIS'),
    'евро-2024': ('euro_2024', 'ЕВРО-2024'),
    'leopards trophy': ('leopards_trophy', 'Leopards Trophy'),
    'лиги европы': ('europe_league', 'Лига Европы'),
}

STATISTIC_MEDAL_TITLES = {
    MedalType.Statistic.GOALS: {
        1: 'Золотой мяч',
        2: 'Серебряный мяч',
        3: 'Бронзовый мяч',
    },
    MedalType.Statistic.ASSISTS: {
        1: 'Золотая бутса',
        2: 'Серебряная бутса',
        3: 'Бронзовая бутса',
    },
    MedalType.Statistic.CLEAN_SHEETS: {
        1: 'Золотая перчатка',
        2: 'Серебряная перчатка',
        3: 'Бронзовая перчатка',
    },
}

PLACE_ORDER = {1: 0, 2: 10, 3: 20}

NOMINATION_ORDER = {
    'BEST_PLAYER': 300,
    'BEST_GOALKEEPER': 400,
    'BEST_DEFENDER': 500,
    'BEST_STRIKER': 600,
    'BEST_CAPTAIN': 700,
    'BEST_LEADER': 800,
    'BEST_NEWCOMER': 900,
    'BREAKTHROUGH': 1000,
    'DISCOVERY': 1100,
    'PROGRESS': 1200,
}

STATISTIC_ORDER = {
    MedalType.Statistic.GOALS: 1400,
    MedalType.Statistic.ASSISTS: 1500,
    MedalType.Statistic.CLEAN_SHEETS: 1600,
}

AUXILIARY_COMPETITION_ORDER = {
    'elo': 100,
    'predictions': 200,
    'arena_reborn': 300,
    'fantasy_league': 400,
    'survival_instinct': 500,
    'saturday_cup_rating': 600,
    'slotcybercup': 700,
    'hax_premier_trophy': 800,
    'copa_del_cis': 900,
    'euro_2024': 1000,
    'europe_league': 1100,
    'leopards_trophy': 1200,
}

AUXILIARY_VARIANT_ORDER = {
    '': 0,
    'classic_9': 0,
    'futsal': 30,
}

LEAGUE_SCOPE_ORDER = {
    League.Type.PREMIER_LEAGUE: 0,
    League.Type.FIRST_LEAGUE: 30,
    League.Type.SECOND_LEAGUE: 60,
    League.Type.CHAMPIONS_LEAGUE: 90,
}

CAREER_UNIT_ORDER = {
    MedalType.Unit.MATCHES: 0,
    MedalType.Unit.GOALS: 50,
    MedalType.Unit.ASSISTS: 100,
    MedalType.Unit.CLEAN_SHEETS: 150,
}

HONORARY_ORDER = {
    'best_inspector': 2000,
    'media_contributor': 2100,
    'designer': 2200,
    'rooster_of_year': 2300,
    'thanos_of_season': 2400,
    'roflyanka': 2500,
}

CUP_LEAGUE_ORDER = {
    League.Type.RUSSIAN_CUP: 0,
    League.Type.PREMIER_LEAGUE_CUP: 30,
    League.Type.FIRST_LEAGUE_CUP: 60,
    League.Type.SECOND_LEAGUE_CUP: 90,
    League.Type.LEAGUE_CUP: 120,
}


@dataclass(frozen=True)
class MedalDescriptor:
    code: str
    kind: str
    title: str
    place: int | None = None
    league_type: str | None = None
    statistic: str | None = None
    nomination_code: str | None = None
    nomination_name: str | None = None
    competition_code: str = ''
    variant: str = ''
    threshold: int | None = None
    unit: str = ''
    result_value: int | None = None
    season_ordinal: int | None = None
    season_type: str | None = None
    season_year: int | None = None
    edition: str = ''


@dataclass
class ImportReport:
    processed: int = 0
    classified: int = 0
    imported: int = 0
    already_mapped: int = 0
    skipped_unassigned: int = 0
    unresolved: list[str] = None
    import_errors: list[str] = None
    resolution_warnings: list[str] = None

    def __post_init__(self):
        if self.unresolved is None:
            self.unresolved = []
        if self.import_errors is None:
            self.import_errors = []
        if self.resolution_warnings is None:
            self.resolution_warnings = []


class LegacyMedalClassifier:
    def classify(self, achievement: Achievements | TeamAchievement) -> MedalDescriptor | None:
        text = f'{achievement.title} {achievement.description}'.lower().replace('ё', 'е').replace('cезона', 'сезона')
        place = self._place(text)
        league_type = self._league_type(text, achievement)
        season_ordinal, season_type, season_year = self._season(text, league_type)

        career = self._career(text)
        if career:
            unit, threshold, title = career
            return MedalDescriptor(
                code=f'career.{unit}.{threshold}',
                kind=MedalType.Kind.CAREER_MILESTONE,
                title=title,
                threshold=threshold,
                unit=unit,
            )

        for alias, (code, title) in NOMINATIONS.items():
            if alias in text:
                effective_place = place or (1 if 'v2.0' not in text else None)
                if not effective_place or not league_type:
                    return None
                return MedalDescriptor(
                    code=f'nomination.{code.lower()}.{league_type}.{effective_place}',
                    kind=MedalType.Kind.NOMINATION_PLACE,
                    title=f'{title} — {self._place_label(effective_place)}',
                    place=effective_place,
                    league_type=league_type,
                    nomination_code=code,
                    nomination_name=title,
                    season_ordinal=season_ordinal,
                    season_type=season_type,
                )

        statistic = self._statistic(text)
        if statistic and place and league_type:
            statistic_code = statistic
            result_value = self._result_value(text, statistic_code)
            return MedalDescriptor(
                code=f'stat.{statistic_code}.{league_type}.{place}',
                kind=MedalType.Kind.STATISTIC_PLACE,
                title=STATISTIC_MEDAL_TITLES[statistic_code][place],
                place=place,
                league_type=league_type,
                statistic=statistic_code,
                result_value=result_value,
                season_ordinal=season_ordinal,
                season_type=season_type,
            )

        auxiliary = self._auxiliary(text)
        if auxiliary and place:
            competition_code, title, variant = auxiliary
            canonical_league_type = None if competition_code == 'predictions' else league_type
            scope = f'.{canonical_league_type}' if canonical_league_type else ''
            variant_code = f'.{variant}' if variant else ''
            season_scoped = bool(league_type) or competition_code in {'predictions', 'saturday_cup_rating'}
            return MedalDescriptor(
                code=f'aux.{competition_code}{variant_code}{scope}.{place}',
                kind=MedalType.Kind.AUXILIARY_COMPETITION_PLACE,
                title=f'{title} — {self._place_label(place)}',
                place=place,
                league_type=league_type,
                competition_code=competition_code,
                variant=variant,
                season_ordinal=season_ordinal if season_scoped else None,
                season_type=season_type if season_scoped else None,
                edition=self._auxiliary_edition(
                    achievement.title,
                    competition_code,
                    variant,
                    season_ordinal,
                ),
            )

        for marker, (code, title) in HONORARY.items():
            if marker in text:
                honorary_season_ordinal = 8 if code == 'thanos_of_season' else season_ordinal
                honorary_season_type = Season.Type.RUSSIAN_CHAMPIONSHIP if code == 'thanos_of_season' else season_type
                return MedalDescriptor(
                    code=f'honorary.{code}',
                    kind=MedalType.Kind.HONORARY,
                    title=title,
                    season_ordinal=honorary_season_ordinal,
                    season_type=honorary_season_type,
                    season_year=season_year,
                    edition=f'{season_year} год' if code == 'rooster_of_year' and season_year else '',
                )

        if league_type and place and self._is_tournament_result(text):
            return MedalDescriptor(
                code=f'tournament.{league_type}.{place}',
                kind=MedalType.Kind.TOURNAMENT_PLACE,
                title=f'{League.Type(league_type).label} — {self._place_label(place)}',
                place=place,
                league_type=league_type,
                season_ordinal=season_ordinal,
                season_type=season_type,
                season_year=season_year,
            )

        return None

    @staticmethod
    def _place(text):
        if any(value in text for value in ('бронз', '3 место')):
            return 3
        if any(value in text for value in ('серебр', '2 место')):
            return 2
        if any(value in text for value in ('золот', 'чемпион', 'победител', 'обладател', '1 место')):
            return 1
        return None

    @staticmethod
    def _league_type(text, achievement):
        if 'итогов' in text:
            return League.Type.FINALS
        if 'лиги чемпион' in text or '(лч,' in text:
            return League.Type.CHAMPIONS_LEAGUE
        if any(value in text for value in ('кубок россии', 'кубка россии')) or re.search(
            r'\bкубок\s*\(\d+\s*сезон', text
        ):
            return League.Type.RUSSIAN_CUP
        if 'кубок высшей' in text or 'кубка высшей' in text:
            return League.Type.PREMIER_LEAGUE_CUP
        if 'кубок первой' in text or 'кубка первой' in text:
            return League.Type.FIRST_LEAGUE_CUP
        if 'кубок второй' in text or 'кубка второй' in text:
            return League.Type.SECOND_LEAGUE_CUP
        if 'кубок лиг' in text or 'кубка лиг' in text:
            return League.Type.LEAGUE_CUP
        if 'первая лига' in text or 'первой лиги' in text:
            return League.Type.FIRST_LEAGUE
        if 'вторая лига' in text or 'второй лиги' in text:
            return League.Type.SECOND_LEAGUE
        if 'высшая лига' in text or 'высшей лиги' in text or 'единая лига' in text:
            return League.Type.PREMIER_LEAGUE
        category = getattr(achievement, 'category', None)
        if category:
            return {
                'Чемпионат. Высшая лига': League.Type.PREMIER_LEAGUE,
                'Чемпионат. Первая лига': League.Type.FIRST_LEAGUE,
                'Чемпионат. Вторая лига': League.Type.SECOND_LEAGUE,
                'Лига Чемпионов': League.Type.CHAMPIONS_LEAGUE,
            }.get(category.title)
        if isinstance(achievement, TeamAchievement) and re.search(
            r'^(чемпионство|серебро|бронза|победитель чемпионата|'
            r'серебряный призер чемпионата|бронзовый призер чемпионата)',
            text,
        ):
            return League.Type.PREMIER_LEAGUE
        return None

    @staticmethod
    def _season(text, league_type):
        year_match = re.search(r'\b(20\d{2})\b', text)
        ordinal_match = re.search(r'(\d+)\s*сезон', text)
        season_year = int(year_match.group(1)) if year_match else None
        ordinal = int(ordinal_match.group(1)) if ordinal_match else None
        if league_type == League.Type.CHAMPIONS_LEAGUE:
            season_type = Season.Type.CHAMPIONS_LEAGUE
        elif league_type == League.Type.FINALS:
            season_type = Season.Type.FINAL_TOURNAMENT
        else:
            season_type = Season.Type.RUSSIAN_CHAMPIONSHIP
        return ordinal, season_type, season_year

    @staticmethod
    def _statistic(text):
        if 'мяч' in text:
            return MedalType.Statistic.GOALS
        if 'бутс' in text:
            return MedalType.Statistic.ASSISTS
        if 'перчат' in text:
            return MedalType.Statistic.CLEAN_SHEETS
        return None

    @staticmethod
    def _result_value(text, statistic):
        result_words = {
            'goals': r'гол(?:а|ов)?',
            'assists': r'(?:ассист(?:а|ов)?|передач(?:а|и)?)',
            'clean_sheets': r'сухар(?:ь|я|ей)?',
        }
        match = re.search(rf'\(?\b(\d+)\b\)?\s*{result_words[statistic]}', text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _career(text):
        patterns = [
            (MedalType.Unit.MATCHES, 'матч', 'сыгранных матчей'),
            (MedalType.Unit.CLEAN_SHEETS, 'сух', 'сухих таймов'),
            (MedalType.Unit.GOALS, 'забит', 'забитых голов'),
            (MedalType.Unit.ASSISTS, 'голев', 'голевых передач'),
        ]
        if 'за карьер' not in text:
            return None
        for unit, marker, label in patterns:
            if marker in text and (match := re.search(r'(\d+)', text)):
                threshold = int(match.group(1))
                return unit, threshold, f'{threshold} {label} за карьеру'
        return None

    @staticmethod
    def _auxiliary(text):
        if re.search(r'\belo\b', text):
            return 'elo', 'ELO', ''
        for marker, (code, title) in AUXILIARY_COMPETITIONS.items():
            if marker in text:
                variant = ''
                if code == 'arena_reborn':
                    variant = 'futsal' if 'futsal' in text else 'classic_9' if 'classic 9' in text else ''
                return code, title, variant
        return None

    @staticmethod
    def _external_edition(title):
        return re.sub(r'^(Победитель|Серебряный приз[её]р|Бронзовый приз[её]р)\s+', '', title, flags=re.I)

    @classmethod
    def _auxiliary_edition(cls, title, competition_code, variant, season_ordinal):
        if competition_code in {'predictions', 'fantasy_league', 'saturday_cup_rating'} and season_ordinal:
            return ''
        if competition_code in {'elo', 'europe_league'} and season_ordinal:
            return f'{season_ordinal} сезон'
        if competition_code == 'slotcybercup' and (
            edition_number := re.search(r'slotcybercup\s*#\s*(\d+)', title, flags=re.I)
        ):
            return f'SlotCyberCup#{edition_number.group(1)}'
        if competition_code == 'arena_reborn' and season_ordinal:
            variant_title = {
                'futsal': 'Futsal',
                'classic_9': 'Classic 9',
            }.get(variant)
            return f'{season_ordinal} сезон [{variant_title}]' if variant_title else f'{season_ordinal} сезон'
        return cls._external_edition(title)

    @staticmethod
    def _is_tournament_result(text):
        return any(
            value in text for value in ('чемпион', 'победител', 'обладател', 'призер', 'призёр', 'кубок', 'золото')
        )

    @staticmethod
    def _place_label(place):
        return {1: 'золото', 2: 'серебро', 3: 'бронза'}[place]


class LegacyMedalImporter:
    def __init__(self, apply=False):
        self.apply = apply
        self.classifier = LegacyMedalClassifier()
        self._legacy_awarded_dates = None
        self._legacy_season_cutoff_number = None
        self._medal_categories = {}
        self._career_medal_category = None

    def run(self):
        report = ImportReport()
        if self.apply:
            self._copy_medal_categories()
        sources = [
            (LegacyMedalMapping.SourceModel.TEAM_ACHIEVEMENT, TeamAchievement.objects.prefetch_related('team')),
            (
                LegacyMedalMapping.SourceModel.PLAYER_ACHIEVEMENT,
                Achievements.objects.select_related('category').prefetch_related('player'),
            ),
        ]
        for source_model, queryset in sources:
            for source in queryset.iterator(chunk_size=200):
                report.processed += 1
                recipients = (
                    source.team if source_model == LegacyMedalMapping.SourceModel.TEAM_ACHIEVEMENT else source.player
                )
                if not recipients.exists():
                    report.skipped_unassigned += 1
                    continue
                descriptor = self.classifier.classify(source)
                if not descriptor:
                    report.unresolved.append(f'{source_model}:{source.pk} {source.title}')
                    continue
                if descriptor.kind == MedalType.Kind.STATISTIC_PLACE and descriptor.result_value is None:
                    report.unresolved.append(
                        f'{source_model}:{source.pk} Cannot resolve the statistical result for {source.title!r}'
                    )
                    continue
                report.classified += 1
                if self.apply:
                    try:
                        status, warning = self._import_source(source_model, source, descriptor)
                    except (ValueError, ValidationError) as error:
                        report.import_errors.append(f'{source_model}:{source.pk} {error}')
                        continue
                    if warning:
                        report.resolution_warnings.append(f'{source_model}:{source.pk} {warning}')
                    if status == 'mapped':
                        report.already_mapped += 1
                    else:
                        report.imported += 1
        return report

    @transaction.atomic
    def _import_source(self, source_model, source, descriptor):
        mapping = (
            LegacyMedalMapping.objects.select_related('medal__medal_type')
            .filter(source_model=source_model, source_id=source.pk)
            .first()
        )
        if mapping:
            self._set_medal_type_order(mapping.medal.medal_type, descriptor)
            self._set_image_override(mapping.medal, descriptor, source)
            awarded_at = self._legacy_awarded_at(source_model, source, descriptor)
            overwrite_awarded_at = self._awarded_at_override(descriptor) is not None
            self._set_grant_dates(
                mapping.medal,
                source_model,
                source,
                awarded_at,
                overwrite=overwrite_awarded_at,
            )
            self._import_favorites(source_model, source, mapping.medal)
            return 'mapped', self._awarded_at_warning(descriptor, awarded_at)

        season = self._resolve_season(descriptor)
        if descriptor.season_ordinal and not season:
            raise ValueError(f'Cannot resolve season for {source_model}:{source.pk} {source.title!r}')
        descriptor, league = self._resolve_descriptor_and_league(descriptor, season, source)
        warnings = []
        if (
            descriptor.league_type
            and season
            and not league
            and not self._has_multiple_first_league_divisions(descriptor, season)
        ):
            warnings.append(
                f'No League row for {League.Type(descriptor.league_type).label!r} in {season.title!r}; '
                'created a season-scoped medal'
            )

        awarded_at = self._legacy_awarded_at(source_model, source, descriptor)
        if awarded_at_warning := self._awarded_at_warning(descriptor, awarded_at):
            warnings.append(awarded_at_warning)

        nomination = None
        if descriptor.nomination_code:
            nomination, _ = AwardNomination.objects.get_or_create(
                code=descriptor.nomination_code,
                defaults={'name': descriptor.nomination_name, 'order': 100},
            )
        medal_type, _ = MedalType.objects.get_or_create(
            code=descriptor.code,
            defaults={
                'kind': descriptor.kind,
                'title': descriptor.title,
                'description': source.description,
                'image': source.image.name if source.image else None,
                'league_type': None if descriptor.competition_code == 'predictions' else descriptor.league_type,
                'place': descriptor.place,
                'nomination': nomination,
                'statistic': descriptor.statistic,
                'competition_code': descriptor.competition_code,
                'variant': descriptor.variant,
                'threshold': descriptor.threshold,
                'unit': descriptor.unit,
                'order': self._medal_type_order(descriptor),
            },
        )
        self._set_medal_type_order(medal_type, descriptor)
        medal_key = self._medal_key(descriptor, medal_type, season, league, source)
        medal_category = self._medal_category(source, descriptor)
        medal, _ = Medal.objects.get_or_create(
            key=medal_key,
            defaults={
                'medal_type': medal_type,
                'category': medal_category,
                'season': season,
                'league': league,
                'edition': descriptor.edition,
                'result_value': descriptor.result_value,
                'title_override': source.title,
                'description_override': source.description,
                'image_override': self._image_override(descriptor, source),
            },
        )
        if medal.category_id is None and medal_category:
            medal.category = medal_category
            medal.save(update_fields=['category'])
        self._set_image_override(medal, descriptor, source)
        LegacyMedalMapping.objects.create(source_model=source_model, source_id=source.pk, medal=medal)
        if source_model == LegacyMedalMapping.SourceModel.PLAYER_ACHIEVEMENT:
            PlayerMedal.objects.bulk_create(
                [PlayerMedal(medal=medal, player=player, awarded_at=awarded_at) for player in source.player.all()],
                ignore_conflicts=True,
            )
        else:
            TeamMedal.objects.bulk_create(
                [
                    TeamMedal(
                        medal=medal,
                        team=team,
                        players_raw_list=source.players_raw_list,
                        awarded_at=awarded_at,
                    )
                    for team in source.team.all()
                ],
                ignore_conflicts=True,
            )
        overwrite_awarded_at = self._awarded_at_override(descriptor) is not None
        self._set_grant_dates(
            medal,
            source_model,
            source,
            awarded_at,
            overwrite=overwrite_awarded_at,
        )
        self._import_favorites(source_model, source, medal)
        return 'imported', '; '.join(warnings) or None

    @staticmethod
    def _import_favorites(source_model, source, medal):
        if source_model != LegacyMedalMapping.SourceModel.PLAYER_ACHIEVEMENT:
            return
        for profile in source.favorited_by_profiles.all():
            FavoriteMedal.objects.get_or_create(profile=profile, medal=medal)

    @classmethod
    def _set_medal_type_order(cls, medal_type, descriptor):
        order = cls._medal_type_order(descriptor)
        if medal_type.order != order:
            medal_type.order = order
            medal_type.save(update_fields=['order'])

    @staticmethod
    def _medal_type_order(descriptor):
        place_order = PLACE_ORDER.get(descriptor.place, 0)

        if descriptor.kind == MedalType.Kind.TOURNAMENT_PLACE:
            if descriptor.league_type in CUP_LEAGUE_ORDER:
                return 200 + CUP_LEAGUE_ORDER[descriptor.league_type] + place_order
            return 100 + place_order

        if descriptor.kind == MedalType.Kind.NOMINATION_PLACE:
            return NOMINATION_ORDER.get(descriptor.nomination_code, 1300) + place_order

        if descriptor.kind == MedalType.Kind.STATISTIC_PLACE:
            return STATISTIC_ORDER.get(descriptor.statistic, 1200) + place_order

        if descriptor.kind == MedalType.Kind.AUXILIARY_COMPETITION_PLACE:
            league_scope_order = (
                0 if descriptor.competition_code == 'predictions' else LEAGUE_SCOPE_ORDER.get(descriptor.league_type, 0)
            )
            return (
                AUXILIARY_COMPETITION_ORDER.get(descriptor.competition_code, 2000)
                + AUXILIARY_VARIANT_ORDER.get(descriptor.variant, 20)
                + league_scope_order
                + place_order
            )

        if descriptor.kind == MedalType.Kind.CAREER_MILESTONE:
            return CAREER_UNIT_ORDER.get(descriptor.unit, 20000) + (descriptor.threshold or 0)

        if descriptor.kind == MedalType.Kind.HONORARY:
            honorary_code = descriptor.code.removeprefix('honorary.')
            return HONORARY_ORDER.get(honorary_code, 3000)

        return 0

    def _copy_medal_categories(self):
        legacy_categories = list(AchievementCategory.objects.all())
        for legacy_category in legacy_categories:
            category, _ = MedalCategory.objects.update_or_create(
                title=legacy_category.title,
                defaults={
                    'description': legacy_category.description,
                    'order': legacy_category.order,
                },
            )
            self._medal_categories[legacy_category.pk] = category

        self._career_medal_category, _ = MedalCategory.objects.update_or_create(
            title='Карьерные достижения',
            defaults={
                'description': 'Медали за карьерные рубежи',
                'order': max((category.order for category in legacy_categories), default=0) + 1,
            },
        )

    def _medal_category(self, source, descriptor):
        if descriptor.kind == MedalType.Kind.CAREER_MILESTONE:
            return self._career_medal_category
        category_id = getattr(source, 'category_id', None)
        return self._medal_categories.get(category_id)

    def _legacy_awarded_at(self, source_model, source, descriptor):
        if awarded_at := self._awarded_at_override(descriptor):
            return awarded_at
        if descriptor.kind == MedalType.Kind.CAREER_MILESTONE:
            return None
        if self._legacy_awarded_dates is None:
            self._legacy_awarded_dates = self._load_legacy_awarded_dates()
        return self._legacy_awarded_dates.get((source_model, source.pk))

    def _awarded_at_override(self, descriptor):
        if (
            descriptor.competition_code == 'predictions'
            and descriptor.season_type == Season.Type.RUSSIAN_CHAMPIONSHIP
            and descriptor.season_ordinal == 15
        ):
            return date(2025, 12, 27)
        season = self._resolve_season(descriptor)
        if season and season.number < self._legacy_season_cutoff():
            return date(2020, 8, 20)
        return None

    def _legacy_season_cutoff(self):
        if self._legacy_season_cutoff_number is None:
            self._legacy_season_cutoff_number = (
                Season.objects.only('number')
                .get(
                    type=Season.Type.RUSSIAN_CHAMPIONSHIP,
                    title='ЧР, 5 сезон',
                )
                .number
            )
        return self._legacy_season_cutoff_number

    @staticmethod
    def _load_legacy_awarded_dates():
        dates = {}
        source_models = {
            LegacyMedalMapping.SourceModel.PLAYER_ACHIEVEMENT: Achievements,
            LegacyMedalMapping.SourceModel.TEAM_ACHIEVEMENT: TeamAchievement,
        }
        for source_model, model in source_models.items():
            content_type = ContentType.objects.get_for_model(model)
            creation_logs = (
                LogEntry.objects.filter(content_type=content_type, action_flag=ADDITION)
                .order_by('action_time')
                .values_list('object_id', 'action_time')
            )
            for object_id, action_time in creation_logs:
                try:
                    source_id = int(object_id)
                except (TypeError, ValueError):
                    continue
                dates.setdefault((source_model, source_id), timezone.localtime(action_time).date())
        return dates

    @staticmethod
    def _awarded_at_warning(descriptor, awarded_at):
        if descriptor.kind != MedalType.Kind.CAREER_MILESTONE and awarded_at is None:
            return 'No Django admin creation history; recipient award date remains empty'
        return None

    @staticmethod
    def _set_grant_dates(medal, source_model, source, awarded_at, *, overwrite=False):
        if awarded_at is None:
            return
        if source_model == LegacyMedalMapping.SourceModel.PLAYER_ACHIEVEMENT:
            grants = PlayerMedal.objects.filter(
                medal=medal,
                player__in=source.player.all(),
            )
        else:
            grants = TeamMedal.objects.filter(
                medal=medal,
                team__in=source.team.all(),
            )
        if not overwrite:
            grants = grants.filter(awarded_at__isnull=True)
        grants.update(awarded_at=awarded_at)

    @staticmethod
    def _image_override(descriptor, source):
        if descriptor.league_type == League.Type.FINALS and source.image:
            return source.image.name
        return None

    def _set_image_override(self, medal, descriptor, source):
        image_override = self._image_override(descriptor, source)
        if medal.image_override.name != image_override:
            medal.image_override = image_override
            medal.save(update_fields=['image_override'])

    @staticmethod
    def _resolve_season(descriptor):
        queryset = (
            Season.objects.filter(type=descriptor.season_type) if descriptor.season_type else Season.objects.none()
        )
        if descriptor.season_year:
            return queryset.filter(title__contains=str(descriptor.season_year)).first()
        if descriptor.season_ordinal:
            pattern = re.compile(rf'(^|\D){descriptor.season_ordinal}\s*сезон', flags=re.I)
            return next((season for season in queryset if pattern.search(season.title)), None)
        return None

    @classmethod
    def _resolve_descriptor_and_league(cls, descriptor, season, source):
        if cls._has_multiple_first_league_divisions(descriptor, season):
            return descriptor, None

        if descriptor.league_type != League.Type.LEAGUE_CUP:
            return descriptor, cls._resolve_league(descriptor.league_type, season, source)

        cup_types = (
            League.Type.PREMIER_LEAGUE_CUP,
            League.Type.FIRST_LEAGUE_CUP,
            League.Type.SECOND_LEAGUE_CUP,
            League.Type.LEAGUE_CUP,
        )
        candidates = League.objects.filter(championship=season, type__in=cup_types) if season else League.objects.none()
        league = cls._resolve_from_candidates(candidates, season, source)
        if not league:
            return descriptor, None

        resolved = replace(
            descriptor,
            code=f'tournament.{league.type}.{descriptor.place}',
            title=f'{league.get_type_display()} — {LegacyMedalClassifier._place_label(descriptor.place)}',
            league_type=league.type,
        )
        return resolved, league

    @staticmethod
    def _has_multiple_first_league_divisions(descriptor, season):
        return (
            season is not None
            and descriptor.league_type == League.Type.FIRST_LEAGUE
            and League.objects.filter(championship=season, type=League.Type.FIRST_LEAGUE).count() > 1
        )

    @classmethod
    def _resolve_league(cls, league_type, season, source):
        if not season or not league_type:
            return None
        leagues = League.objects.filter(championship=season, type=league_type)
        if leagues.count() == 1:
            return leagues.first()
        exact_title = League.Type(league_type).label
        exact = leagues.filter(title__iexact=exact_title)
        if exact.count() == 1:
            return exact.first()
        return cls._resolve_from_candidates(leagues, season, source)

    @staticmethod
    def _resolve_from_candidates(leagues, season, source):
        if isinstance(source, TeamAchievement):
            team_ids = source.team.values_list('id', flat=True)
            by_recipient = leagues.filter(teams__id__in=team_ids).distinct()
            if by_recipient.count() == 1:
                return by_recipient.first()
        if isinstance(source, Achievements):
            scored_leagues = []
            for candidate in leagues:
                matching_transfers = PlayerTransfer.objects.filter(
                    season_join=season,
                    trans_player__in=source.player.all(),
                    to_team__in=candidate.teams.all(),
                ).count()
                scored_leagues.append((matching_transfers, candidate))
            best_score = max((score for score, _ in scored_leagues), default=0)
            best_leagues = [candidate for score, candidate in scored_leagues if score == best_score and score > 0]
            if len(best_leagues) == 1:
                return best_leagues[0]
        return None

    @staticmethod
    def _medal_key(descriptor, medal_type, season, league, source):
        if season or league:
            return f'{medal_type.code}:season:{season.pk if season else 0}:league:{league.pk if league else 0}'
        if descriptor.edition:
            edition = re.sub(r'[^a-zа-я0-9]+', '-', descriptor.edition.lower()).strip('-')
            return f'{medal_type.code}:edition:{edition}'[:200]
        if descriptor.kind == MedalType.Kind.CAREER_MILESTONE:
            return f'{medal_type.code}:global'
        return f'{medal_type.code}:legacy:{source.pk}'
